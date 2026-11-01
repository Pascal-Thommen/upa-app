"""Esquemas del modelo unificado de Publicaciones (Noticia, Evento o ambos en un mismo objeto)."""

from datetime import UTC, datetime, time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .event import EventRegistrationEntry
from .post import (
    ASUNCION_TZ,
    effective_published_at,
    effective_reminders,
    ensure_utc_datetime,
    extra_detail_fields,
    format_paraguay_date,
    format_paraguay_datetime,
    format_paraguay_time,
    normalize_target_groups,
    parse_24h_time,
    parse_paraguay_datetime,
)


def clean_group_codes(raw_values: Any) -> list[str]:
    """Limpia una lista de codigos de grupo sin forzar 'ALL' cuando esta vacia."""
    if not isinstance(raw_values, list):
        return []
    seen: dict[str, None] = {}
    for item in raw_values:
        val = str(item or "").strip()
        if val:
            seen.setdefault(val, None)
    return list(seen)


def normalize_reminders_list(raw_values: Any) -> list[int]:
    """Normaliza una lista de minutos de recordatorio (enteros >= 0, sin duplicados, ordenados)."""
    if not isinstance(raw_values, list):
        return []
    cleaned: set[int] = set()
    for val in raw_values:
        if isinstance(val, bool):
            raise ValueError("Los minutos de recordatorio deben ser números enteros.")
        minutes = int(val)
        if minutes < 0 or minutes > 43200:
            raise ValueError("Cada recordatorio debe estar entre 0 y 43200 minutos (30 días).")
        cleaned.add(minutes)
    return sorted(cleaned)


def extract_instagram_teaser(caption: str | None) -> str:
    """Extrae las primeras dos lineas de la descripcion de Instagram como resumen corto."""
    if not caption or not caption.strip():
        return ""
    lines = [line.strip() for line in caption.strip().splitlines() if line.strip()]
    teaser = "\n".join(lines[:2])
    return teaser[:300]


def _resolve_event_datetimes(
    raw_start: Any,
    raw_end: Any,
    raw_date: Any,
    raw_start_time: Any,
    raw_end_time: Any,
) -> tuple[datetime | None, datetime | None]:
    """
    Resuelve event_start y event_end aceptando:
    - ISO-8601 completo en event_start / event_end
    - Formato paraguayo DD/MM/YYYY [HH:mm] en event_start / event_date
    - Campos separados event_date (DD/MM/YYYY o YYYY-MM-DD) + event_start_time (HH:mm) + event_end_time (HH:mm)
    - Hora simple HH:mm en event_end o event_end_time (combinada con el mismo dia de inicio)
    """
    start_dt: datetime | None = None
    if raw_start is not None and str(raw_start).strip() != "":
        start_dt = parse_paraguay_datetime(raw_start)
    elif raw_date is not None and str(raw_date).strip() != "":
        date_str = str(raw_date).strip()
        time_str = str(raw_start_time).strip() if raw_start_time is not None and str(raw_start_time).strip() else "00:00"
        t_obj = parse_24h_time(time_str)
        if t_obj is None:
            raise ValueError(f"Hora de inicio invalida (use HH:mm en 24h): {time_str}")
        base_dt = parse_paraguay_datetime(date_str)
        if base_dt is None:
            raise ValueError(f"Fecha de evento invalida (use DD/MM/YYYY): {date_str}")
        local_base = base_dt.astimezone(ASUNCION_TZ)
        local_start = datetime(
            local_base.year,
            local_base.month,
            local_base.day,
            t_obj.hour,
            t_obj.minute,
            t_obj.second,
            tzinfo=ASUNCION_TZ,
        )
        start_dt = local_start.astimezone(UTC)

    # Si se envio event_start como fecha y aparte event_start_time
    if start_dt is not None and raw_start_time is not None and str(raw_start_time).strip() != "":
        t_obj = parse_24h_time(raw_start_time)
        if t_obj is None:
            raise ValueError(f"Hora de inicio invalida (use HH:mm en 24h): {raw_start_time}")
        local_start_base = start_dt.astimezone(ASUNCION_TZ)
        start_dt = datetime(
            local_start_base.year,
            local_start_base.month,
            local_start_base.day,
            t_obj.hour,
            t_obj.minute,
            t_obj.second,
            tzinfo=ASUNCION_TZ,
        ).astimezone(UTC)

    end_candidate = raw_end if (raw_end is not None and str(raw_end).strip() != "") else raw_end_time
    if end_candidate is None or str(end_candidate).strip() == "":
        return start_dt, None

    if isinstance(end_candidate, datetime):
        end_dt = end_candidate.replace(tzinfo=UTC) if end_candidate.tzinfo is None else end_candidate.astimezone(UTC)
        return start_dt, end_dt

    clean_end = str(end_candidate).strip()
    # Verificar si es solo una hora HH:mm en 24h
    end_time_only: time | None = None
    try:
        end_time_only = parse_24h_time(clean_end)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc

    if end_time_only is not None:
        if start_dt is None:
            return None, None
        # Combinar con el mismo dia que start_dt (respetando America/Asuncion)
        local_start = start_dt.astimezone(ASUNCION_TZ)
        local_end = datetime(
            local_start.year,
            local_start.month,
            local_start.day,
            end_time_only.hour,
            end_time_only.minute,
            end_time_only.second,
            tzinfo=ASUNCION_TZ,
        )
        return start_dt, local_end.astimezone(UTC)

    end_dt = parse_paraguay_datetime(clean_end)
    return start_dt, end_dt


class PublicationWrite(BaseModel):
    """Carga util unificada para crear o editar una publicacion (Noticia, Evento o ambos)."""

    title: str = Field(..., description="Titulo principal")
    post_type: str = Field(default="MANUAL", description="MANUAL, EMERGENCY_BANNER o INSTAGRAM (solo edicion)")
    has_registration: bool = Field(default=False, description="Permite inscribirse o darse de baja (RSVP)")
    target_groups: list[str] = Field(default_factory=lambda: ["ALL"], description="Grupos destinatarios")
    published_at: datetime | None = Field(
        default=None,
        description="Fecha de publicacion programada; si es nulo se sella la hora actual al guardar",
    )

    # Seccion Post / Noticia
    is_news: bool = Field(default=True, description="Activa la publicacion como Noticia en el feed")
    notify_groups: list[str] = Field(
        default_factory=list,
        description="Subconjunto de grupos a notificar por push al publicar o guardar",
    )
    caption: str | None = Field(default=None, description="Resumen breve visible en la tarjeta")
    content: str | None = Field(default=None, description="Texto principal de la publicacion")
    category: str | None = Field(default=None, description="Categoria opcional")
    is_pinned: bool = Field(default=False, description="Fijar en la parte superior")
    expires_at: datetime | None = Field(default=None, description="Vencimiento opcional")
    media_url: str | None = Field(default=None, description="URL de imagen, video o cartel")
    image_url: str | None = Field(default=None, description="URL de miniatura o imagen de portada (poster)")
    media_type: str | None = Field(default=None, description="IMAGE, VIDEO o CAROUSEL_ALBUM")
    link_label: str | None = Field(default=None, description="Texto del boton de enlace opcional")
    link_url: str | None = Field(default=None, description="URL destino del boton de enlace opcional")
    permalink: str | None = Field(default=None, description="Enlace permanente externo")

    # Seccion Evento
    is_event: bool = Field(default=False, description="Activa la seccion de Evento en calendario")
    event_start: datetime | None = Field(default=None, description="Inicio del evento (ISO-8601 o DD/MM/YYYY HH:mm)")
    event_end: datetime | None = Field(
        default=None,
        description="Fin del evento opcional (ISO-8601, DD/MM/YYYY HH:mm o HH:mm en el mismo dia)",
    )
    event_date: str | None = Field(default=None, description="Fecha del evento opcional en formato DD/MM/YYYY")
    event_start_time: str | None = Field(default=None, description="Hora de inicio opcional en formato 24h HH:mm")
    event_end_time: str | None = Field(default=None, description="Hora de fin opcional en formato 24h HH:mm")
    location: str | None = Field(default=None, description="Lugar o enlace del evento")
    event_notify_groups: list[str] = Field(
        default_factory=list,
        description="Subconjunto de grupos que reciben recordatorios del evento",
    )
    reminders: list[int] | None = Field(
        default=None,
        description="Lista de recordatorios en minutos previos al inicio (por defecto [30] al activar evento)",
    )

    @model_validator(mode="before")
    @classmethod
    def _parse_dates_and_times(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        for dt_key in ("published_at", "expires_at"):
            val = out.get(dt_key)
            if isinstance(val, str):
                clean = val.strip()
                out[dt_key] = parse_paraguay_datetime(clean) if clean else None
        if any(k in out for k in ("event_start", "event_end", "event_date", "event_start_time", "event_end_time")):
            start_dt, end_dt = _resolve_event_datetimes(
                out.get("event_start"),
                out.get("event_end"),
                out.get("event_date"),
                out.get("event_start_time"),
                out.get("event_end_time"),
            )
            out["event_start"] = start_dt
            out["event_end"] = end_dt
        return out

    @field_validator("reminders")
    @classmethod
    def _check_reminders(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return None
        return normalize_reminders_list(value)


class PublicationUpdate(BaseModel):
    """Carga parcial o completa para actualizar una publicacion existente."""

    title: str | None = None
    post_type: str | None = None
    has_registration: bool | None = None
    target_groups: list[str] | None = None
    published_at: datetime | None = None

    is_news: bool | None = None
    notify_groups: list[str] | None = None
    caption: str | None = None
    content: str | None = None
    category: str | None = None
    is_pinned: bool | None = None
    expires_at: datetime | None = None
    media_url: str | None = None
    image_url: str | None = None
    media_type: str | None = None
    link_label: str | None = None
    link_url: str | None = None
    permalink: str | None = None

    is_event: bool | None = None
    event_start: datetime | None = None
    event_end: datetime | None = None
    event_date: str | None = None
    event_start_time: str | None = None
    event_end_time: str | None = None
    location: str | None = None
    event_notify_groups: list[str] | None = None
    reminders: list[int] | None = None

    @model_validator(mode="before")
    @classmethod
    def _parse_update_dates_and_times(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        for dt_key in ("published_at", "expires_at"):
            if dt_key in out and isinstance(out[dt_key], str):
                clean = out[dt_key].strip()
                out[dt_key] = parse_paraguay_datetime(clean) if clean else None

        has_start_input = any(k in out for k in ("event_start", "event_date", "event_start_time"))
        has_end_input = any(k in out for k in ("event_end", "event_end_time"))
        if has_start_input or has_end_input:
            raw_end_val = out.get("event_end") if "event_end" in out else out.get("event_end_time")
            # Si event_end viene como hora HH:mm pero no se envio event_start en el patch, conservar en event_end_time
            if (
                not has_start_input
                and isinstance(raw_end_val, str)
                and raw_end_val.strip()
                and parse_24h_time(raw_end_val.strip()) is not None
            ):
                out["event_end_time"] = raw_end_val.strip()
                out.pop("event_end", None)
            else:
                start_dt, end_dt = _resolve_event_datetimes(
                    out.get("event_start"),
                    out.get("event_end"),
                    out.get("event_date"),
                    out.get("event_start_time"),
                    out.get("event_end_time"),
                )
                if has_start_input:
                    out["event_start"] = start_dt
                if has_end_input:
                    out["event_end"] = end_dt
        return out

    @field_validator("reminders")
    @classmethod
    def _check_reminders(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return None
        return normalize_reminders_list(value)


class PublicationRsvpRequest(BaseModel):
    status: str = Field(..., pattern="^(attending|declined)$", description="Estado RSVP: attending o declined")


class PublicationRegistrationsResponse(BaseModel):
    publication_id: int
    title: str
    has_registration: bool = False
    attending_count: int = 0
    declined_count: int = 0
    registrations: list[EventRegistrationEntry] = Field(default_factory=list)


class PublicationResponse(BaseModel):
    """Representacion completa de una publicacion unificada con metricas reales de alcance y RSVP."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    summary: str = ""
    caption: str = ""
    content: str = ""
    post_type: str = "MANUAL"
    category: str = ""
    is_news: bool = True
    is_event: bool = False
    is_pinned: bool = False
    is_edited: bool = True
    is_ai_generated: bool = False
    status: str = "edited"
    has_registration: bool = False
    target_groups: list[str] = Field(default_factory=lambda: ["ALL"])
    notify_groups: list[str] = Field(default_factory=list)
    event_notify_groups: list[str] = Field(default_factory=list)
    published_at: datetime
    expires_at: datetime | None = None
    event_start: datetime | None = None
    event_end: datetime | None = None
    event_date: str = ""
    event_start_time: str = ""
    event_end_time: str = ""
    event_start_formatted: str = ""
    event_end_formatted: str = ""
    location: str = ""
    reminders: list[int] = Field(default_factory=list)
    instagram_id: str = ""
    media_type: str = ""
    media_url: str = ""
    image_url: str = ""
    permalink: str = ""
    link_url: str = ""
    link_label: str = ""
    views_count: int = 0
    attending_count: int = 0
    declined_count: int = 0
    created_at: datetime
    updated_at: datetime | None = None

    @classmethod
    def from_orm_post(cls, post: Any) -> "PublicationResponse":
        raw_title = (getattr(post, "title", None) or "").strip() or "Publicación UPA"
        raw_caption = (getattr(post, "caption", None) or "").strip()
        raw_content = (getattr(post, "content", None) or "").strip()
        full_content = raw_content or raw_caption
        post_type = (getattr(post, "post_type", None) or "MANUAL").strip() or "MANUAL"
        if post_type == "INSTAGRAM":
            raw_caption = extract_instagram_teaser(raw_content or raw_caption)
        summary_text = (
            raw_caption if raw_caption else (full_content[:140] + "..." if len(full_content) > 140 else full_content)
        )
        media = (getattr(post, "media_url", None) or "").strip()
        img = (getattr(post, "image_url", None) or media).strip()
        created = ensure_utc_datetime(getattr(post, "created_at", None))
        published = effective_published_at(post)
        raw_updated = getattr(post, "updated_at", None)
        raw_expires = getattr(post, "expires_at", None)
        raw_start = getattr(post, "event_start", None)
        raw_end = getattr(post, "event_end", None)

        raw_views = getattr(post, "views", None) or []
        views_count = len(raw_views)

        raw_regs = getattr(post, "registrations", None) or []
        attending_count = sum(
            1 for r in raw_regs if (getattr(r, "status", "attending") or "attending") == "attending"
        )
        declined_count = sum(1 for r in raw_regs if (getattr(r, "status", "") or "") == "declined")

        raw_is_edited = getattr(post, "is_edited", None)
        is_edited = bool(raw_is_edited) if raw_is_edited is not None else (post_type != "INSTAGRAM")
        is_ai_generated = bool(getattr(post, "is_ai_generated", False))
        status_val = "ai" if (is_ai_generated and not is_edited) else ("edited" if is_edited else "pending")

        return cls(
            id=int(getattr(post, "id", 0) or 0),
            title=raw_title,
            summary=summary_text,
            caption=raw_caption,
            content=raw_content,
            post_type=post_type,
            category=(getattr(post, "category", None) or "").strip(),
            is_news=bool(getattr(post, "is_news", True)),
            is_event=bool(getattr(post, "is_event", False)),
            is_pinned=bool(getattr(post, "is_pinned", False)),
            is_edited=is_edited,
            is_ai_generated=is_ai_generated,
            status=status_val,
            has_registration=bool(getattr(post, "has_registration", False)),
            target_groups=normalize_target_groups(getattr(post, "target_groups", None)),
            notify_groups=clean_group_codes(getattr(post, "notify_groups", None)),
            event_notify_groups=clean_group_codes(getattr(post, "event_notify_groups", None)),
            published_at=published,
            expires_at=ensure_utc_datetime(raw_expires) if raw_expires else None,
            event_start=ensure_utc_datetime(raw_start) if raw_start else None,
            event_end=ensure_utc_datetime(raw_end) if raw_end else None,
            event_date=format_paraguay_date(raw_start) if raw_start else "",
            event_start_time=format_paraguay_time(raw_start) if raw_start else "",
            event_end_time=format_paraguay_time(raw_end) if raw_end else "",
            event_start_formatted=format_paraguay_datetime(raw_start) if raw_start else "",
            event_end_formatted=format_paraguay_datetime(raw_end) if raw_end else "",
            location=(getattr(post, "location", None) or "").strip(),
            reminders=effective_reminders(post),
            instagram_id=(getattr(post, "instagram_id", None) or "").strip(),
            media_type=(getattr(post, "media_type", None) or "").strip(),
            media_url=media,
            image_url=img,
            permalink=(getattr(post, "permalink", None) or "").strip(),
            **extra_detail_fields(post),
            views_count=views_count,
            attending_count=attending_count,
            declined_count=declined_count,
            created_at=created,
            updated_at=ensure_utc_datetime(raw_updated) if raw_updated else None,
        )
