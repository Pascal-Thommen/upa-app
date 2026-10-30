"""Control de IA: configuracion de la clave de Google Gemini y prueba de conexion en vivo."""

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import User
from ..permissions import require_permission
from ..services import gemini

router = APIRouter(prefix="/api/ai", tags=["AI"])


class AiConfigResponse(BaseModel):
    configured: bool
    masked_key: str
    source: str
    model: str


class AiConfigUpdate(BaseModel):
    api_key: str


class AiTestRequest(BaseModel):
    api_key: str | None = None


class AiTestResponse(BaseModel):
    ok: bool
    code: str
    message: str
    model: str


def require_admin(current_user: User = Depends(require_permission("apis"))) -> User:
    if (current_user.role or "").strip() != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado: solo los administradores pueden gestionar la IA.",
        )
    return current_user


def _config_response(db: Session) -> AiConfigResponse:
    key, source = gemini.resolve_api_key(db)
    return AiConfigResponse(
        configured=bool(key), masked_key=gemini.mask_key(key), source=source, model=settings.GEMINI_MODEL
    )


@router.get("/config", response_model=AiConfigResponse, summary="Estado de la clave de Gemini")
def get_ai_config(db: Session = Depends(get_db), _: User = Depends(require_permission("apis"))) -> AiConfigResponse:
    return _config_response(db)


@router.post("/config", response_model=AiConfigResponse, summary="Guardar la clave de Gemini (administradores)")
def set_ai_config(
    payload: AiConfigUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> AiConfigResponse:
    key = (payload.api_key or "").strip()
    if len(key) < 10 or any(c.isspace() for c in key):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="La clave de API no es válida: debe tener al menos 10 caracteres y no contener espacios.",
        )
    gemini.save_api_key(db, key, admin.email)
    return _config_response(db)


@router.post("/test-connection", response_model=AiTestResponse, summary="Prueba de conexión en vivo con Gemini")
def test_ai_connection(
    payload: AiTestRequest | None = Body(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> AiTestResponse:
    candidate = (payload.api_key or "").strip() if payload and payload.api_key else ""
    if candidate:
        key = candidate
    else:
        key, _source = gemini.resolve_api_key(db)
    result = gemini.check_connection(key)
    return AiTestResponse(ok=result.ok, code=result.code, message=result.message, model=result.model)
