from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .post import ensure_utc_datetime, normalize_target_groups


class EventResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 2,
                "title": "¿Que significa seguir siendo humanos en la era de la IA?",
                "description": "Inteligencia artificial, decisiones, libertad y responsabilidad. Disertante: Daniel Romero.",
                "summary": "holaa 👋 manana tenemos charla de 11 a 12, vayan pues",
                "event_start": "2026-10-22T11:00:00Z",
                "event_end": "2026-10-22T12:00:00Z",
                "location": "Auditorio Edificio 1, Piso 1",
                "has_registration": True,
                "is_pinned": True,
                "target_groups": ["ALL", "TIE", "Informatica"],
                "image_url": "",
                "permalink": "",
                "created_at": "2026-10-21T10:00:00Z",
                "is_registered": False,
                "registered_count": 12,
            }
        },
    )

    id: int = Field(..., description="Identificador unico del evento")
    title: str = Field(..., description="Titulo del evento academico o institucional")
    description: str = Field(default="", description="Descripcion detallada del evento (nunca nulo)")
    summary: str = Field(default="", description="Resumen corto del evento (nunca nulo)")
    event_start: datetime = Field(..., description="Fecha y hora de inicio en formato ISO-8601 UTC")
    event_end: datetime = Field(..., description="Fecha y hora de finalizacion en formato ISO-8601 UTC")
    location: str = Field(default="Campus UPA", description="Ubicacion del evento (nunca nulo)")
    has_registration: bool = Field(default=False, description="Indica si permite registro de asistencia")
    is_pinned: bool = Field(default=False, description="Indica si el evento esta destacado")
    target_groups: list[str] = Field(
        default_factory=lambda: ["ALL"], description="Grupos destinatarios del evento"
    )
    image_url: str = Field(default="", description="URL de imagen del evento (cadena vacia si no aplica)")
    permalink: str = Field(default="", description="Enlace externo del evento (cadena vacia si no aplica)")
    created_at: datetime = Field(..., description="Fecha de creacion del registro en ISO-8601 UTC")
    is_registered: bool = Field(
        default=False,
        description="Indica si el usuario actual esta inscrito en el evento",
    )
    registered_count: int = Field(
        default=0,
        ge=0,
        description="Cantidad total de participantes inscritos en el evento",
    )

    @classmethod
    def from_orm_post(cls, post: Any, current_user_id: int | None = None) -> "EventResponse":
        raw_title = (getattr(post, "title", None) or "").strip() or "Evento UPA"
        raw_caption = (getattr(post, "caption", None) or "").strip()
        raw_content = (getattr(post, "content", None) or "").strip()
        desc = raw_content or raw_caption
        summary = (
            raw_caption
            if raw_caption
            else (desc[:150] + "..." if len(desc) > 150 else desc)
        )
        created = ensure_utc_datetime(getattr(post, "created_at", None))
        start_dt = ensure_utc_datetime(getattr(post, "event_start", None), fallback=created)
        raw_end = getattr(post, "event_end", None)
        end_dt = ensure_utc_datetime(raw_end, fallback=start_dt + timedelta(hours=1))
        if end_dt < start_dt:
            end_dt = start_dt + timedelta(hours=1)
        loc = (getattr(post, "location", None) or "").strip() or "Campus UPA"
        img = (getattr(post, "media_url", None) or "").strip()

        raw_regs = getattr(post, "registrations", None) or []
        attending_regs = [
            r
            for r in raw_regs
            if (getattr(r, "status", "attending") or "attending") == "attending"
        ]
        reg_count = len(attending_regs)
        is_reg = False
        if current_user_id is not None:
            is_reg = any(
                int(getattr(r, "user_id", 0) or 0) == int(current_user_id)
                for r in attending_regs
            )

        return cls(
            id=int(getattr(post, "id", 0) or 0),
            title=raw_title,
            description=desc,
            summary=summary,
            event_start=start_dt,
            event_end=end_dt,
            location=loc,
            has_registration=bool(getattr(post, "has_registration", False)),
            is_pinned=bool(getattr(post, "is_pinned", False)),
            target_groups=normalize_target_groups(getattr(post, "target_groups", None)),
            image_url=img,
            permalink=(getattr(post, "permalink", None) or "").strip(),
            created_at=created,
            is_registered=is_reg,
            registered_count=reg_count,
        )


class EventUpdate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "Conferencia Magistral de Inteligencia Artificial 2026",
                "description": "Actualizacion de horario y disertante invitado.",
                "summary": "Charla magistral en el Auditorio Principal",
                "event_start": "2026-10-22T14:00:00Z",
                "event_end": "2026-10-22T16:00:00Z",
                "location": "Auditorio Principal Edificio 1",
                "has_registration": True,
                "is_pinned": True,
                "target_groups": ["ALL", "TIE"],
                "image_url": "",
                "permalink": "",
            }
        }
    )

    title: str | None = Field(default=None, description="Titulo actualizado del evento")
    description: str | None = Field(default=None, description="Descripcion o contenido detallado del evento")
    summary: str | None = Field(default=None, description="Resumen corto o subtitulo del evento")
    caption: str | None = Field(default=None, description="Alias compatible para resumen corto")
    content: str | None = Field(default=None, description="Alias compatible para contenido detallado")
    event_start: datetime | None = Field(default=None, description="Fecha y hora de inicio en ISO-8601 UTC")
    event_end: datetime | None = Field(default=None, description="Fecha y hora de finalizacion en ISO-8601 UTC")
    location: str | None = Field(default=None, description="Ubicacion fisica o virtual del evento")
    has_registration: bool | None = Field(default=None, description="Habilita o deshabilita inscripcion")
    is_pinned: bool | None = Field(default=None, description="Destaca el evento en la parte superior")
    is_news: bool | None = Field(default=None, description="Indica si tambien aparece en noticias")
    target_groups: list[str] | None = Field(default=None, description="Grupos destinatarios (ej. ALL, TIE)")
    image_url: str | None = Field(default=None, description="URL de imagen del evento")
    media_url: str | None = Field(default=None, description="Alias compatible para URL multimedia")
    media_type: str | None = Field(default=None, description="Tipo de medio: IMAGE, VIDEO o CAROUSEL_ALBUM")
    permalink: str | None = Field(default=None, description="Enlace externo del evento")
    reminder_minutes_before: int | None = Field(default=None, ge=0, description="Minutos previos para recordatorio")
    expires_at: datetime | None = Field(default=None, description="Fecha de expiracion opcional")


class EventCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "Conferencia Magistral de Inteligencia Artificial 2026",
                "description": "Charla abierta con disertante invitado.",
                "summary": "Charla magistral en el Auditorio Principal",
                "event_start": "2026-10-22T14:00:00Z",
                "event_end": "2026-10-22T16:00:00Z",
                "location": "Auditorio Principal Edificio 1",
                "has_registration": True,
                "is_pinned": False,
                "target_groups": ["ALL", "TIE"],
                "image_url": "",
            }
        }
    )

    title: str = Field(..., description="Titulo del evento")
    description: str | None = Field(default=None, description="Descripcion o contenido detallado del evento")
    summary: str | None = Field(default=None, description="Resumen corto o subtitulo del evento")
    caption: str | None = Field(default=None, description="Alias compatible para resumen corto")
    content: str | None = Field(default=None, description="Alias compatible para contenido detallado")
    event_start: datetime = Field(..., description="Fecha y hora de inicio en ISO-8601 UTC")
    event_end: datetime | None = Field(default=None, description="Fecha y hora de finalizacion en ISO-8601 UTC")
    location: str | None = Field(default=None, description="Ubicacion fisica o virtual del evento")
    has_registration: bool = Field(default=False, description="Habilita inscripcion (RSVP)")
    is_pinned: bool = Field(default=False, description="Destaca el evento en la parte superior")
    is_news: bool = Field(default=False, description="Indica si tambien aparece en noticias")
    target_groups: list[str] = Field(default_factory=lambda: ["ALL"], description="Grupos destinatarios")
    image_url: str | None = Field(default=None, description="URL de imagen del evento")
    media_url: str | None = Field(default=None, description="Alias compatible para URL multimedia")
    media_type: str | None = Field(default=None, description="Tipo de medio: IMAGE, VIDEO o CAROUSEL_ALBUM")
    permalink: str | None = Field(default=None, description="Enlace externo del evento")
    reminder_minutes_before: int | None = Field(default=30, ge=0, description="Minutos previos para recordatorio")
    expires_at: datetime | None = Field(default=None, description="Fecha de expiracion opcional")


class EventRegistrationEntry(BaseModel):
    user_id: int = Field(..., description="Identificador del usuario inscrito")
    full_name: str = Field(default="", description="Nombre completo del participante")
    email: str = Field(default="", description="Correo institucional del participante")
    status: str = Field(default="attending", description="Estado de la inscripcion: attending o declined")
    registered_at: datetime = Field(..., description="Fecha de inscripcion en ISO-8601 UTC")


class EventRegistrationsResponse(BaseModel):
    event_id: int = Field(..., description="Identificador del evento")
    title: str = Field(..., description="Titulo del evento")
    has_registration: bool = Field(default=False, description="Indica si el evento admite inscripcion")
    attending_count: int = Field(default=0, ge=0, description="Cantidad de participantes con estado attending")
    registrations: list[EventRegistrationEntry] = Field(default_factory=list, description="Lista de inscritos")
