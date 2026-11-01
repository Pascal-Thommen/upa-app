from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .post import (
    effective_reminders,
    ensure_utc_datetime,
    extra_detail_fields,
    format_paraguay_date,
    format_paraguay_datetime,
    format_paraguay_time,
    normalize_target_groups,
)


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
                "event_date": "22/10/2026",
                "event_start_time": "08:00",
                "event_end_time": "09:00",
                "event_start_formatted": "22/10/2026 08:00",
                "event_end_formatted": "22/10/2026 09:00",
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
    event_end: datetime | None = Field(default=None, description="Fecha y hora de finalizacion opcional en ISO-8601 UTC")
    event_date: str = Field(default="", description="Fecha del evento en formato paraguayo DD/MM/YYYY")
    event_start_time: str = Field(default="", description="Hora de inicio en formato 24h HH:mm (America/Asuncion)")
    event_end_time: str = Field(default="", description="Hora de finalizacion opcional en formato 24h HH:mm")
    event_start_formatted: str = Field(default="", description="Inicio del evento en formato DD/MM/YYYY HH:mm")
    event_end_formatted: str = Field(default="", description="Fin del evento en formato DD/MM/YYYY HH:mm (vacio si opcional)")
    location: str = Field(default="Campus UPA", description="Ubicacion del evento (nunca nulo)")
    has_registration: bool = Field(default=False, description="Indica si permite registro de asistencia")
    is_pinned: bool = Field(default=False, description="Indica si el evento esta destacado")
    target_groups: list[str] = Field(default_factory=lambda: ["ALL"], description="Grupos destinatarios del evento")
    image_url: str = Field(default="", description="URL de imagen del evento (cadena vacia si no aplica)")
    permalink: str = Field(default="", description="Enlace externo del evento (cadena vacia si no aplica)")
    link_url: str = Field(default="", description="URL del boton de enlace opcional (cadena vacia si no aplica)")
    link_label: str = Field(default="", description="Texto del boton de enlace opcional (cadena vacia si no aplica)")
    reminders: list[int] = Field(
        default_factory=list,
        description="Recordatorios en minutos antes del inicio (ej. [30, 1440])",
    )
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
        summary = raw_caption if raw_caption else (desc[:150] + "..." if len(desc) > 150 else desc)
        created = ensure_utc_datetime(getattr(post, "created_at", None))
        start_dt = ensure_utc_datetime(getattr(post, "event_start", None), fallback=created)
        raw_end = getattr(post, "event_end", None)
        end_dt: datetime | None = ensure_utc_datetime(raw_end) if raw_end is not None else None
        if end_dt is not None and end_dt < start_dt:
            end_dt = None
        loc = (getattr(post, "location", None) or "").strip() or "Campus UPA"
        media = (getattr(post, "media_url", None) or "").strip()
        img = (getattr(post, "image_url", None) or media).strip()

        raw_regs = getattr(post, "registrations", None) or []
        attending_regs = [r for r in raw_regs if (getattr(r, "status", "attending") or "attending") == "attending"]
        reg_count = len(attending_regs)
        is_reg = False
        if current_user_id is not None:
            is_reg = any(int(getattr(r, "user_id", 0) or 0) == int(current_user_id) for r in attending_regs)

        return cls(
            id=int(getattr(post, "id", 0) or 0),
            title=raw_title,
            description=desc,
            summary=summary,
            event_start=start_dt,
            event_end=end_dt,
            event_date=format_paraguay_date(start_dt),
            event_start_time=format_paraguay_time(start_dt),
            event_end_time=format_paraguay_time(end_dt) if end_dt is not None else "",
            event_start_formatted=format_paraguay_datetime(start_dt),
            event_end_formatted=format_paraguay_datetime(end_dt) if end_dt is not None else "",
            location=loc,
            has_registration=bool(getattr(post, "has_registration", False)),
            is_pinned=bool(getattr(post, "is_pinned", False)),
            target_groups=normalize_target_groups(getattr(post, "target_groups", None)),
            image_url=img,
            permalink=(getattr(post, "permalink", None) or "").strip(),
            **extra_detail_fields(post),
            reminders=effective_reminders(post),
            created_at=created,
            is_registered=is_reg,
            registered_count=reg_count,
        )


class EventRegistrationEntry(BaseModel):
    user_id: int = Field(..., description="Identificador del usuario inscrito")
    full_name: str = Field(default="", description="Nombre completo del participante")
    email: str = Field(default="", description="Correo institucional del participante")
    status: str = Field(default="attending", description="Estado de la inscripcion: attending o declined")
    registered_at: datetime = Field(..., description="Fecha de inscripcion en ISO-8601 UTC")
