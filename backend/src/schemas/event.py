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

    @classmethod
    def from_orm_post(cls, post: Any) -> "EventResponse":
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
        )
