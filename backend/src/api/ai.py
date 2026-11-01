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
    system_prompt_autocomplete: str
    system_prompt_instagram: str
    default_system_prompt_autocomplete: str = gemini.DEFAULT_SYSTEM_PROMPT_AUTOCOMPLETE
    default_system_prompt_instagram: str = gemini.DEFAULT_SYSTEM_PROMPT_INSTAGRAM
    quota_rpm: int = gemini.FREE_TIER_QUOTA_RPM


class AiConfigUpdate(BaseModel):
    api_key: str | None = None
    system_prompt: str | None = None
    system_prompt_autocomplete: str | None = None
    system_prompt_instagram: str | None = None


class AiPromptUpdate(BaseModel):
    system_prompt: str | None = None
    system_prompt_autocomplete: str | None = None
    system_prompt_instagram: str | None = None


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


def _config_response(db: Session) -> AiConfigResponse:
    key, source = gemini.resolve_api_key(db)
    active_model = gemini.resolve_active_model(db)
    sys_prompt_auto = gemini.get_system_prompt_autocomplete(db)
    sys_prompt_ig = gemini.get_system_prompt_instagram(db)
    return AiConfigResponse(
        configured=bool(key),
        masked_key=gemini.mask_key(key),
        source=source,
        model=active_model,
        system_prompt=sys_prompt_auto,
        system_prompt_autocomplete=sys_prompt_auto,
        system_prompt_instagram=sys_prompt_ig,
        default_system_prompt_autocomplete=gemini.DEFAULT_SYSTEM_PROMPT_AUTOCOMPLETE,
        default_system_prompt_instagram=gemini.DEFAULT_SYSTEM_PROMPT_INSTAGRAM,
        quota_rpm=gemini.FREE_TIER_QUOTA_RPM,
    )


def _validate_prompt_length(prompt_text: str) -> str:
    clean_prompt = prompt_text.strip()
    if len(clean_prompt) > 4000:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El prompt del sistema no puede superar los 4000 caracteres.",
        )
    return clean_prompt


@router.get("/config", response_model=AiConfigResponse, summary="Estado de la clave y configuración de Gemini")
def get_ai_config(db: Session = Depends(get_db), _: User = Depends(require_ai_read)) -> AiConfigResponse:
    return _config_response(db)


@router.post("/config", response_model=AiConfigResponse, summary="Guardar clave o prompts de Gemini (permiso apis)")
def set_ai_config(
    payload: AiConfigUpdate,
    db: Session = Depends(get_db),
    operator: User = Depends(require_permission("apis")),
) -> AiConfigResponse:
    raw_key = payload.api_key
    has_prompt_fields = (
        payload.system_prompt is not None
        or payload.system_prompt_autocomplete is not None
        or payload.system_prompt_instagram is not None
    )
    has_key_field = (raw_key is not None and len(raw_key) > 0) or not has_prompt_fields
    if has_key_field:
        key = (raw_key or "").strip()
        if len(key) < 10 or any(c.isspace() for c in key):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="La clave de API no es válida: debe tener al menos 10 caracteres y no contener espacios.",
            )
        gemini.save_api_key(db, key, operator.email)

    autocomplete_raw = (
        payload.system_prompt_autocomplete
        if payload.system_prompt_autocomplete is not None
        else payload.system_prompt
    )
    if autocomplete_raw is not None:
        clean_auto = _validate_prompt_length(autocomplete_raw)
        gemini.save_system_prompt_autocomplete(db, clean_auto, operator.email)

    if payload.system_prompt_instagram is not None:
        clean_ig = _validate_prompt_length(payload.system_prompt_instagram)
        gemini.save_system_prompt_instagram(db, clean_ig, operator.email)

    return _config_response(db)


@router.post("/system-prompt", response_model=AiConfigResponse, summary="Guardar los prompts de sistema para IA")
@router.put("/system-prompt", response_model=AiConfigResponse, summary="Actualizar los prompts de sistema para IA")
def update_ai_system_prompt(
    payload: AiPromptUpdate,
    db: Session = Depends(get_db),
    operator: User = Depends(require_permission("apis")),
) -> AiConfigResponse:
    autocomplete_raw = (
        payload.system_prompt_autocomplete
        if payload.system_prompt_autocomplete is not None
        else payload.system_prompt
    )
    if autocomplete_raw is None and payload.system_prompt_instagram is None:
        autocomplete_raw = ""

    if autocomplete_raw is not None:
        clean_auto = _validate_prompt_length(str(autocomplete_raw))
        gemini.save_system_prompt_autocomplete(db, clean_auto, operator.email)

    if payload.system_prompt_instagram is not None:
        clean_ig = _validate_prompt_length(str(payload.system_prompt_instagram))
        gemini.save_system_prompt_instagram(db, clean_ig, operator.email)

    return _config_response(db)


@router.post("/test-connection", response_model=AiTestResponse, summary="Prueba de conexión en vivo con Gemini")
def test_ai_connection(
    payload: AiTestRequest | None = Body(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("apis")),
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
