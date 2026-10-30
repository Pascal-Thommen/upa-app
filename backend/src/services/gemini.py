"""Cliente de Google Gemini (Google AI Studio): almacenamiento de la clave y prueba de conexion en vivo."""

from dataclasses import dataclass

import httpx
from sqlalchemy.orm import Session

from ..config import settings
from ..models import AppSetting

GEMINI_KEY_SETTING = "GEMINI_API_KEY"


def mask_key(key: str) -> str:
    """Enmascara la clave dejando visibles solo los ultimos 4 caracteres."""
    clean = (key or "").strip()
    if not clean:
        return ""
    if len(clean) <= 8:
        return "*" * len(clean)
    return f"{clean[:4]}{'*' * 8}{clean[-4:]}"


def get_stored_key(db: Session) -> str:
    row = db.get(AppSetting, GEMINI_KEY_SETTING)
    return (row.value or "").strip() if row else ""


def resolve_api_key(db: Session) -> tuple[str, str]:
    """Devuelve (clave, origen) con origen 'database', 'environment' o 'none'."""
    stored = get_stored_key(db)
    if stored:
        return stored, "database"
    env_key = (settings.GEMINI_API_KEY or "").strip()
    if env_key:
        return env_key, "environment"
    return "", "none"


def save_api_key(db: Session, key: str, updated_by: str) -> None:
    row = db.get(AppSetting, GEMINI_KEY_SETTING)
    if row is None:
        db.add(AppSetting(key=GEMINI_KEY_SETTING, value=key, updated_by=updated_by))
    else:
        row.value = key
        row.updated_by = updated_by
    db.commit()


@dataclass
class ConnectionResult:
    ok: bool
    code: str
    message: str
    model: str


def _error_reason(response: httpx.Response) -> tuple[str, str]:
    """Extrae (status, mensaje) del cuerpo de error de la API de Google."""
    try:
        err = response.json().get("error", {})
    except ValueError:
        return "", ""
    details = " ".join(str(d.get("reason", "")) for d in err.get("details", []) if isinstance(d, dict))
    return f"{err.get('status', '')} {details}".strip(), str(err.get("message", ""))


def check_connection(api_key: str) -> ConnectionResult:
    """Prueba en vivo contra Google Gemini con un prompt minimo ('ping') y traduce el error a texto claro."""
    model = settings.GEMINI_MODEL
    if not (api_key or "").strip():
        return ConnectionResult(False, "NO_KEY", "No hay ninguna clave de API configurada. Pegue su clave primero.", model)

    base_url = settings.GEMINI_API_BASE_URL.rstrip("/")
    body = {"contents": [{"parts": [{"text": "ping"}]}], "generationConfig": {"maxOutputTokens": 8}}
    candidate_models = [model]
    if "generativelanguage.googleapis.com" in base_url:
        for fallback in ("gemini-2.0-flash", "gemini-2.5-flash"):
            if fallback not in candidate_models:
                candidate_models.append(fallback)

    response = None
    for idx, candidate in enumerate(candidate_models):
        url = f"{base_url}/v1beta/models/{candidate}:generateContent"
        try:
            response = httpx.post(
                url,
                json=body,
                headers={"x-goog-api-key": api_key.strip()},
                timeout=settings.GEMINI_TIMEOUT_SECONDS,
            )
        except httpx.TimeoutException:
            return ConnectionResult(False, "TIMEOUT", "Error de red con Google: tiempo de espera agotado.", model)
        except httpx.HTTPError:
            return ConnectionResult(False, "NETWORK", "Error de red con Google: no se pudo establecer la conexión.", model)

        if response.status_code == 404 and idx < len(candidate_models) - 1:
            continue
        break

    assert response is not None
    if response.status_code == 200:
        return ConnectionResult(True, "OK", f"Conexión exitosa con Google Gemini (Modelo {model} listo)", model)

    status_text, _ = _error_reason(response)
    if response.status_code == 429 or "RESOURCE_EXHAUSTED" in status_text:
        return ConnectionResult(
            False, "QUOTA", "Límite de cuota gratuito agotado (Quota exceeded). Intente más tarde.", model
        )
    if response.status_code in (400, 401, 403) or "API_KEY_INVALID" in status_text:
        if response.status_code == 403 and "PERMISSION_DENIED" in status_text and "API_KEY" not in status_text:
            return ConnectionResult(
                False, "FORBIDDEN", "Clave de API inválida o expirada (sin permiso para usar Gemini).", model
            )
        return ConnectionResult(False, "INVALID_KEY", "Clave de API inválida o expirada.", model)
    if response.status_code == 404:
        return ConnectionResult(False, "MODEL_NOT_FOUND", f"El modelo {model} no está disponible para esta clave.", model)
    if response.status_code >= 500:
        return ConnectionResult(
            False, "GOOGLE_ERROR", "Error de red con Google: el servicio no responde (error del servidor).", model
        )
    return ConnectionResult(False, "UNKNOWN", f"Google rechazó la solicitud (código {response.status_code}).", model)
