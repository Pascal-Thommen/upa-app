"""Cliente de Google Gemini (Google AI Studio): almacenamiento de la clave, prueba de conexion y autocompletado multimodal."""

import base64
import hashlib
import io
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from cryptography.fernet import Fernet, InvalidToken
from PIL import Image, ImageOps
from sqlalchemy.orm import Session

from ..config import settings
from ..models import AppSetting

GEMINI_KEY_SETTING = "GEMINI_API_KEY"
GEMINI_MODEL_SETTING = "GEMINI_ACTIVE_MODEL"
GEMINI_SYSTEM_PROMPT_SETTING = "GEMINI_SYSTEM_PROMPT"
GEMINI_SYSTEM_PROMPT_AUTOCOMPLETE_SETTING = "GEMINI_SYSTEM_PROMPT_AUTOCOMPLETE"
GEMINI_SYSTEM_PROMPT_INSTAGRAM_SETTING = "GEMINI_SYSTEM_PROMPT_INSTAGRAM"
AUTOCOMPLETE_ERROR_PREFIX = "No se pudo autocompletar: Verifique la clave de IA en Control de IA"
ENCRYPTED_KEY_PREFIX = "enc:v1:"

DEFAULT_SYSTEM_PROMPT_AUTOCOMPLETE = (
    "Eres el asistente editorial inteligente de la Universidad Paraguayo Alemana (UPA). "
    "Redacta en español formal institucional, claro y conciso. "
    "REGLA ESTRICTA CERO ALUCINACIONES (GROUNDING): Extrae y utiliza ÚNICAMENTE hechos, fechas, horas, "
    "lugares y detalles que aparezcan explícitamente en la imagen adjunta (afiche/flyer) o en el texto "
    "proporcionado. Está terminantemente PROHIBIDO inventar, suponer o extrapolar fechas, horarios "
    "(24h HH:mm), ubicaciones o descripciones de otros eventos. Si faltan fecha, hora o lugar en el "
    "material fuente, esos campos deben quedar obligatoriamente null o vacíos. Respeta el horario en "
    "formato de 24 horas (HH:mm) y la fecha en formato DD/MM/YYYY."
)
DEFAULT_SYSTEM_PROMPT_INSTAGRAM = (
    "Eres el analizador multimodal de eventos de la Universidad Paraguayo Alemana (UPA) para publicaciones e imágenes de Instagram. "
    "REGLA ESTRICTA CERO ALUCINACIONES (GROUNDING): Extrae únicamente eventos y datos (fecha, hora de inicio, "
    "hora de fin, lugar) que estén explícitamente confirmados en el texto del pie de foto o en el afiche adjunto. "
    "Si faltan fecha, hora o lugar en el material fuente, devuelve null sin inventar datos. "
    "Respeta estrictamente horarios del mismo día calendario y selecciona grupos destinatarios de forma conservadora."
)
DEFAULT_SYSTEM_PROMPT = DEFAULT_SYSTEM_PROMPT_AUTOCOMPLETE

FREE_TIER_QUOTA_RPM = 15

IMAGE_DOWNSCALE_THRESHOLD_BYTES = 1_500_000
IMAGE_MAX_EDGE_PX = 1568

# Orden de prioridad oficial de modelos gratuitos Gemini Flash en Google AI Studio (mas reciente primero)
PREFERRED_FLASH_MODELS: tuple[str, ...] = (
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-1.5-flash",
)
DEFAULT_FLASH_MODEL = "gemini-3.6-flash"

# Modelos Gemini Flash actuales en Google Generative Language API v1beta (ordenados por estabilidad y velocidad)
MODERN_FLASH_MODELS: tuple[str, ...] = (
    "gemini-3.6-flash",
    "gemini-3-flash-preview",
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-flash-lite-latest",
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-flash-latest",
)

# Modelos Gemini 3 Flash que soportan thinkingLevel MINIMAL para extraccion JSON ultrarrapida (~2.5s)
MINIMAL_THINKING_FLASH_MODELS: frozenset[str] = frozenset(
    {
        "gemini-3-flash-preview",
        "gemini-3.1-flash-lite",
        "gemini-3.1-flash-lite-preview",
    }
)
PER_CANDIDATE_AUTOCOMPLETE_TIMEOUT_SECONDS = 15.0
PER_CANDIDATE_CONNECTION_TIMEOUT_SECONDS = 8.0

# Modelos retirados para claves en Google AI Studio que deben ignorarse
RETIRED_FLASH_MODELS: frozenset[str] = frozenset(
    {
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-2.0-flash-exp",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash-preview",
    }
)

EXCLUDED_MODEL_KEYWORDS: tuple[str, ...] = (
    "image",
    "tts",
    "audio",
    "live",
    "thinking",
    "vision",
    "omni",
    "robotics",
    "computer-use",
    "transcribe",
)


def _build_fernet() -> Fernet:
    secret_material = (getattr(settings, "JWT_SECRET", "") or "upa-default-jwt-secret").encode("utf-8")
    digest = hashlib.sha256(secret_material).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_api_key(raw_key: str) -> str:
    """Cifra simetricamente la clave de API antes de persistirla en la base de datos."""
    clean = (raw_key or "").strip()
    if not clean:
        return ""
    if clean.startswith(ENCRYPTED_KEY_PREFIX):
        return clean
    token = _build_fernet().encrypt(clean.encode("utf-8")).decode("ascii")
    return f"{ENCRYPTED_KEY_PREFIX}{token}"


def decrypt_api_key(stored_value: str) -> str:
    """Descifra la clave almacenada en la base de datos (compatible con valores legados)."""
    clean = (stored_value or "").strip()
    if not clean:
        return ""
    if not clean.startswith(ENCRYPTED_KEY_PREFIX):
        return clean
    ciphertext = clean[len(ENCRYPTED_KEY_PREFIX) :].strip()
    if not ciphertext:
        return ""
    try:
        return _build_fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8").strip()
    except (InvalidToken, ValueError):
        return ""


def _is_valid_flash_model(model_name: str) -> bool:
    clean = (model_name or "").removeprefix("models/").strip().lower()
    if (
        not clean
        or clean in RETIRED_FLASH_MODELS
        or clean.startswith("gemini-2.0-")
        or clean.startswith("gemini-2.5-")
    ):
        return False
    if clean in PREFERRED_FLASH_MODELS or clean in MODERN_FLASH_MODELS:
        return True
    if not clean.startswith("gemini-") or "flash" not in clean:
        return False
    if any(keyword in clean for keyword in EXCLUDED_MODEL_KEYWORDS):
        return False
    return True


def preprocess_image_for_gemini(
    image_bytes: bytes | None,
    image_mime_type: str | None,
    *,
    max_bytes_threshold: int = IMAGE_DOWNSCALE_THRESHOLD_BYTES,
    max_edge_px: int = IMAGE_MAX_EDGE_PX,
) -> tuple[bytes | None, str | None]:
    """
    Reescala imagenes grandes (>1.5 MB o >1568px de borde maximo cuando superan el umbral)
    a un maximo de 1568px de lado para reducir latencia de transferencia y tokens en Gemini.
    Los PDFs e imagenes pequeñas se devuelven sin cambios.
    """
    if not image_bytes or not image_mime_type:
        return image_bytes, image_mime_type
    clean_mime = image_mime_type.split(";", 1)[0].strip().lower()
    if clean_mime == "application/pdf" or not clean_mime.startswith("image/"):
        return image_bytes, image_mime_type

    needs_bytes_reduction = len(image_bytes) > max_bytes_threshold
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            transposed = ImageOps.exif_transpose(img)
            img_work = transposed if transposed is not None else img
            width, height = img_work.size
            exceeds_dimensions = max(width, height) > max_edge_px
            if not needs_bytes_reduction and not exceeds_dimensions:
                return image_bytes, clean_mime

            if exceeds_dimensions:
                scale = max_edge_px / float(max(width, height))
                new_size = (
                    max(1, int(round(width * scale))),
                    max(1, int(round(height * scale))),
                )
                img_work = img_work.resize(new_size, Image.Resampling.LANCZOS)

            if img_work.mode not in ("RGB", "L"):
                if "A" in img_work.mode or img_work.mode == "P":
                    rgba = img_work.convert("RGBA")
                    bg = Image.new("RGB", rgba.size, (255, 255, 255))
                    bg.paste(rgba, mask=rgba.split()[3])
                    img_work = bg
                else:
                    img_work = img_work.convert("RGB")
            elif img_work.mode == "L":
                img_work = img_work.convert("RGB")

            buf = io.BytesIO()
            img_work.save(buf, format="JPEG", quality=85, optimize=True)
            compressed = buf.getvalue()
            if compressed and (exceeds_dimensions or len(compressed) < len(image_bytes)):
                return compressed, "image/jpeg"
    except Exception:
        return image_bytes, image_mime_type

    return image_bytes, image_mime_type


def mask_key(key: str) -> str:
    """Enmascara la clave dejando visibles solo los primeros 4 y ultimos 4 caracteres."""
    clean = (key or "").strip()
    if not clean:
        return ""
    if len(clean) <= 8:
        return "*" * len(clean)
    return f"{clean[:4]}{'*' * 8}{clean[-4:]}"


def get_stored_key(db: Session) -> str:
    row = db.get(AppSetting, GEMINI_KEY_SETTING)
    if not row or not (row.value or "").strip():
        return ""
    return decrypt_api_key(row.value)


def get_stored_model(db: Session | None) -> str:
    if db is None:
        return ""
    row = db.get(AppSetting, GEMINI_MODEL_SETTING)
    return (row.value or "").strip() if row else ""


def resolve_active_model(db: Session | None = None) -> str:
    """Devuelve el modelo Gemini Flash activo (guardado tras deteccion o predeterminado en configuracion)."""
    stored_model = get_stored_model(db)
    if _is_valid_flash_model(stored_model):
        return stored_model
    configured = (settings.GEMINI_MODEL or "").strip()
    if _is_valid_flash_model(configured):
        return configured
    return DEFAULT_FLASH_MODEL


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


def get_system_prompt_autocomplete(db: Session | None) -> str:
    """Devuelve el prompt de sistema de autocompletado configurado o el prompt institucional por defecto."""
    if db is None:
        return DEFAULT_SYSTEM_PROMPT_AUTOCOMPLETE
    row = db.get(AppSetting, GEMINI_SYSTEM_PROMPT_AUTOCOMPLETE_SETTING)
    if row is not None and (row.value or "").strip():
        return row.value.strip()
    legacy_row = db.get(AppSetting, GEMINI_SYSTEM_PROMPT_SETTING)
    if legacy_row is not None and (legacy_row.value or "").strip():
        return legacy_row.value.strip()
    return DEFAULT_SYSTEM_PROMPT_AUTOCOMPLETE


def save_system_prompt_autocomplete(db: Session, prompt_text: str, updated_by: str) -> str:
    """Guarda el prompt de sistema de autocompletado (o restaura el predeterminado si se envia vacio)."""
    clean = (prompt_text or "").strip()
    effective = clean if clean else DEFAULT_SYSTEM_PROMPT_AUTOCOMPLETE
    for key in (GEMINI_SYSTEM_PROMPT_AUTOCOMPLETE_SETTING, GEMINI_SYSTEM_PROMPT_SETTING):
        row = db.get(AppSetting, key)
        if row is None:
            db.add(AppSetting(key=key, value=effective, updated_by=updated_by))
        else:
            row.value = effective
            row.updated_by = updated_by
    db.commit()
    return effective


def get_system_prompt_instagram(db: Session | None) -> str:
    """Devuelve el prompt de sistema para analisis multimodal de Instagram o el prompt institucional por defecto."""
    if db is None:
        return DEFAULT_SYSTEM_PROMPT_INSTAGRAM
    row = db.get(AppSetting, GEMINI_SYSTEM_PROMPT_INSTAGRAM_SETTING)
    if row is not None and (row.value or "").strip():
        return row.value.strip()
    return DEFAULT_SYSTEM_PROMPT_INSTAGRAM


def save_system_prompt_instagram(db: Session, prompt_text: str, updated_by: str) -> str:
    """Guarda el prompt de sistema de Instagram (o restaura el predeterminado si se envia vacio)."""
    clean = (prompt_text or "").strip()
    effective = clean if clean else DEFAULT_SYSTEM_PROMPT_INSTAGRAM
    row = db.get(AppSetting, GEMINI_SYSTEM_PROMPT_INSTAGRAM_SETTING)
    if row is None:
        db.add(AppSetting(key=GEMINI_SYSTEM_PROMPT_INSTAGRAM_SETTING, value=effective, updated_by=updated_by))
    else:
        row.value = effective
        row.updated_by = updated_by
    db.commit()
    return effective


def get_system_prompt(db: Session | None) -> str:
    """Alias compatible hacia el prompt de autocompletado."""
    return get_system_prompt_autocomplete(db)


def save_system_prompt(db: Session, prompt_text: str, updated_by: str) -> str:
    """Alias compatible hacia el guardado del prompt de autocompletado."""
    return save_system_prompt_autocomplete(db, prompt_text, updated_by)


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
    encrypted_value = encrypt_api_key(key)
    row = db.get(AppSetting, GEMINI_KEY_SETTING)
    if row is None:
        db.add(AppSetting(key=GEMINI_KEY_SETTING, value=encrypted_value, updated_by=updated_by))
    else:
        row.value = encrypted_value
        row.updated_by = updated_by
    db.commit()


def _parse_flash_model_sort_key(model_id: str) -> tuple[int, int, int, int, int, str]:
    """
    Ordena los modelos Gemini Flash gratuitos priorizando los modelos estables rapidos verificados
    en Google AI Studio y dejando variantes pesadas o experimentales detras.
    """
    clean = model_id.removeprefix("models/").strip().lower()
    if clean in MODERN_FLASH_MODELS:
        priority_rank = len(MODERN_FLASH_MODELS) - MODERN_FLASH_MODELS.index(clean)
        return (1, priority_rank, 0, 0, 0, clean)
    m = re.match(r"^gemini-(\d+)(?:\.(\d+))?-flash(.*)$", clean)
    if not m:
        return (0, 0, 0, 0, 0, clean)
    major = int(m.group(1))
    minor = int(m.group(2) or 0)
    suffix = (m.group(3) or "").strip()
    is_exact_base = 2 if suffix in ("", "-latest") else (1 if not ("lite" in suffix or "8b" in suffix) else 0)
    is_stable = 1 if ("exp" not in suffix and "preview" not in suffix) else 0
    return (0, major, minor, is_exact_base, is_stable, clean)


def discover_available_flash_models(api_key: str, base_url: str | None = None) -> list[str]:
    """
    Consulta el catalogo de modelos disponibles para la clave en Google AI Studio (GET /v1beta/models)
    y devuelve los modelos oficiales Gemini Flash compatibles con generateContent.
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
        if not _is_valid_flash_model(name):
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
    1. Si el servidor expone /v1beta/models, prioriza el Flash oficial mas reciente descubierto.
    2. Añade el modelo preferido/configurado y la cadena de respaldo oficial (2.0/1.5 y 3.x Flash).
    """
    base_url = settings.GEMINI_API_BASE_URL.rstrip("/")
    candidates: list[str] = []

    discovered = discover_available_flash_models(api_key, base_url=base_url)
    for m in discovered:
        if _is_valid_flash_model(m) and m not in candidates:
            candidates.append(m)

    initial = (preferred_model or resolve_active_model(db) or settings.GEMINI_MODEL or "").strip()
    if _is_valid_flash_model(initial) and initial not in candidates:
        candidates.append(initial)

    for fallback in PREFERRED_FLASH_MODELS:
        if fallback not in candidates:
            candidates.append(fallback)

    for modern in MODERN_FLASH_MODELS:
        if modern not in candidates:
            candidates.append(modern)

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

    raw_timeout = float(settings.GEMINI_TIMEOUT_SECONDS or 15.0)
    per_candidate_timeout = (
        min(raw_timeout, PER_CANDIDATE_CONNECTION_TIMEOUT_SECONDS)
        if len(candidate_models) > 1
        else raw_timeout
    )
    deadline = time.monotonic() + raw_timeout

    response = None
    active_model = candidate_models[0] if candidate_models else initial_model
    for idx, candidate in enumerate(candidate_models):
        active_model = candidate
        url = f"{base_url}/v1beta/models/{candidate}:generateContent"
        remaining = deadline - time.monotonic()
        if idx > 0 and remaining <= 0:
            return ConnectionResult(
                False, "TIMEOUT", "Error de red con Google: tiempo de espera agotado.", active_model
            )
        attempt_timeout = min(per_candidate_timeout, max(0.05, remaining)) if idx > 0 else per_candidate_timeout
        try:
            response = httpx.post(
                url,
                json=body,
                headers={"x-goog-api-key": api_key.strip()},
                timeout=attempt_timeout,
            )
        except httpx.TimeoutException:
            if idx < len(candidate_models) - 1 and (deadline - time.monotonic()) > 0.05:
                continue
            return ConnectionResult(
                False, "TIMEOUT", "Error de red con Google: tiempo de espera agotado.", active_model
            )
        except httpx.HTTPError:
            if idx < len(candidate_models) - 1 and (deadline - time.monotonic()) > 0.05:
                continue
            return ConnectionResult(
                False, "NETWORK", "Error de red con Google: no se pudo establecer la conexión.", active_model
            )
        except Exception:
            return ConnectionResult(
                False, "INVALID_KEY", "Clave de API inválida o expirada.", active_model
            )

        if response.status_code in (404, 429, 503) and idx < len(candidate_models) - 1:
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
    raw_content = first.get("content")
    content = raw_content if isinstance(raw_content, dict) else {}
    raw_parts = content.get("parts")
    parts = raw_parts if isinstance(raw_parts, list) else []
    raw_text = ""
    for part in parts:
        if isinstance(part, dict) and isinstance(part.get("text"), str) and not part.get("thought"):
            raw_text += part["text"]
    if not raw_text.strip():
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


_TEMPORAL_GROUNDING_RE = re.compile(
    r"(\d|"
    r"\b(?:hoy|mañana|manana|lunes|martes|miércoles|miercoles|jueves|viernes|sábado|sabado|domingo|"
    r"enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre|"
    r"próximo|proximo|mediodía|mediodia)\b)",
    re.IGNORECASE,
)


def has_temporal_grounding(text: str | None) -> bool:
    """Verifica si el texto fuente contiene referencias explicitas de fecha, hora o numeros."""
    clean = (text or "").strip()
    if not clean:
        return False
    return bool(_TEMPORAL_GROUNDING_RE.search(clean))


def has_autocomplete_source_context(form_data: dict[str, Any], *, has_image: bool = False) -> bool:
    """
    Determina si la solicitud de autocompletado cuenta con material fuente suficiente
    (imagen/afiche adjunto o texto base en caption/content) mas alla de un simple titulo.
    """
    if has_image:
        return True
    if str(form_data.get("media_url") or form_data.get("image_url") or form_data.get("image_base64") or "").strip():
        return True
    if str(form_data.get("caption") or "").strip():
        return True
    if str(form_data.get("content") or "").strip():
        return True
    return False


def _build_autocomplete_prompt(
    form_data: dict[str, Any],
    empty_fields: list[str],
    available_groups: list[dict[str, str]],
    has_image: bool,
    system_prompt: str | None = None,
) -> str:
    groups_desc = ", ".join(f"{g.get('id')}: {g.get('name')}" for g in available_groups if g.get("id"))
    if not groups_desc:
        groups_desc = "PI: Ingeniería Industrial, TI: Tecnologías de la Información, PROF: Cuerpo docente"

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

    active_system_prompt = (system_prompt or "").strip() or DEFAULT_SYSTEM_PROMPT
    has_text_body = bool(str(form_data.get("caption") or "").strip() or str(form_data.get("content") or "").strip())

    if has_image:
        workflow_instruction = (
            "MODO AFICHE/IMAGEN ADJUNTA: Extrae prioritariamente los hechos visibles en la imagen adjunta "
            "(título, fecha, hora de inicio, hora de fin si figura en el mismo día, lugar y detalles del evento) "
            "combinándolos únicamente con los datos ya presentes en el formulario.\n"
        )
    elif not has_text_body:
        workflow_instruction = (
            "ADVERTENCIA DE CONTEXTO INSUFICIENTE (SOLO TÍTULO SIN IMAGEN NI TEXTO): "
            "No se adjuntó ninguna imagen ni texto descriptivo (caption/content). "
            "Está ESTRICTAMENTE PROHIBIDO generar un evento de calendario (is_event debe ser false), "
            "inventar fechas u horas (event_start, event_date, event_start_time, event_end, event_end_time deben ser null) "
            "o inventar ubicaciones (location: null) o textos descriptivos libres (caption: null, content: null).\n"
        )
    else:
        workflow_instruction = (
            "MODO TEXTO SIN IMAGEN: Extrae únicamente hechos explícitos presentes en el texto ingresado. "
            "Si el texto no menciona explícitamente una fecha, hora o lugar, deja esos campos en null o vacíos.\n"
        )

    return (
        f"{active_system_prompt}\n"
        "Analiza los datos actuales del formulario"
        + (" y la imagen adjunta (afiche/flyer)" if has_image else "")
        + " para sugerir valores ÚNICAMENTE para los campos que están vacíos.\n"
        + workflow_instruction
        + "REGLAS ESTRICTAS DE GROUNDING (CERO ALUCINACIONES):\n"
        "- Solo pueden asumirse hechos que estén explícitamente escritos en la imagen (flyer) o en el texto entregado.\n"
        "- Si faltan fecha, hora de inicio, hora de finalización o lugar en el material fuente, esos campos DEBEN quedar null o vacíos. Está prohibido inventar datos de eventos.\n"
        f"Datos actuales ya ingresados (NO modificar): {json.dumps(existing_summary, ensure_ascii=False)}\n"
        f"Campos vacíos a completar si hay información explícita suficiente: {', '.join(empty_fields)}\n"
        f"Grupos destinatarios válidos en UPA: {groups_desc}\n"
        "Categorías válidas: MELDUNG, ANKUENDIGUNG, VERANSTALTUNG, STELLENANGEBOT.\n"
        "Regla estricta para fin del evento: event_end es estrictamente opcional y debe corresponder a una "
        "hora en el mismo día del inicio (sistema 24h HH:mm). Si la hora de finalización no se menciona "
        "explícitamente en el texto o afiche, NO la inventes y omítela o devuélvela vacía.\n"
        "Si se detecta un evento (is_event: true), activa siempre has_registration: true por defecto.\n"
        "Devuelve exclusivamente un objeto JSON válido con las claves de los campos vacíos que puedas inferir "
        "(por ejemplo: title, caption, content, is_event, event_start en formato YYYY-MM-DDTHH:MM, "
        "event_date en formato DD/MM/YYYY, event_start_time en formato 24h HH:MM, "
        "event_end en formato YYYY-MM-DDTHH:MM o event_end_time en formato 24h HH:MM solo si se menciona explícitamente la hora de finalización, "
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


def _filter_only_empty_fields(
    form_data: dict[str, Any],
    raw_suggestions: dict[str, Any],
    *,
    has_image: bool | None = None,
) -> dict[str, Any]:
    """
    Garantiza que solo se devuelvan valores para los campos que estaban vacios en el formulario
    y aplica las barreras Cero Alucinaciones cuando falta contexto fuente (imagen o texto base).
    """
    effective_has_image = (
        bool(has_image)
        if has_image is not None
        else bool(
            str(
                form_data.get("media_url")
                or form_data.get("image_url")
                or form_data.get("image_base64")
                or ""
            ).strip()
        )
    )
    has_source_context = has_autocomplete_source_context(form_data, has_image=effective_has_image)
    title_val = str(form_data.get("title") or "").strip()
    caption_val = str(form_data.get("caption") or "").strip()
    content_val = str(form_data.get("content") or "").strip()
    post_type = str(form_data.get("post_type") or "MANUAL").strip().upper()

    # Si no hay imagen ni texto alguno (ni siquiera titulo), no hay nada que inferir
    if not has_source_context and not title_val:
        return {}

    # Si solo se ingreso un titulo sin imagen ni texto (caption/content), bloquear cualquier
    # evento de calendario inventado, fechas/horas, ubicaciones o textos descriptivos libres
    if not has_source_context:
        filtered_minimal: dict[str, Any] = {}
        existing_cat = str(form_data.get("category") or "").strip()
        cand_cat = raw_suggestions.get("category")
        if not existing_cat and isinstance(cand_cat, str) and cand_cat.strip():
            filtered_minimal["category"] = cand_cat.strip()
        existing_groups = _clean_group_list(form_data.get("target_groups"))
        if not existing_groups:
            suggested_groups = _clean_group_list(raw_suggestions.get("target_groups"))
            if suggested_groups:
                filtered_minimal["target_groups"] = suggested_groups
        return filtered_minimal

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
    readonly_instagram_fields = {"caption", "content", "link_label", "link_url"}
    for field_name in text_fields:
        if post_type == "INSTAGRAM" and field_name in readonly_instagram_fields:
            continue
        existing_val = str(form_data.get(field_name) or "").strip()
        if existing_val:
            continue
        candidate_val = raw_suggestions.get(field_name)
        if isinstance(candidate_val, str) and candidate_val.strip():
            filtered[field_name] = candidate_val.strip()

    # Sin imagen adjunta, exigir anclaje temporal explicito en el texto antes de aceptar fechas/horas
    combined_source_text = f"{title_val} {caption_val} {content_val}".strip()
    has_existing_temporal = bool(
        str(form_data.get("event_start") or form_data.get("event_date") or "").strip()
    )
    if not effective_has_image and not has_existing_temporal and not has_temporal_grounding(combined_source_text):
        for temporal_key in ("event_start", "event_date", "event_start_time"):
            filtered.pop(temporal_key, None)

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
    if not existing_end and effective_start:
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

    if post_type != "EMERGENCY_BANNER":
        if not form_data.get("is_event"):
            has_grounded_event_date = bool(
                effective_start
                or filtered.get("event_start")
                or filtered.get("event_date")
                or str(form_data.get("event_date") or "").strip()
            )
            if has_grounded_event_date and (
                raw_suggestions.get("is_event") is True
                or "event_start" in filtered
                or "event_date" in filtered
                or "location" in filtered
            ):
                filtered["is_event"] = True

    if not form_data.get("has_registration") and (
        form_data.get("is_event") or filtered.get("is_event") is True
    ):
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

    resolved_prompt = system_prompt if system_prompt is not None else get_system_prompt_autocomplete(db)
    prompt = _build_autocomplete_prompt(
        form_data=form_data,
        empty_fields=empty_fields,
        available_groups=available_groups or [],
        has_image=bool(image_bytes and image_mime_type),
        system_prompt=resolved_prompt,
    )

    parts: list[dict[str, Any]] = [{"text": prompt}]
    if image_bytes and image_mime_type:
        processed_bytes, processed_mime = preprocess_image_for_gemini(image_bytes, image_mime_type)
        parts.append(
            {
                "inline_data": {
                    "mime_type": processed_mime or image_mime_type,
                    "data": base64.b64encode(processed_bytes or image_bytes).decode("ascii"),
                }
            }
        )

    body: dict[str, Any] = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "temperature": 0.0,
            "responseMimeType": "application/json",
        },
    }
    if resolved_prompt:
        body["systemInstruction"] = {"parts": [{"text": resolved_prompt}]}

    base_url = settings.GEMINI_API_BASE_URL.rstrip("/")
    candidate_models = build_candidate_flash_models(api_key, preferred_model=initial_model, db=db)
    stored_model = get_stored_model(db)
    if _is_valid_flash_model(stored_model):
        candidate_models = [stored_model] + [m for m in candidate_models if m != stored_model]

    raw_timeout = float(settings.GEMINI_TIMEOUT_SECONDS or 45.0)
    per_candidate_timeout = (
        min(raw_timeout, PER_CANDIDATE_AUTOCOMPLETE_TIMEOUT_SECONDS)
        if len(candidate_models) > 1
        else raw_timeout
    )
    deadline = time.monotonic() + raw_timeout

    response = None
    parsed_suggestions: dict[str, Any] | None = None
    active_model = candidate_models[0] if candidate_models else initial_model
    for idx, candidate in enumerate(candidate_models):
        active_model = candidate
        url = f"{base_url}/v1beta/models/{candidate}:generateContent"
        remaining = deadline - time.monotonic()
        if idx > 0 and remaining <= 0:
            return AutocompleteResult(
                False,
                "TIMEOUT",
                f"{AUTOCOMPLETE_ERROR_PREFIX} (tiempo de espera agotado).",
                active_model,
                {},
            )
        attempt_timeout = min(per_candidate_timeout, max(0.05, remaining)) if idx > 0 else per_candidate_timeout
        candidate_body = dict(body)
        if candidate in MINIMAL_THINKING_FLASH_MODELS:
            candidate_body["generationConfig"] = {
                **body["generationConfig"],
                "thinkingConfig": {"thinkingLevel": "MINIMAL"},
            }
        try:
            response = httpx.post(
                url,
                json=candidate_body,
                headers={"x-goog-api-key": api_key.strip()},
                timeout=attempt_timeout,
            )
            if response.status_code == 400 and "thinkingConfig" in candidate_body.get("generationConfig", {}):
                response = httpx.post(
                    url,
                    json=body,
                    headers={"x-goog-api-key": api_key.strip()},
                    timeout=attempt_timeout,
                )
        except httpx.TimeoutException:
            if idx < len(candidate_models) - 1 and (deadline - time.monotonic()) > 0.05:
                continue
            return AutocompleteResult(
                False,
                "TIMEOUT",
                f"{AUTOCOMPLETE_ERROR_PREFIX} (tiempo de espera agotado).",
                active_model,
                {},
            )
        except httpx.HTTPError:
            if idx < len(candidate_models) - 1 and (deadline - time.monotonic()) > 0.05:
                continue
            return AutocompleteResult(
                False,
                "NETWORK",
                f"{AUTOCOMPLETE_ERROR_PREFIX} (error de red con Google).",
                active_model,
                {},
            )
        except Exception:
            return AutocompleteResult(
                False,
                "INVALID_KEY",
                f"{AUTOCOMPLETE_ERROR_PREFIX}.",
                active_model,
                {},
            )

        if response.status_code in (404, 429, 503) and idx < len(candidate_models) - 1:
            continue
        if response.status_code == 200:
            try:
                resp_json = response.json()
                parsed_suggestions = _extract_candidate_json(resp_json)
            except ValueError:
                parsed_suggestions = None
            if parsed_suggestions is None and idx < len(candidate_models) - 1:
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
    suggestions = _filter_only_empty_fields(
        form_data,
        parsed_suggestions,
        has_image=bool(image_bytes and image_mime_type),
    )
    return AutocompleteResult(True, "OK", "Campos completados por IA", active_model, suggestions)
