from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .classroom import ClassroomDeadlineResponse
from .event import EventResponse
from .post import effective_published_at, ensure_utc_datetime, extra_detail_fields, normalize_target_groups
from .user import sanitize_user_groups


class ErrorResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "detail": "Autenticacion requerida (Bearer Token ausente o invalido)",
            }
        }
    )

    detail: str = Field(..., description="Mensaje descriptivo del error para el cliente")


class FeedItemResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 1,
                "title": "Busqueda Laboral: Recepcionista",
                "caption": "Estamos buscando Recepcionista. Envia tu CV a rrhh@upa.edu.py",
                "content": "Principales funciones: Atencion al publico, recepcion y soporte administrativo.",
                "summary": "Estamos buscando Recepcionista. Envia tu CV a rrhh@upa.edu.py",
                "post_type": "INSTAGRAM",
                "is_news": True,
                "is_event": False,
                "is_pinned": False,
                "expires_at": None,
                "event_start": None,
                "event_end": None,
                "location": "",
                "has_registration": False,
                "target_groups": ["ALL"],
                "instagram_id": "insta_recepcionista_2026",
                "media_type": "IMAGE",
                "media_url": "https://upa.edu.py/static/images/recepcionista_post.png",
                "image_url": "https://upa.edu.py/static/images/recepcionista_post.png",
                "permalink": "https://www.instagram.com/p/DerQoIzjtYf/",
                "created_at": "2026-10-20T14:00:00Z",
                "published_at": "2026-10-20T14:00:00Z",
            }
        },
    )

    id: int = Field(..., description="Identificador unico de la publicacion")
    title: str = Field(..., description="Titulo principal")
    caption: str = Field(default="", description="Subtitulo o pie de publicacion (nunca nulo)")
    content: str = Field(default="", description="Contenido completo (nunca nulo)")
    summary: str = Field(default="", description="Resumen corto (nunca nulo)")
    post_type: str = Field(default="MANUAL", description="Tipo: INSTAGRAM, MANUAL, EMERGENCY_BANNER")
    is_news: bool = Field(default=True, description="Indica si pertenece a noticias")
    is_event: bool = Field(default=False, description="Indica si es un evento")
    is_pinned: bool = Field(default=False, description="Indica si esta fijado arriba")
    expires_at: datetime | None = Field(default=None, description="Fecha de expiracion opcional")
    event_start: datetime | None = Field(default=None, description="Inicio del evento opcional")
    event_end: datetime | None = Field(default=None, description="Fin del evento opcional")
    location: str = Field(default="", description="Ubicacion del evento (nunca nulo)")
    has_registration: bool = Field(default=False, description="Indica si admite registro")
    target_groups: list[str] = Field(default_factory=lambda: ["ALL"], description="Grupos destinatarios")
    instagram_id: str = Field(default="", description="ID de Instagram (cadena vacia si no aplica)")
    media_type: str = Field(default="", description="Tipo multimedia (cadena vacia si no aplica)")
    media_url: str = Field(default="", description="URL multimedia (cadena vacia si no aplica)")
    image_url: str = Field(default="", description="URL de imagen (cadena vacia si no aplica)")
    permalink: str = Field(default="", description="Enlace permanente externo (cadena vacia si no aplica)")
    detail_text: str = Field(default="", description="Texto adicional exclusivo al abrir la publicacion en la app")
    link_url: str = Field(default="", description="URL del boton de enlace opcional (cadena vacia si no aplica)")
    link_label: str = Field(default="", description="Texto del boton de enlace opcional (cadena vacia si no aplica)")
    is_registered: bool = Field(default=False, description="Indica si el usuario autenticado esta inscrito (eventos)")
    registered_count: int = Field(default=0, ge=0, description="Total de inscritos al evento")
    created_at: datetime = Field(..., description="Fecha de creacion en ISO-8601 UTC")
    published_at: datetime = Field(..., description="Fecha de publicacion en ISO-8601 UTC")

    @classmethod
    def from_orm_post(cls, post: Any, current_user_id: int | None = None) -> "FeedItemResponse":
        raw_title = (getattr(post, "title", None) or "").strip() or "Publicacion UPA"
        raw_caption = (getattr(post, "caption", None) or "").strip()
        raw_content = (getattr(post, "content", None) or "").strip()
        full_content = raw_content or raw_caption
        summary_text = (
            raw_caption if raw_caption else (full_content[:150] + "..." if len(full_content) > 150 else full_content)
        )
        img = (getattr(post, "media_url", None) or "").strip()
        created = ensure_utc_datetime(getattr(post, "created_at", None))
        published = effective_published_at(post)
        raw_expires = getattr(post, "expires_at", None)
        raw_start = getattr(post, "event_start", None)
        raw_end = getattr(post, "event_end", None)
        raw_regs = getattr(post, "registrations", None) or []
        attending = [r for r in raw_regs if (getattr(r, "status", "attending") or "attending") == "attending"]
        is_registered = current_user_id is not None and any(
            int(getattr(r, "user_id", 0) or 0) == int(current_user_id) for r in attending
        )
        return cls(
            id=int(getattr(post, "id", 0) or 0),
            title=raw_title,
            caption=raw_caption or summary_text,
            content=full_content,
            summary=summary_text,
            post_type=(getattr(post, "post_type", None) or "MANUAL").strip() or "MANUAL",
            is_news=bool(getattr(post, "is_news", True)),
            is_event=bool(getattr(post, "is_event", False)),
            is_pinned=bool(getattr(post, "is_pinned", False)),
            expires_at=ensure_utc_datetime(raw_expires) if raw_expires else None,
            event_start=ensure_utc_datetime(raw_start) if raw_start else None,
            event_end=ensure_utc_datetime(raw_end) if raw_end else None,
            location=(getattr(post, "location", None) or "").strip(),
            has_registration=bool(getattr(post, "has_registration", False)),
            target_groups=normalize_target_groups(getattr(post, "target_groups", None)),
            instagram_id=(getattr(post, "instagram_id", None) or "").strip(),
            media_type=(getattr(post, "media_type", None) or "").strip(),
            media_url=img,
            image_url=img,
            permalink=(getattr(post, "permalink", None) or "").strip(),
            **extra_detail_fields(post),
            is_registered=is_registered,
            registered_count=len(attending),
            created_at=created,
            published_at=published,
        )


class FeedResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "urgent_banners": [],
                "posts": [
                    {
                        "id": 1,
                        "title": "Busqueda Laboral: Recepcionista",
                        "caption": "Estamos buscando Recepcionista.",
                        "content": "Principales funciones: Atencion al publico.",
                        "summary": "Estamos buscando Recepcionista.",
                        "post_type": "INSTAGRAM",
                        "is_news": True,
                        "is_event": False,
                        "is_pinned": False,
                        "expires_at": None,
                        "event_start": None,
                        "event_end": None,
                        "location": "",
                        "has_registration": False,
                        "target_groups": ["ALL"],
                        "instagram_id": "insta_recepcionista_2026",
                        "media_type": "IMAGE",
                        "media_url": "https://upa.edu.py/static/images/recepcionista_post.png",
                        "image_url": "https://upa.edu.py/static/images/recepcionista_post.png",
                        "permalink": "https://www.instagram.com/p/DerQoIzjtYf/",
                        "created_at": "2026-10-20T14:00:00Z",
                        "published_at": "2026-10-20T14:00:00Z",
                    }
                ],
            }
        }
    )

    urgent_banners: list[FeedItemResponse] = Field(
        default_factory=list,
        description="Lista de avisos urgentes activos (solo usuarios autenticados)",
    )
    posts: list[FeedItemResponse] = Field(
        default_factory=list,
        description="Lista de publicaciones del campus e Instagram",
    )


class AppStateFeedItem(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": 1,
                "title": "Busqueda Laboral: Recepcionista",
                "summary": "Estamos buscando Recepcionista. Envia tu CV a rrhh@upa.edu.py",
                "content": "Principales funciones: Atencion al publico.",
                "post_type": "INSTAGRAM",
                "is_pinned": False,
                "target_groups": ["ALL"],
                "image_url": "https://upa.edu.py/static/images/recepcionista_post.png",
                "permalink": "https://www.instagram.com/p/DerQoIzjtYf/",
                "published_at": "2026-10-20T14:00:00+00:00",
            }
        }
    )

    id: int = Field(..., description="Identificador unico de la publicacion")
    title: str = Field(..., description="Titulo de la publicacion (nunca nulo)")
    summary: str = Field(default="", description="Resumen corto (nunca nulo)")
    content: str = Field(default="", description="Contenido completo (nunca nulo)")
    post_type: str = Field(default="MANUAL", description="Tipo de publicacion")
    is_pinned: bool = Field(default=False, description="Indica si esta fijado arriba")
    target_groups: list[str] = Field(default_factory=lambda: ["ALL"], description="Grupos destinatarios")
    image_url: str = Field(default="", description="URL de imagen (cadena vacia si no tiene)")
    permalink: str = Field(default="", description="Enlace permanente (cadena vacia si no tiene)")
    published_at: str = Field(..., description="Fecha de publicacion en formato ISO-8601 UTC")

    @classmethod
    def from_orm_post(cls, post: Any) -> "AppStateFeedItem":
        raw_title = (getattr(post, "title", None) or "").strip() or "Publicacion UPA"
        raw_caption = (getattr(post, "caption", None) or "").strip()
        raw_content = (getattr(post, "content", None) or "").strip()
        summary = raw_caption or raw_content
        content = raw_content or raw_caption
        published = effective_published_at(post)
        return cls(
            id=int(getattr(post, "id", 0) or 0),
            title=raw_title,
            summary=summary,
            content=content,
            post_type=(getattr(post, "post_type", None) or "MANUAL").strip() or "MANUAL",
            is_pinned=bool(getattr(post, "is_pinned", False)),
            target_groups=normalize_target_groups(getattr(post, "target_groups", None)),
            image_url=(getattr(post, "media_url", None) or "").strip(),
            permalink=(getattr(post, "permalink", None) or "").strip(),
            published_at=published.isoformat(),
        )


class AppStateUser(BaseModel):
    id: int = Field(..., description="ID unico del usuario")
    email: str = Field(..., description="Correo institucional")
    full_name: str = Field(..., description="Nombre completo")
    role: str = Field(..., description="Rol del usuario: user o admin")
    groups: list[str] = Field(default_factory=list, description="Grupos visibles segun politica de privacidad")
    google_groups: list[dict[str, str]] = Field(
        default_factory=list, description="Detalle de grupos de Google Workspace"
    )
    has_classroom_token: bool = Field(default=False, description="Indica si tiene Classroom vinculado")

    @model_validator(mode="after")
    def _enforce_privacy_and_clean_groups(self) -> "AppStateUser":
        if (self.role or "").strip().lower() != "admin":
            self.groups = []
            self.google_groups = []
        else:
            self.groups = sanitize_user_groups(self.groups)
        return self


class AppStateResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "portal": "UPA Mobile Campus Platform",
                "api_version": "1.0.0",
                "authenticated": True,
                "user": {
                    "id": 1,
                    "email": "pascal.thommen@upa.edu.py",
                    "full_name": "Pascal Thommen",
                    "role": "admin",
                    "groups": ["ALL", "Semester_4", "TIE"],
                    "google_groups": [],
                    "has_classroom_token": False,
                },
                "feed": [
                    {
                        "id": 1,
                        "title": "Busqueda Laboral: Recepcionista",
                        "summary": "Estamos buscando Recepcionista.",
                        "content": "Principales funciones: Atencion al publico.",
                        "post_type": "INSTAGRAM",
                        "is_pinned": False,
                        "target_groups": ["ALL"],
                        "image_url": "https://upa.edu.py/static/images/recepcionista_post.png",
                        "permalink": "https://www.instagram.com/p/DerQoIzjtYf/",
                        "published_at": "2026-10-20T14:00:00+00:00",
                    }
                ],
                "upcoming_events": [
                    {
                        "id": 2,
                        "title": "¿Que significa seguir siendo humanos en la era de la IA?",
                        "description": "Inteligencia artificial, decisiones, libertad y responsabilidad.",
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
                        "registered_count": 0,
                    }
                ],
                "upcoming_deadlines": [],
            }
        }
    )

    portal: str = Field(default="UPA Mobile Campus Platform", description="Nombre de la plataforma")
    api_version: str = Field(default="1.0.0", description="Version actual de la API")
    authenticated: bool = Field(default=False, description="Indica si la sesion actual esta autenticada")
    user: AppStateUser | None = Field(
        default=None, description="Datos del usuario autenticado (nulo si no se envia token)"
    )
    feed: list[AppStateFeedItem] = Field(
        default_factory=list, description="Publicaciones filtradas segun nivel de acceso y rol"
    )
    upcoming_events: list[EventResponse] = Field(
        default_factory=list,
        description="Proximos eventos del calendario ordenados cronologicamente",
    )
    upcoming_deadlines: list[ClassroomDeadlineResponse] = Field(
        default_factory=list,
        description="Proximos plazos academicos de Google Classroom ordenados cronologicamente",
    )


class HealthResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "healthy",
                "environment": "production",
                "service": "upa-app-backend",
            }
        }
    )

    status: str = Field(default="healthy", description="Estado operativo del servicio")
    environment: str = Field(..., description="Entorno de ejecucion activo")
    service: str = Field(default="upa-app-backend", description="Identificador del microservicio")


class AgendaItemResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "item_type": "EVENT",
                "id": "2",
                "title": "¿Que significa seguir siendo humanos en la era de la IA?",
                "description": "Inteligencia artificial, decisiones, libertad y responsabilidad.",
                "timestamp": "2026-10-22T11:00:00+00:00",
                "sort_key": "2026-10-22 11:00",
                "location_or_course": "Auditorio Edificio 1, Piso 1",
                "link": "",
                "is_registered": False,
                "registered_count": 0,
            }
        }
    )

    item_type: str = Field(..., description="Tipo de entrada en la agenda: EVENT o DEADLINE")
    id: str = Field(..., description="Identificador del evento o entrega")
    title: str = Field(..., description="Titulo del evento o tarea")
    description: str = Field(default="", description="Descripcion detallada (nunca nulo)")
    timestamp: str = Field(..., description="Fecha y hora de inicio o vencimiento")
    sort_key: str = Field(..., description="Clave ISO normalizada YYYY-MM-DD HH:MM para ordenamiento cronologico")
    location_or_course: str = Field(default="", description="Ubicacion del evento o nombre del curso")
    link: str = Field(default="", description="Enlace externo o de Google Classroom")
    is_registered: bool = Field(default=False, description="Indica si el usuario esta inscrito (para eventos)")
    registered_count: int = Field(default=0, ge=0, description="Total de inscritos (para eventos)")


class AgendaResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "events": [],
                "deadlines": [],
                "items": [],
            }
        }
    )

    events: list[EventResponse] = Field(
        default_factory=list,
        description="Lista de eventos de calendario ordenados cronologicamente",
    )
    deadlines: list[ClassroomDeadlineResponse] = Field(
        default_factory=list,
        description="Lista de plazos academicos de Classroom ordenados cronologicamente",
    )
    items: list[AgendaItemResponse] = Field(
        default_factory=list,
        description="Linea de tiempo consolidada de eventos y plazos en orden cronologico",
    )
