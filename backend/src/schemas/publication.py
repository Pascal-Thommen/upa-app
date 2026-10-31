"""Esquemas del modelo unificado de Publicaciones (Noticia, Evento o ambos en un mismo objeto)."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .event import EventRegistrationEntry
from .post import (
    effective_published_at,
    effective_reminders,
    ensure_utc_datetime,
    extra_detail_fields,
    normalize_target_groups,
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
    media_url: str | None = Field(default=None, description="URL de imagen o cartel")
    media_type: str | None = Field(default=None, description="IMAGE, VIDEO o CAROUSEL_ALBUM")
    link_label: str | None = Field(default=None, description="Texto del boton de enlace opcional")
    link_url: str | None = Field(default=None, description="URL destino del boton de enlace opcional")
    permalink: str | None = Field(default=None, description="Enlace permanente externo")

    # Seccion Evento
    is_event: bool = Field(default=False, description="Activa la seccion de Evento en calendario")
    event_start: datetime | None = Field(default=None, description="Inicio del evento")
    event_end: datetime | None = Field(default=None, description="Fin del evento")
    location: str | None = Field(default=None, description="Lugar o enlace del evento")
    event_notify_groups: list[str] = Field(
        default_factory=list,
        description="Subconjunto de grupos que reciben recordatorios del evento",
    )
    reminders: list[int] | None = Field(
        default=None,
        description="Lista de recordatorios en minutos previos al inicio (por defecto [30] al activar evento)",
    )

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
    media_type: str | None = None
    link_label: str | None = None
    link_url: str | None = None
    permalink: str | None = None

    is_event: bool | None = None
    event_start: datetime | None = None
    event_end: datetime | None = None
    location: str | None = None
    event_notify_groups: list[str] | None = None
    reminders: list[int] | None = None

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
        img = (getattr(post, "media_url", None) or "").strip()
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
            location=(getattr(post, "location", None) or "").strip(),
            reminders=effective_reminders(post),
            instagram_id=(getattr(post, "instagram_id", None) or "").strip(),
            media_type=(getattr(post, "media_type", None) or "").strip(),
            media_url=img,
            image_url=img,
            permalink=(getattr(post, "permalink", None) or "").strip(),
            **extra_detail_fields(post),
            views_count=views_count,
            attending_count=attending_count,
            declined_count=declined_count,
            created_at=created,
            updated_at=ensure_utc_datetime(raw_updated) if raw_updated else None,
        )
