"""IA: configuracion de la clave de Google Gemini, prompt del sistema y prueba de conexion en vivo."""

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import User
from ..permissions import effective_permissions, require_permission
from ..services import gemini

router = APIRouter(prefix="/api/ai", tags=["AI"])


class AiConfigResponse(BaseModel):
    configured: bool
    masked_key: str
    source: str
    model: str
    system_prompt: str
    quota_rpm: int = gemini.FREE_TIER_QUOTA_RPM


class AiConfigUpdate(BaseModel):
    api_key: str | None = None
    system_prompt: str | None = None


class AiPromptUpdate(BaseModel):
    system_prompt: str = ""


class AiTestRequest(BaseModel):
    api_key: str | None = None


class AiTestResponse(BaseModel):
    ok: bool
    code: str
    message: str
    model: str
    quota_rpm: int = gemini.FREE_TIER_QUOTA_RPM


def require_ai_read(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    perms = effective_permissions(db, current_user)
    if "apis" not in perms and "publicaciones" not in perms:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado: su cuenta no tiene permiso para consultar la configuración de IA.",
        )
    return current_user


def require_admin(current_user: User = Depends(require_permission("apis"))) -> User:
    if (current_user.role or "").strip() != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado: solo los administradores pueden gestionar la IA.",
        )
    return current_user


def _config_response(db: Session) -> AiConfigResponse:
    key, source = gemini.resolve_api_key(db)
    active_model = gemini.resolve_active_model(db)
    sys_prompt = gemini.get_system_prompt(db)
    return AiConfigResponse(
        configured=bool(key),
        masked_key=gemini.mask_key(key),
        source=source,
        model=active_model,
        system_prompt=sys_prompt,
        quota_rpm=gemini.FREE_TIER_QUOTA_RPM,
    )


@router.get("/config", response_model=AiConfigResponse, summary="Estado de la clave y configuración de Gemini")
def get_ai_config(db: Session = Depends(get_db), _: User = Depends(require_ai_read)) -> AiConfigResponse:
    return _config_response(db)


@router.post("/config", response_model=AiConfigResponse, summary="Guardar clave o prompt de Gemini (administradores)")
def set_ai_config(
    payload: AiConfigUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> AiConfigResponse:
    raw_key = payload.api_key
    has_key_field = (raw_key is not None and bool(raw_key.strip())) or payload.system_prompt is None
    if has_key_field:
        key = (raw_key or "").strip()
        if len(key) < 10 or any(c.isspace() for c in key):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="La clave de API no es válida: debe tener al menos 10 caracteres y no contener espacios.",
            )
        gemini.save_api_key(db, key, admin.email)

    if payload.system_prompt is not None:
        clean_prompt = payload.system_prompt.strip()
        if len(clean_prompt) > 4000:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="El prompt del sistema no puede superar los 4000 caracteres.",
            )
        gemini.save_system_prompt(db, clean_prompt, admin.email)

    return _config_response(db)


@router.post("/system-prompt", response_model=AiConfigResponse, summary="Guardar el prompt de sistema para redaccion con IA")
@router.put("/system-prompt", response_model=AiConfigResponse, summary="Actualizar el prompt de sistema para redaccion con IA")
def update_ai_system_prompt(
    payload: AiPromptUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> AiConfigResponse:
    prompt_text = str(payload.system_prompt or "").strip()
    if len(prompt_text) > 4000:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El prompt del sistema no puede superar los 4000 caracteres.",
        )
    gemini.save_system_prompt(db, prompt_text, admin.email)
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
    result = gemini.check_connection(key, db=db)
    return AiTestResponse(
        ok=result.ok,
        code=result.code,
        message=result.message,
        model=result.model,
        quota_rpm=gemini.FREE_TIER_QUOTA_RPM,
    )
