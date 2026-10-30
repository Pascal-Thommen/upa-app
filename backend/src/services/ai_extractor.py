"""Servicio multimodal de extraccion de eventos con Google Gemini Flash para publicaciones de Instagram."""

import base64
import json
import logging
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from ..config import settings
from ..models import AppSetting, AudienceGroup
from . import gemini

logger = logging.getLogger(__name__)

AI_EXTRACTION_ENABLED_SETTING = "AI_EVENT_EXTRACTION_ENABLED"


def parse_iso_datetime(raw: str | datetime | None) -> datetime | None:
    """Convierte una cadena ISO-8601 o un objeto datetime en datetime valido o devuelve None."""
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw
    clean = str(raw).strip()
    if not clean:
        return None
    if clean.endswith("Z"):
        clean = clean[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(clean)
    except ValueError:
        return None


def to_utc_datetime(raw: str | datetime | None) -> datetime | None:
    """Convierte un valor ISO-8601 o datetime a UTC con tzinfo explicita."""
    parsed = parse_iso_datetime(raw)
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def is_same_calendar_day(start_dt: datetime, end_dt: datetime) -> bool:
    """
    Regla estricta de plausibilidad: la fecha de inicio y la fecha de finalizacion
    DEBEN caer en el mismo dia calendario, y la hora de fin debe ser posterior al inicio.
    """
    if start_dt.tzinfo is not None and end_dt.tzinfo is not None:
        end_in_start_tz = end_dt.astimezone(start_dt.tzinfo)
        if start_dt.date() != end_in_start_tz.date():
            return False
        return end_dt > start_dt

    start_naive = start_dt.replace(tzinfo=None)
    end_naive = end_dt.replace(tzinfo=None)
    if start_naive.date() != end_naive.date():
        return False
    return end_naive > start_naive


def enforce_same_day_rule(start_time: str | datetime | None, end_time: str | datetime | None) -> str | None:
    """
    Valida que end_time caiga en el mismo dia calendario que start_time y sea posterior.
    Si cae en otro dia o es invalido, devuelve None.
    """
    start_dt = parse_iso_datetime(start_time)
    end_dt = parse_iso_datetime(end_time)
    if start_dt is None or end_dt is None:
        return None
    if not is_same_calendar_day(start_dt, end_dt):
        return None
    return end_time.isoformat() if isinstance(end_time, datetime) else str(end_time).strip()


class AIEventExtractionResult(BaseModel):
    """Esquema estructurado de respuesta de Google Gemini para deteccion multimodal de eventos."""

    is_event: bool = Field(default=False, description="Indica si la publicacion corresponde a un evento o actividad")
    event_title: str | None = Field(default=None, description="Titulo conciso del evento")
    start_time: str | None = Field(default=None, description="Fecha y hora de inicio en formato ISO-8601")
    end_time: str | None = Field(default=None, description="Fecha y hora de finalizacion en formato ISO-8601")
    location: str | None = Field(default=None, description="Ubicacion del evento (ej. Aula Magna, Campus UPA, Online)")
    allow_registration: bool = Field(default=False, description="Indica si el evento requiere o permite inscripcion")
    target_groups: list[str] = Field(
        default_factory=list,
        description="Etiquetas de grupos destinatarios seleccionadas de forma conservadora",
    )
    notify_push: bool = Field(default=False, description="Recomendacion conservadora de notificacion push")

    @model_validator(mode="after")
    def _validate_and_normalize(self) -> "AIEventExtractionResult":
        if self.event_title is not None:
            self.event_title = self.event_title.strip() or None
        if self.location is not None:
            self.location = self.location.strip() or None

        cleaned_groups: list[str] = []
        seen: set[str] = set()
        for raw_group in self.target_groups or []:
            val = str(raw_group or "").strip()
            if val and val.upper() not in seen:
                seen.add(val.upper())
                cleaned_groups.append(val)
        self.target_groups = cleaned_groups

        start_dt = parse_iso_datetime(self.start_time)
        if start_dt is None:
            self.start_time = None
            self.end_time = None
            if self.is_event:
                self.is_event = False
            return self

        self.start_time = str(self.start_time).strip()
        self.end_time = enforce_same_day_rule(self.start_time, self.end_time)

        if not self.is_event:
            self.end_time = None
            self.allow_registration = False
            self.notify_push = False

        return self


# Alias compatibles para importaciones externas
ExtractedEventData = AIEventExtractionResult
GeminiEventSchema = AIEventExtractionResult


def _detect_image_mime_type(data: bytes, content_type_header: str = "", url: str = "") -> str:
    header_clean = (content_type_header or "").split(";")[0].strip().lower()
    if header_clean in ("image/jpeg", "image/png", "image/webp"):
        return header_clean
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    lower_url = (url or "").lower().split("?")[0]
    if lower_url.endswith(".png"):
        return "image/png"
    if lower_url.endswith(".webp"):
        return "image/webp"
    return "image/jpeg"


def fetch_image_bytes(media_url: str | None, media_type: str | None = None) -> tuple[bytes, str] | None:
    """
    Descarga los bytes de la imagen de Instagram para el analisis multimodal con Gemini.
    Retorna (bytes, mime_type) o None si no hay imagen disponible o falla la descarga.
    """
    clean_url = (media_url or "").strip()
    if not clean_url:
        return None
    upper_type = (media_type or "").strip().upper()
    if upper_type == "VIDEO" and clean_url.lower().split("?")[0].endswith((".mp4", ".webm", ".mov")):
        return None
    if not clean_url.startswith(("http://", "https://")):
        return None

    timeout = min(float(settings.GEMINI_TIMEOUT_SECONDS or 15.0), 10.0)
    max_bytes = int(getattr(settings, "GEMINI_MAX_IMAGE_BYTES", 4 * 1024 * 1024) or 4 * 1024 * 1024)
    try:
        response = httpx.get(clean_url, timeout=timeout, follow_redirects=True)
        if response.status_code != 200 or not response.content:
            return None
        if len(response.content) > max_bytes:
            logger.warning("[AI Extractor] Imagen excede el limite (%s bytes): %s", len(response.content), clean_url)
            return None
        mime_type = _detect_image_mime_type(
            response.content,
            response.headers.get("content-type", ""),
            clean_url,
        )
        return response.content, mime_type
    except Exception as exc:
        logger.debug("[AI Extractor] No se pudo descargar la imagen %s: %s", clean_url, exc)
        return None


def is_ai_extraction_enabled(db: Session | None = None) -> tuple[bool, str]:
    """
    Determina si la extraccion con IA esta activa y devuelve (habilitado, api_key).
    Requiere AI_EVENT_EXTRACTION_ENABLED activo y una clave GEMINI_API_KEY configurada.
    """
    if not bool(getattr(settings, "AI_EVENT_EXTRACTION_ENABLED", True)):
        return False, ""

    if db is not None:
        toggle_row = db.get(AppSetting, AI_EXTRACTION_ENABLED_SETTING)
        if toggle_row is not None and (toggle_row.value or "").strip().lower() in ("false", "0", "no", "off"):
            return False, ""
        api_key, _source = gemini.resolve_api_key(db)
    else:
        api_key = (settings.GEMINI_API_KEY or "").strip()

    if not api_key:
        return False, ""
    return True, api_key


def _available_group_tags(db: Session | None) -> list[str]:
    if db is None:
        return ["estudiantes", "docentes", "staff", "egresados", "TIE", "PI", "TI"]
    try:
        rows = db.query(AudienceGroup).all()
        tags = [str(r.id).strip() for r in rows if r.id and str(r.id).strip()]
        return tags or ["estudiantes", "docentes", "staff", "egresados"]
    except Exception:
        return ["estudiantes", "docentes", "staff", "egresados"]


def _build_extraction_prompt(caption: str, group_tags: list[str], reference_date: datetime | None = None) -> str:
    ref_iso = (reference_date or datetime.now(UTC)).isoformat()
    groups_str = ", ".join(group_tags) if group_tags else "estudiantes, docentes, staff, egresados"
    return (
        "Analiza esta publicación de Instagram de la Universidad Paraguayo Alemana (UPA) "
        "combinando el texto del pie de foto y la imagen adjunta (afiche/flyer).\n"
        f"Fecha de referencia de la publicación: {ref_iso}\n"
        f"Grupos institucionales disponibles: [{groups_str}]\n\n"
        "Instrucciones estrictas:\n"
        "1. Determina si la publicación anuncia un evento, charla, taller, conferencia o actividad con fecha/hora concreta (is_event).\n"
        "2. Si es un evento, extrae event_title, start_time (ISO-8601), end_time (ISO-8601 o null), location y allow_registration.\n"
        "3. REGLA DE PLAUSIBILIDAD: start_time y end_time DEBEN estar en el mismo día calendario. "
        "Si la hora de finalización cae en otro día o no se menciona claramente, devuelve end_time como null.\n"
        "4. SELECCIÓN CONSERVADORA DE GRUPOS (target_groups): Elige etiquetas de grupo de forma extremadamente conservadora. "
        "Es preferible devolver pocos grupos o una lista vacía [] antes que seleccionar demasiados grupos.\n"
        "5. notify_push: Activa true solo si es un evento institucional importante con fecha próxima confirmada.\n"
        "6. Responde únicamente con un objeto JSON válido que cumpla el esquema solicitado.\n\n"
        f"Texto de la publicación (caption):\n{caption or '(sin texto)'}"
    )


def _extract_json_text(response_payload: dict[str, Any]) -> str:
    candidates = response_payload.get("candidates") or []
    for candidate in candidates:
        content = candidate.get("content") if isinstance(candidate, dict) else None
        parts = content.get("parts") if isinstance(content, dict) else None
        for part in parts or []:
            if isinstance(part, dict) and isinstance(part.get("text"), str) and part["text"].strip():
                raw_text = part["text"].strip()
                if raw_text.startswith("```"):
                    lines = raw_text.splitlines()
                    if lines and lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].strip().startswith("```"):
                        lines = lines[:-1]
                    raw_text = "\n".join(lines).strip()
                return raw_text
    return ""


def extract_event_from_instagram_post(
    caption: str,
    media_url: str | None = None,
    media_type: str | None = None,
    db: Session | None = None,
    *,
    image_bytes: bytes | None = None,
    image_mime_type: str = "image/jpeg",
    reference_date: datetime | None = None,
) -> AIEventExtractionResult:
    """
    Analiza multimodalmente (texto + imagen) un post de Instagram con Google Gemini Flash.
    En caso de IA desactivada, falta de clave, cuota agotada, timeout o error de red/JSON,
    devuelve de forma segura AIEventExtractionResult(is_event=False) sin interrumpir el flujo.
    """
    enabled, api_key = is_ai_extraction_enabled(db)
    if not enabled or not api_key:
        return AIEventExtractionResult(is_event=False)

    resolved_bytes = image_bytes
    resolved_mime = image_mime_type
    if resolved_bytes is None and media_url:
        fetched = fetch_image_bytes(media_url, media_type)
        if fetched is not None:
            resolved_bytes, resolved_mime = fetched

    group_tags = _available_group_tags(db)
    prompt = _build_extraction_prompt(caption, group_tags, reference_date=reference_date)

    parts: list[dict[str, Any]] = [{"text": prompt}]
    if resolved_bytes:
        parts.append(
            {
                "inline_data": {
                    "mime_type": resolved_mime or "image/jpeg",
                    "data": base64.b64encode(resolved_bytes).decode("ascii"),
                }
            }
        )

    body: dict[str, Any] = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json",
        },
    }

    base_url = settings.GEMINI_API_BASE_URL.rstrip("/")
    model = settings.GEMINI_MODEL
    candidate_models = [model]
    if "generativelanguage.googleapis.com" in base_url:
        for fallback in ("gemini-2.0-flash", "gemini-2.5-flash"):
            if fallback not in candidate_models:
                candidate_models.append(fallback)

    response: httpx.Response | None = None
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
            logger.warning("[AI Extractor] Timeout consultando Google Gemini (%s).", candidate)
            return AIEventExtractionResult(is_event=False)
        except httpx.HTTPError as exc:
            logger.warning("[AI Extractor] Error de red consultando Google Gemini: %s", exc)
            return AIEventExtractionResult(is_event=False)
        except Exception as exc:
            logger.warning("[AI Extractor] Error inesperado en llamada a Gemini: %s", exc)
            return AIEventExtractionResult(is_event=False)

        if response.status_code == 404 and idx < len(candidate_models) - 1:
            continue
        break

    if response is None or response.status_code != 200:
        if response is not None:
            logger.warning(
                "[AI Extractor] Gemini respondio HTTP %s; aplicando fallback a noticia estandar.",
                response.status_code,
            )
        return AIEventExtractionResult(is_event=False)

    try:
        payload = response.json()
        raw_json_text = _extract_json_text(payload)
        if not raw_json_text:
            logger.warning("[AI Extractor] Respuesta de Gemini sin contenido JSON utilizable.")
            return AIEventExtractionResult(is_event=False)
        parsed_data = json.loads(raw_json_text)
        if not isinstance(parsed_data, dict):
            return AIEventExtractionResult(is_event=False)
        return AIEventExtractionResult.model_validate(parsed_data)
    except Exception as exc:
        logger.warning("[AI Extractor] Respuesta JSON de Gemini invalida (%s); aplicando fallback.", exc)
        return AIEventExtractionResult(is_event=False)
