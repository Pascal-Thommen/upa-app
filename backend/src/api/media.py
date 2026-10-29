import logging
import os
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.responses import Response
from starlette.types import Scope

from ..auth import require_editor
from ..config import settings
from ..models import User
from ..schemas.feed import ErrorResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/media", tags=["Media"])

UPLOADS_URL_PREFIX = "/uploads"
CHUNK_SIZE = 64 * 1024

# Tipo MIME permitido -> extension canonica en disco. La extension nunca se toma del nombre del cliente.
ALLOWED_CONTENT_TYPES: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
}


class UploadsStaticFiles(StaticFiles):
    """
    Entrega de los archivos subidos con cache para clientes moviles. Los nombres son UUID y
    nunca cambian, por lo que el contenido puede cachearse a largo plazo como inmutable.
    """

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        if response.status_code in (200, 304):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            response.headers["X-Content-Type-Options"] = "nosniff"
        return response


class MediaUploadResponse(BaseModel):
    url: str = Field(..., description="URL absoluta del archivo, accesible para clientes moviles")
    filename: str = Field(..., description="Nombre unico generado en el servidor (UUID + extension)")
    content_type: str = Field(..., description="Tipo MIME verificado por contenido")
    size_bytes: int = Field(..., ge=1, description="Tamano del archivo guardado en bytes")

    model_config = {
        "json_schema_extra": {
            "example": {
                "url": "https://api.upa.edu.py/uploads/3f2b8c1e4d5a4f7e9a0b1c2d3e4f5a6b.png",
                "filename": "3f2b8c1e4d5a4f7e9a0b1c2d3e4f5a6b.png",
                "content_type": "image/png",
                "size_bytes": 482133,
            }
        }
    }


def get_upload_dir() -> Path:
    """Devuelve el directorio persistente de subidas y lo crea si no existe."""
    upload_dir = Path(settings.UPLOAD_DIR).resolve()
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


def sniff_content_type(header: bytes) -> str | None:
    """Detecta el tipo real del archivo por sus bytes iniciales (magic bytes)."""
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(header) >= 12 and header[0:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "image/webp"
    if header.startswith(b"%PDF-"):
        return "application/pdf"
    if len(header) >= 8 and header[4:8] == b"ftyp":
        return "video/mp4"
    if header.startswith(b"\x1a\x45\xdf\xa3"):
        return "video/webm"
    return None


def _build_public_url(request: Request, filename: str) -> str:
    base = (settings.PUBLIC_BASE_URL or "").strip().rstrip("/")
    if not base:
        base = str(request.base_url).rstrip("/")
    return f"{base}{UPLOADS_URL_PREFIX}/{filename}"


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


@router.post(
    "/upload",
    response_model=MediaUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Subir imagen (JPG, PNG, WEBP) o documento PDF de hasta 10 MB",
    responses={
        400: {
            "model": ErrorResponse,
            "description": "Archivo ausente, vacio, demasiado grande o con tipo no permitido",
        },
        401: {"model": ErrorResponse, "description": "Token JWT ausente, invalido o expirado"},
        403: {"model": ErrorResponse, "description": "Permisos insuficientes (requiere rol editor o admin)"},
        500: {"model": ErrorResponse, "description": "No se pudo persistir el archivo en el servidor"},
    },
)
async def upload_media(
    request: Request,
    file: UploadFile | None = File(None, description="Archivo multipart/form-data (campo 'file')"),
    current_user: User = Depends(require_editor),
) -> MediaUploadResponse:
    """
    Guarda el archivo de forma persistente con nombre UUID y devuelve su URL publica.
    El tipo se valida por contenido real (no solo por el encabezado del cliente) y el
    tamano se limita durante la lectura en bloques, sin cargar el archivo completo en memoria.
    """
    if file is None:
        raise _bad_request("Falta el archivo multipart (campo 'file').")

    max_size = settings.MAX_UPLOAD_SIZE_BYTES
    declared_type = (file.content_type or "").split(";")[0].strip().lower()
    if declared_type not in ALLOWED_CONTENT_TYPES:
        raise _bad_request("Tipo de archivo no permitido. Formatos validos: JPG, PNG, WEBP y PDF.")

    first_chunk = await file.read(CHUNK_SIZE)
    if not first_chunk:
        raise _bad_request("El archivo esta vacio.")

    real_type = sniff_content_type(first_chunk)
    if real_type is None or real_type != declared_type:
        raise _bad_request("El contenido del archivo no coincide con un formato permitido (JPG, PNG, WEBP, PDF).")

    try:
        upload_dir = get_upload_dir()
    except OSError as exc:
        logger.error("[Media] Directorio de subidas no disponible: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="El almacenamiento de archivos no esta disponible.",
        ) from exc

    filename = f"{uuid.uuid4().hex}{ALLOWED_CONTENT_TYPES[real_type]}"
    target_path = upload_dir / filename

    # Escritura atomica: primero archivo temporal en el mismo directorio, luego rename
    size = 0
    tmp_path: str | None = None
    try:
        fd, tmp_path = tempfile.mkstemp(dir=upload_dir, prefix=".upload-", suffix=".part")
        with os.fdopen(fd, "wb") as out:
            chunk = first_chunk
            while chunk:
                size += len(chunk)
                if size > max_size:
                    raise _bad_request(
                        f"El archivo supera el tamano maximo permitido de {max_size // (1024 * 1024)} MB."
                    )
                out.write(chunk)
                chunk = await file.read(CHUNK_SIZE)
            out.flush()
            os.fsync(out.fileno())
        os.chmod(tmp_path, 0o644)
        os.replace(tmp_path, target_path)
        tmp_path = None
    except HTTPException:
        raise
    except OSError as exc:
        logger.error("[Media] Error al escribir archivo subido: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo guardar el archivo en el servidor.",
        ) from exc
    finally:
        if tmp_path is not None and os.path.exists(tmp_path):
            os.remove(tmp_path)

    logger.info(
        "[Media] Archivo subido user_id=%s filename=%s type=%s size_bytes=%s",
        current_user.id,
        filename,
        real_type,
        size,
    )
    return MediaUploadResponse(
        url=_build_public_url(request, filename),
        filename=filename,
        content_type=real_type,
        size_bytes=size,
    )
