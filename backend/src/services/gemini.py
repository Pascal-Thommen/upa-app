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
GEMINI_MODEL_SETTING = "GEMINI_ACTIVE_MODEL"
GEMINI_SYSTEM_PROMPT_SETTING = "GEMINI_SYSTEM_PROMPT"
AUTOCOMPLETE_ERROR_PREFIX = "No se pudo autocompletar: Verifique la clave de IA en Control de IA"

DEFAULT_SYSTEM_PROMPT = (
    "Eres el asistente editorial inteligente de la Universidad Paraguayo Alemana (UPA). "
    "Redacta siempre en español claro, institucional y conciso, utilizando formato de fecha "
    "paraguayo (DD/MM/YYYY) y sistema horario de 24 horas (HH:mm). No inventes fechas ni "
    "horas de finalización si no están explícitamente indicadas."
)

FREE_TIER_QUOTA_RPM = 15

# Orden de prioridad de modelos gratuitos Gemini Flash (mas reciente primero)
PREFERRED_FLASH_MODELS: tuple[str, ...] = (
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
)


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


def get_stored_model(db: Session | None) -> str:
    if db is None:
        return ""
    row = db.get(AppSetting, GEMINI_MODEL_SETTING)
    return (row.value or "").strip() if row else ""


def resolve_active_model(db: Session | None = None) -> str:
    """Devuelve el modelo Gemini Flash activo (guardado tras deteccion o predeterminado en configuracion)."""
    stored_model = get_stored_model(db)
    if stored_model:
        return stored_model
    configured = (settings.GEMINI_MODEL or "").strip()
    return configured or "gemini-2.5-flash"


def save_active_model(db: Session | None, model_name: str, updated_by: str = "system") -> None:
    if db is None or not (model_name or "").strip():
        return
    clean_model = model_name.strip()
    row = db.get(AppSetting, GEMINI_MODEL_SETTING)
    if row is None:
        db.add(AppSetting(key=GEMINI_MODEL_SETTING, value=clean_model, updated_by=updated_by))
    else:
        row.value = clean_model
        row.updated_by = updated_by
    db.commit()


def get_system_prompt(db: Session | None) -> str:
    """Devuelve el prompt de sistema configurado o el prompt institucional por defecto."""
    if db is None:
        return DEFAULT_SYSTEM_PROMPT
    row = db.get(AppSetting, GEMINI_SYSTEM_PROMPT_SETTING)
    if row is not None and (row.value or "").strip():
        return row.value.strip()
    return DEFAULT_SYSTEM_PROMPT


def save_system_prompt(db: Session, prompt_text: str, updated_by: str) -> str:
    """Guarda el prompt de sistema personalizado (o restaura el predeterminado si se envia vacio)."""
    clean = (prompt_text or "").strip()
    effective = clean if clean else DEFAULT_SYSTEM_PROMPT
    row = db.get(AppSetting, GEMINI_SYSTEM_PROMPT_SETTING)
    if row is None:
        db.add(AppSetting(key=GEMINI_SYSTEM_PROMPT_SETTING, value=effective, updated_by=updated_by))
    else:
        row.value = effective
        row.updated_by = updated_by
    db.commit()
    return effective


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


def _parse_flash_model_sort_key(model_id: str) -> tuple[int, int, int, int, str]:
    """
    Ordena los modelos Gemini Flash gratuitos priorizando la version estable mas reciente
    (ej. gemini-2.5-flash > gemini-2.0-flash > gemini-1.5-flash) y dejando variantes -lite o -preview detras.
    """
    clean = model_id.removeprefix("models/").strip().lower()
    m = re.match(r"^gemini-(\d+)(?:\.(\d+))?-flash(.*)$", clean)
    if not m:
        return (0, 0, 0, 0, clean)
    major = int(m.group(1))
    minor = int(m.group(2) or 0)
    suffix = (m.group(3) or "").strip()
    # Priorizar modelo base exacto ("") o "-latest" sobre "-lite", "-exp", "-preview" o "-001"
    is_exact_base = 2 if suffix in ("", "-latest") else (1 if not ("lite" in suffix or "8b" in suffix) else 0)
    is_stable = 1 if ("exp" not in suffix and "preview" not in suffix) else 0
    return (major, minor, is_exact_base, is_stable, clean)


def discover_available_flash_models(api_key: str, base_url: str | None = None) -> list[str]:
    """
    Consulta el catalogo de modelos disponibles para la clave en Google AI Studio (GET /v1beta/models)
    y devuelve los modelos Gemini Flash compatibles con generateContent ordenados del mas reciente al mas antiguo.
    """
    clean_key = (api_key or "").strip()
    if not clean_key:
        return []
    resolved_base = (base_url or settings.GEMINI_API_BASE_URL).rstrip("/")
    url = f"{resolved_base}/v1beta/models"
    try:
        resp = httpx.get(
            url,
            headers={"x-goog-api-key": clean_key},
            timeout=min(float(settings.GEMINI_TIMEOUT_SECONDS or 15.0), 8.0),
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
    except (httpx.HTTPError, ValueError):
        return []

    raw_models = data.get("models") if isinstance(data, dict) else None
    if not isinstance(raw_models, list):
        return []

    discovered: list[str] = []
    for item in raw_models:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").removeprefix("models/").strip()
        if not name:
            continue
        lower_name = name.lower()
        if not lower_name.startswith("gemini-") or "flash" not in lower_name:
            continue
        if any(excluded in lower_name for excluded in ("image", "tts", "audio", "live", "thinking", "vision")):
            continue
        methods = item.get("supportedGenerationMethods")
        if isinstance(methods, list) and methods and "generateContent" not in methods:
            continue
        if name not in discovered:
            discovered.append(name)

    discovered.sort(key=_parse_flash_model_sort_key, reverse=True)
    return discovered


def build_candidate_flash_models(
    api_key: str,
    *,
    preferred_model: str | None = None,
    db: Session | None = None,
) -> list[str]:
    """
    Construye la lista priorizada de modelos Gemini Flash en el contingente gratuito (15 RPM):
    1. Si el servidor expone /v1beta/models, prioriza el Flash mas reciente descubierto.
    2. Añade el modelo preferido/configurado y la cadena de respaldo (gemini-2.5-flash, gemini-2.0-flash, gemini-1.5-flash).
    """
    base_url = settings.GEMINI_API_BASE_URL.rstrip("/")
    candidates: list[str] = []

    discovered = discover_available_flash_models(api_key, base_url=base_url)
    for m in discovered:
        if m not in candidates:
            candidates.append(m)

    initial = (preferred_model or resolve_active_model(db) or settings.GEMINI_MODEL or "").strip()
    if initial and initial not in candidates:
        candidates.append(initial)

    for fallback in PREFERRED_FLASH_MODELS:
        if fallback not in candidates:
            candidates.append(fallback)

    return candidates


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


def check_connection(api_key: str, *, db: Session | None = None) -> ConnectionResult:
    """
    Prueba en vivo contra Google Gemini con un prompt minimo ('ping'), descubre automaticamente
    el modelo Gemini Flash gratuito mas reciente disponible (15 RPM) y devuelve el modelo activo real.
    """
    initial_model = resolve_active_model(db)
    if not (api_key or "").strip():
        return ConnectionResult(
            False,
            "NO_KEY",
            "No hay ninguna clave de API configurada. Pegue su clave primero.",
            initial_model,
        )

    base_url = settings.GEMINI_API_BASE_URL.rstrip("/")
    body = {"contents": [{"parts": [{"text": "ping"}]}], "generationConfig": {"maxOutputTokens": 8}}
    candidate_models = build_candidate_flash_models(api_key, preferred_model=initial_model, db=db)

    response = None
    active_model = candidate_models[0] if candidate_models else initial_model
    for idx, candidate in enumerate(candidate_models):
        active_model = candidate
        url = f"{base_url}/v1beta/models/{candidate}:generateContent"
        try:
            response = httpx.post(
                url,
                json=body,
                headers={"x-goog-api-key": api_key.strip()},
                timeout=settings.GEMINI_TIMEOUT_SECONDS,
            )
        except httpx.TimeoutException:
            return ConnectionResult(
                False, "TIMEOUT", "Error de red con Google: tiempo de espera agotado.", active_model
            )
        except httpx.HTTPError:
            return ConnectionResult(
                False, "NETWORK", "Error de red con Google: no se pudo establecer la conexión.", active_model
            )

        if response.status_code == 404 and idx < len(candidate_models) - 1:
            continue
        break

    assert response is not None
    if response.status_code == 200:
        save_active_model(db, active_model)
        return ConnectionResult(
            True,
            "OK",
            f"Conexión exitosa con Google Gemini (Modelo {active_model} listo)",
            active_model,
        )

    status_text, _ = _error_reason(response)
    if response.status_code == 429 or "RESOURCE_EXHAUSTED" in status_text:
        return ConnectionResult(
            False,
            "QUOTA",
            "Límite de cuota gratuito agotado (Quota exceeded). Intente más tarde.",
            active_model,
        )
    if response.status_code in (400, 401, 403) or "API_KEY_INVALID" in status_text:
        if response.status_code == 403 and "PERMISSION_DENIED" in status_text and "API_KEY" not in status_text:
            return ConnectionResult(
                False,
                "FORBIDDEN",
                "Clave de API inválida o expirada (sin permiso para usar Gemini).",
                active_model,
            )
        return ConnectionResult(False, "INVALID_KEY", "Clave de API inválida o expirada.", active_model)
    if response.status_code == 404:
        return ConnectionResult(
            False,
            "MODEL_NOT_FOUND",
            f"El modelo {active_model} no está disponible para esta clave.",
            active_model,
        )
    if response.status_code >= 500:
        return ConnectionResult(
            False,
            "GOOGLE_ERROR",
            "Error de red con Google: el servicio no responde (error del servidor).",
            active_model,
        )
    return ConnectionResult(
        False, "UNKNOWN", f"Google rechazó la solicitud (código {response.status_code}).", active_model
    )


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
    system_prompt: str | None = None,
) -> str:
    groups_desc = ", ".join(f"{g.get('id')}: {g.get('name')}" for g in available_groups if g.get("id"))
    if not groups_desc:
        groups_desc = "ALL: Toda la comunidad UPA, TIE: Ingeniería Empresarial, PI: Ingeniería Industrial, TI: Tecnologías de la Información, PROF: Cuerpo docente"

    existing_summary = {
        k: v
        for k, v in form_data.items()
        if k
        in (
            "title",
            "caption",
            "content",
            "location",
            "event_start",
            "event_end",
            "event_date",
            "event_start_time",
            "event_end_time",
            "target_groups",
            "category",
        )
        and v not in (None, "", [])
    }

    custom_instruction = (system_prompt or DEFAULT_SYSTEM_PROMPT).strip()
    return (
        f"Instrucciones editoriales del sistema:\n{custom_instruction}\n\n"
        "Analiza los datos actuales del formulario"
        + (" y la imagen adjunta" if has_image else "")
        + " para sugerir valores ÚNICAMENTE para los campos que están vacíos.\n"
        f"Datos actuales ya ingresados (NO modificar): {json.dumps(existing_summary, ensure_ascii=False)}\n"
        f"Campos vacíos a completar si hay información suficiente: {', '.join(empty_fields)}\n"
        f"Grupos destinatarios válidos en UPA: {groups_desc}\n"
        "Categorías válidas: MELDUNG, ANKUENDIGUNG, VERANSTALTUNG, STELLENANGEBOT.\n"
        "Regla estricta para fin del evento: event_end es estrictamente opcional y debe corresponder a una "
        "hora en el mismo día del inicio (sistema 24h HH:mm). Si la hora de finalización no se menciona "
        "explícitamente en el texto o afiche, NO la inventes y omítela o devuélvela vacía.\n"
        "Devuelve exclusivamente un objeto JSON válido con las claves de los campos vacíos que puedas inferir "
        "(por ejemplo: title, caption, content, is_event, event_start en formato YYYY-MM-DDTHH:MM, "
        "event_date en formato DD/MM/YYYY, event_start_time en formato 24h HH:MM, "
        "event_end en formato YYYY-MM-DDTHH:MM o event_end_time en formato 24h HH:MM solo si existe explícitamente, "
        "location, target_groups como lista de códigos, category, has_registration, link_label, link_url)."
    )


def _normalize_suggested_end(start_str: str, end_str: str) -> tuple[str, str]:
    """
    Valida que el fin sugerido por IA sea una hora posterior en el mismo dia calendario.
    Devuelve (event_end_iso_local, event_end_time_24h) o ("", "") si cae en otro dia o es invalido.
    """
    clean_end = (end_str or "").strip()
    if not clean_end:
        return "", ""

    clean_start = (start_str or "").strip()
    # Extraer fecha YYYY-MM-DD y hora HH:MM del inicio si existe
    start_date_iso = ""
    start_hhmm = ""
    m_start_iso = re.match(r"^(\d{4}-\d{2}-\d{2})[T\s](\d{2}:\d{2})", clean_start)
    if m_start_iso:
        start_date_iso = m_start_iso.group(1)
        start_hhmm = m_start_iso.group(2)
    else:
        m_start_py = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})(?:[T\s,]+(\d{1,2}):(\d{2}))?", clean_start)
        if m_start_py:
            start_date_iso = f"{int(m_start_py.group(3)):04d}-{int(m_start_py.group(2)):02d}-{int(m_start_py.group(1)):02d}"
            if m_start_py.group(4) is not None:
                start_hhmm = f"{int(m_start_py.group(4)):02d}:{int(m_start_py.group(5)):02d}"

    # Caso 1: end_str es solo HH:MM (24h)
    m_time = re.match(r"^(\d{1,2}):(\d{2})(?::\d{2})?$", clean_end)
    if m_time:
        hh, mm = int(m_time.group(1)), int(m_time.group(2))
        if not (0 <= hh <= 23 and 0 <= mm <= 59):
            return "", ""
        end_hhmm = f"{hh:02d}:{mm:02d}"
        if start_hhmm and end_hhmm <= start_hhmm:
            return "", ""
        if start_date_iso:
            return f"{start_date_iso}T{end_hhmm}", end_hhmm
        return end_hhmm, end_hhmm

    # Caso 2: end_str es YYYY-MM-DDTHH:MM
    m_end_iso = re.match(r"^(\d{4}-\d{2}-\d{2})[T\s](\d{1,2}):(\d{2})", clean_end)
    if m_end_iso:
        end_date_iso = m_end_iso.group(1)
        hh, mm = int(m_end_iso.group(2)), int(m_end_iso.group(3))
        if not (0 <= hh <= 23 and 0 <= mm <= 59):
            return "", ""
        end_hhmm = f"{hh:02d}:{mm:02d}"
        if start_date_iso and end_date_iso != start_date_iso:
            return "", ""
        if start_hhmm and end_hhmm <= start_hhmm:
            return "", ""
        return f"{end_date_iso}T{end_hhmm}", end_hhmm

    # Caso 3: end_str es DD/MM/YYYY HH:MM
    m_end_py = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})[T\s,]+(\d{1,2}):(\d{2})", clean_end)
    if m_end_py:
        end_date_iso = f"{int(m_end_py.group(3)):04d}-{int(m_end_py.group(2)):02d}-{int(m_end_py.group(1)):02d}"
        hh, mm = int(m_end_py.group(4)), int(m_end_py.group(5))
        if not (0 <= hh <= 23 and 0 <= mm <= 59):
            return "", ""
        end_hhmm = f"{hh:02d}:{mm:02d}"
        if start_date_iso and end_date_iso != start_date_iso:
            return "", ""
        if start_hhmm and end_hhmm <= start_hhmm:
            return "", ""
        return f"{end_date_iso}T{end_hhmm}", end_hhmm

    return "", ""


def _filter_only_empty_fields(form_data: dict[str, Any], raw_suggestions: dict[str, Any]) -> dict[str, Any]:
    """Garantiza que solo se devuelvan valores para los campos que estaban vacios en el formulario."""
    filtered: dict[str, Any] = {}
    text_fields = (
        "title",
        "caption",
        "content",
        "location",
        "event_start",
        "event_date",
        "event_start_time",
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

    # Derivar event_date (DD/MM/YYYY) y event_start_time (HH:mm) si se sugirio event_start
    effective_start = str(form_data.get("event_start") or filtered.get("event_start") or "").strip()
    if effective_start:
        m_iso = re.match(r"^(\d{4})-(\d{2})-(\d{2})[T\s](\d{2}:\d{2})", effective_start)
        if m_iso:
            if not str(form_data.get("event_date") or "").strip() and "event_date" not in filtered:
                filtered["event_date"] = f"{m_iso.group(3)}/{m_iso.group(2)}/{m_iso.group(1)}"
            if not str(form_data.get("event_start_time") or "").strip() and "event_start_time" not in filtered:
                filtered["event_start_time"] = m_iso.group(4)

    # Validar estrictamente event_end / event_end_time (opcional, mismo dia, posterior al inicio)
    existing_end = str(form_data.get("event_end") or form_data.get("event_end_time") or "").strip()
    if not existing_end:
        raw_end_cand = str(
            raw_suggestions.get("event_end") or raw_suggestions.get("event_end_time") or ""
        ).strip()
        if raw_end_cand:
            norm_end_iso, norm_end_hhmm = _normalize_suggested_end(effective_start, raw_end_cand)
            if norm_end_iso:
                filtered["event_end"] = norm_end_iso
            if norm_end_hhmm:
                filtered["event_end_time"] = norm_end_hhmm

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
                or "event_date" in filtered
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
    system_prompt: str | None = None,
    db: Session | None = None,
) -> AutocompleteResult:
    """Envía el texto actual y la imagen opcional al modelo multimodal Gemini Flash y devuelve solo campos vacíos."""
    initial_model = resolve_active_model(db)
    if not (api_key or "").strip():
        return AutocompleteResult(
            False,
            "NO_KEY",
            f"{AUTOCOMPLETE_ERROR_PREFIX}.",
            initial_model,
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

    resolved_prompt = system_prompt if system_prompt is not None else get_system_prompt(db)
    prompt = _build_autocomplete_prompt(
        form_data=form_data,
        empty_fields=empty_fields,
        available_groups=available_groups or [],
        has_image=bool(image_bytes and image_mime_type),
        system_prompt=resolved_prompt,
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

    body: dict[str, Any] = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
        },
    }
    if resolved_prompt:
        body["systemInstruction"] = {"parts": [{"text": resolved_prompt}]}

    base_url = settings.GEMINI_API_BASE_URL.rstrip("/")
    candidate_models = build_candidate_flash_models(api_key, preferred_model=initial_model, db=db)

    response = None
    active_model = candidate_models[0] if candidate_models else initial_model
    for idx, candidate in enumerate(candidate_models):
        active_model = candidate
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
                active_model,
                {},
            )
        except httpx.HTTPError:
            return AutocompleteResult(
                False,
                "NETWORK",
                f"{AUTOCOMPLETE_ERROR_PREFIX} (error de red con Google).",
                active_model,
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
                active_model,
                {},
            )
        if response.status_code in (400, 401, 403) or "API_KEY_INVALID" in status_text:
            return AutocompleteResult(
                False,
                "INVALID_KEY",
                f"{AUTOCOMPLETE_ERROR_PREFIX}.",
                active_model,
                {},
            )
        return AutocompleteResult(
            False,
            "GOOGLE_ERROR",
            f"{AUTOCOMPLETE_ERROR_PREFIX} (código {response.status_code}).",
            active_model,
            {},
        )

    try:
        resp_json = response.json()
    except ValueError:
        return AutocompleteResult(
            False,
            "INVALID_RESPONSE",
            f"{AUTOCOMPLETE_ERROR_PREFIX} (respuesta inválida).",
            active_model,
            {},
        )

    parsed_suggestions = _extract_candidate_json(resp_json)
    if parsed_suggestions is None:
        return AutocompleteResult(
            False,
            "INVALID_RESPONSE",
            f"{AUTOCOMPLETE_ERROR_PREFIX} (formato no reconocido).",
            active_model,
            {},
        )

    save_active_model(db, active_model)
    suggestions = _filter_only_empty_fields(form_data, parsed_suggestions)
    return AutocompleteResult(True, "OK", "Campos completados por IA", active_model, suggestions)
