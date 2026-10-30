"""Cliente de Google Gemini (Google AI Studio): almacenamiento de la clave, prueba de conexion y autocompletado multimodal."""

import base64
import json
import re
from dataclasses import dataclass, field
from typing import Any

import httpx
from sqlalchemy.orm import Session

from ..config import settings
from ..models import AppSetting

GEMINI_KEY_SETTING = "GEMINI_API_KEY"
AUTOCOMPLETE_ERROR_PREFIX = "No se pudo autocompletar: Verifique la clave de IA en Control de IA"


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


@dataclass
class AutocompleteResult:
    ok: bool
    code: str
    message: str
    model: str
    suggestions: dict[str, Any] = field(default_factory=dict)


def _extract_candidate_json(payload: Any) -> dict[str, Any] | None:
    """Extrae el diccionario JSON devuelto por Gemini dentro de candidates[0].content.parts."""
    if not isinstance(payload, dict):
        return None
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        return None
    first = candidates[0] if isinstance(candidates[0], dict) else {}
    content = first.get("content") if isinstance(first.get("content"), dict) else {}
    parts = content.get("parts") if isinstance(content.get("parts"), list) else []
    raw_text = ""
    for part in parts:
        if isinstance(part, dict) and isinstance(part.get("text"), str):
            raw_text += part["text"]
    cleaned = raw_text.strip()
    if not cleaned:
        return None
    fenced = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE | re.DOTALL).strip()
    try:
        parsed = json.loads(fenced)
    except ValueError:
        match = re.search(r"\{.*\}", fenced, flags=re.DOTALL)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
        except ValueError:
            return None
    return parsed if isinstance(parsed, dict) else None


def _clean_group_list(raw_groups: Any) -> list[str]:
    if not isinstance(raw_groups, list):
        return []
    seen: list[str] = []
    for item in raw_groups:
        val = str(item or "").strip()
        if val and val not in seen:
            seen.append(val)
    return seen


def _build_autocomplete_prompt(
    form_data: dict[str, Any],
    empty_fields: list[str],
    available_groups: list[dict[str, str]],
    has_image: bool,
) -> str:
    groups_desc = ", ".join(f"{g.get('id')}: {g.get('name')}" for g in available_groups if g.get("id"))
    if not groups_desc:
        groups_desc = "ALL: Toda la comunidad UPA, TIE: Ingeniería Empresarial, PI: Ingeniería Industrial, TI: Tecnologías de la Información, PROF: Cuerpo docente"

    existing_summary = {
        k: v
        for k, v in form_data.items()
        if k in ("title", "caption", "content", "location", "event_start", "event_end", "target_groups", "category")
        and v not in (None, "", [])
    }

    return (
        "Eres el asistente editorial inteligente de la Universidad Paraguayo Alemana (UPA). "
        "Analiza los datos actuales del formulario"
        + (" y la imagen adjunta" if has_image else "")
        + " para sugerir valores ÚNICAMENTE para los campos que están vacíos.\n"
        f"Datos actuales ya ingresados (NO modificar): {json.dumps(existing_summary, ensure_ascii=False)}\n"
        f"Campos vacíos a completar si hay información suficiente: {', '.join(empty_fields)}\n"
        f"Grupos destinatarios válidos en UPA: {groups_desc}\n"
        "Categorías válidas: MELDUNG, ANKUENDIGUNG, VERANSTALTUNG, STELLENANGEBOT.\n"
        "Devuelve exclusivamente un objeto JSON válido con las claves de los campos vacíos que puedas inferir "
        "(por ejemplo: title, caption, content, is_event, event_start en formato YYYY-MM-DDTHH:MM, "
        "event_end en formato YYYY-MM-DDTHH:MM, location, target_groups como lista de códigos, "
        "category, has_registration, link_label, link_url)."
    )


def _filter_only_empty_fields(form_data: dict[str, Any], raw_suggestions: dict[str, Any]) -> dict[str, Any]:
    """Garantiza que solo se devuelvan valores para los campos que estaban vacios en el formulario."""
    filtered: dict[str, Any] = {}
    text_fields = (
        "title",
        "caption",
        "content",
        "location",
        "event_start",
        "event_end",
        "category",
        "link_label",
        "link_url",
    )
    for field_name in text_fields:
        existing_val = str(form_data.get(field_name) or "").strip()
        if existing_val:
            continue
        candidate_val = raw_suggestions.get(field_name)
        if isinstance(candidate_val, str) and candidate_val.strip():
            filtered[field_name] = candidate_val.strip()

    existing_groups = _clean_group_list(form_data.get("target_groups"))
    if not existing_groups:
        suggested_groups = _clean_group_list(raw_suggestions.get("target_groups"))
        if suggested_groups:
            filtered["target_groups"] = suggested_groups

    post_type = str(form_data.get("post_type") or "MANUAL").strip().upper()
    if post_type != "EMERGENCY_BANNER":
        if not form_data.get("is_event"):
            if (
                raw_suggestions.get("is_event") is True
                or "event_start" in filtered
                or "location" in filtered
            ):
                filtered["is_event"] = True

    if not form_data.get("has_registration") and raw_suggestions.get("has_registration") is True:
        filtered["has_registration"] = True

    return filtered


def autocomplete_publication(
    api_key: str,
    *,
    form_data: dict[str, Any],
    available_groups: list[dict[str, str]] | None = None,
    image_bytes: bytes | None = None,
    image_mime_type: str | None = None,
) -> AutocompleteResult:
    """Envía el texto actual y la imagen opcional al modelo multimodal Gemini Flash y devuelve solo campos vacíos."""
    model = settings.GEMINI_MODEL
    if not (api_key or "").strip():
        return AutocompleteResult(
            False,
            "NO_KEY",
            f"{AUTOCOMPLETE_ERROR_PREFIX}.",
            model,
            {},
        )

    text_fields = (
        "title",
        "caption",
        "content",
        "location",
        "event_start",
        "event_end",
        "category",
        "link_label",
        "link_url",
    )
    empty_fields = [f for f in text_fields if not str(form_data.get(f) or "").strip()]
    if not _clean_group_list(form_data.get("target_groups")):
        empty_fields.append("target_groups")

    prompt = _build_autocomplete_prompt(
        form_data=form_data,
        empty_fields=empty_fields,
        available_groups=available_groups or [],
        has_image=bool(image_bytes and image_mime_type),
    )

    parts: list[dict[str, Any]] = [{"text": prompt}]
    if image_bytes and image_mime_type:
        parts.append(
            {
                "inline_data": {
                    "mime_type": image_mime_type,
                    "data": base64.b64encode(image_bytes).decode("ascii"),
                }
            }
        )

    body = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
        },
    }

    base_url = settings.GEMINI_API_BASE_URL.rstrip("/")
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
            return AutocompleteResult(
                False,
                "TIMEOUT",
                f"{AUTOCOMPLETE_ERROR_PREFIX} (tiempo de espera agotado).",
                model,
                {},
            )
        except httpx.HTTPError:
            return AutocompleteResult(
                False,
                "NETWORK",
                f"{AUTOCOMPLETE_ERROR_PREFIX} (error de red con Google).",
                model,
                {},
            )

        if response.status_code == 404 and idx < len(candidate_models) - 1:
            continue
        break

    assert response is not None
    if response.status_code != 200:
        status_text, _ = _error_reason(response)
        if response.status_code == 429 or "RESOURCE_EXHAUSTED" in status_text:
            return AutocompleteResult(
                False,
                "QUOTA",
                f"{AUTOCOMPLETE_ERROR_PREFIX} (límite de cuota agotado).",
                model,
                {},
            )
        if response.status_code in (400, 401, 403) or "API_KEY_INVALID" in status_text:
            return AutocompleteResult(
                False,
                "INVALID_KEY",
                f"{AUTOCOMPLETE_ERROR_PREFIX}.",
                model,
                {},
            )
        return AutocompleteResult(
            False,
            "GOOGLE_ERROR",
            f"{AUTOCOMPLETE_ERROR_PREFIX} (código {response.status_code}).",
            model,
            {},
        )

    try:
        resp_json = response.json()
    except ValueError:
        return AutocompleteResult(
            False,
            "INVALID_RESPONSE",
            f"{AUTOCOMPLETE_ERROR_PREFIX} (respuesta inválida).",
            model,
            {},
        )

    parsed_suggestions = _extract_candidate_json(resp_json)
    if parsed_suggestions is None:
        return AutocompleteResult(
            False,
            "INVALID_RESPONSE",
            f"{AUTOCOMPLETE_ERROR_PREFIX} (formato no reconocido).",
            model,
            {},
        )

    suggestions = _filter_only_empty_fields(form_data, parsed_suggestions)
    return AutocompleteResult(True, "OK", "Campos completados por IA", model, suggestions)
