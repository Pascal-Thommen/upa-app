from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def ensure_utc_datetime(dt: datetime | None, fallback: datetime | None = None) -> datetime:
    """Garantiza que cualquier objeto datetime tenga zona horaria UTC y nunca sea nulo."""
    target = dt or fallback or datetime.now(UTC)
    if target.tzinfo is None:
        return target.replace(tzinfo=UTC)
    return target.astimezone(UTC)


def normalize_target_groups(raw_groups: Any) -> list[str]:
    """Normaliza la lista de grupos destino evitando valores nulos o vacios."""
    if not isinstance(raw_groups, list):
        return ["ALL"]
    cleaned = [str(g).strip() for g in raw_groups if g is not None and str(g).strip()]
    return cleaned if cleaned else ["ALL"]


def user_can_access_post(user: Any, raw_groups: Any) -> bool:
    """
    Aplica el filtrado estricto basado en roles y grupos del servidor:
    - Sin usuario autenticado: solo publicaciones dirigidas a ALL.
    - Rol admin: acceso completo a todas las publicaciones.
    - Rol user (estudiante/docente): acceso solo si la publicacion incluye ALL
      o intersecta con los grupos asignados al usuario.
    """
    post_groups = {g.upper() for g in normalize_target_groups(raw_groups)}
    if "ALL" in post_groups:
        return True
    if user is None:
        return False
    if getattr(user, "role", "user") == "admin":
        return True
    raw_user_groups = getattr(user, "groups", None) or []
    user_groups = {"ALL"} | {
        str(g).strip().upper() for g in raw_user_groups if g is not None and str(g).strip()
    }
    return bool(post_groups & user_groups)


def matches_group_filter(raw_groups: Any, group_filter: str | None) -> bool:
    """Verifica si una publicacion coincide con el parametro de consulta group."""
    if not group_filter or not group_filter.strip():
        return True
    post_groups = {g.upper() for g in normalize_target_groups(raw_groups)}
    target = group_filter.strip().upper()
    return "ALL" in post_groups or target in post_groups


class PostBase(BaseModel):
    title: str = Field(..., description="Titulo principal de la publicacion o evento")
    caption: str | None = Field(default=None, description="Resumen corto o pie de foto")
    content: str | None = Field(default=None, description="Contenido detallado de la publicacion")
    post_type: str = Field(
        default="MANUAL",
        description="Origen de la publicacion: MANUAL, INSTAGRAM o EMERGENCY_BANNER",
    )
    is_news: bool = Field(default=True, description="Indica si se muestra en la seccion de noticias")
    is_event: bool = Field(default=False, description="Indica si es un evento de calendario")
    is_pinned: bool = Field(default=False, description="Fija la publicacion en la parte superior")
    expires_at: datetime | None = Field(
        default=None, description="Fecha de expiracion automatica para avisos urgentes"
    )
    target_groups: list[str] = Field(
        default_factory=lambda: ["ALL"],
        description="Grupos destinatarios (ej. ALL, TIE, TI, PROF)",
    )

    # Campos de eventos
    event_start: datetime | None = Field(default=None, description="Fecha y hora de inicio del evento")
    event_end: datetime | None = Field(default=None, description="Fecha y hora de finalizacion del evento")
    location: str | None = Field(default=None, description="Ubicacion fisica o virtual del evento")
    has_registration: bool = Field(
        default=False, description="Habilita confirmacion de asistencia al evento"
    )
    reminder_minutes_before: int | None = Field(
        default=30, description="Minutos previos para recordatorio automatico"
    )

    # Campos de Instagram
    instagram_id: str | None = Field(default=None, description="ID unico del post en Instagram")
    media_type: str | None = Field(default=None, description="IMAGE, VIDEO o CAROUSEL_ALBUM")
    media_url: str | None = Field(default=None, description="URL del recurso multimedia")
    permalink: str | None = Field(default=None, description="Enlace permanente a la publicacion original")


class PostCreate(PostBase):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "Convocatoria de Becas de Investigacion UPA 2026",
                "caption": "Postulaciones abiertas hasta fin de mes.",
                "content": "Los estudiantes de ingenieria pueden presentar sus proyectos en secretaria academica.",
                "post_type": "MANUAL",
                "is_news": True,
                "is_event": False,
                "is_pinned": True,
                "target_groups": ["ALL", "TIE"],
            }
        }
    )


class NewsResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 1,
                "title": "Busqueda Laboral: Recepcionista",
                "summary": "Estamos buscando Recepcionista. Envia tu CV a rrhh@upa.edu.py",
                "content": "Principales funciones: Atencion a padres, estudiantes y visitantes.",
                "caption": "Estamos buscando Recepcionista. Envia tu CV a rrhh@upa.edu.py",
                "post_type": "INSTAGRAM",
                "is_pinned": False,
                "target_groups": ["ALL"],
                "instagram_id": "insta_recepcionista_2026",
                "image_url": "https://upa.edu.py/static/images/recepcionista_post.png",
                "media_url": "https://upa.edu.py/static/images/recepcionista_post.png",
                "media_type": "IMAGE",
                "permalink": "https://www.instagram.com/p/DerQoIzjtYf/",
                "created_at": "2026-10-20T14:00:00Z",
                "published_at": "2026-10-20T14:00:00Z",
            }
        },
    )

    id: int = Field(..., description="Identificador unico de la noticia")
    title: str = Field(..., description="Titulo de la noticia (nunca nulo)")
    summary: str = Field(default="", description="Resumen corto de la noticia (nunca nulo)")
    content: str = Field(default="", description="Contenido completo de la noticia (nunca nulo)")
    caption: str = Field(default="", description="Texto corto o pie de publicacion (nunca nulo)")
    post_type: str = Field(default="MANUAL", description="Tipo de publicacion: MANUAL, INSTAGRAM, EMERGENCY_BANNER")
    is_pinned: bool = Field(default=False, description="Indica si la noticia esta fijada")
    target_groups: list[str] = Field(default_factory=lambda: ["ALL"], description="Lista de grupos destino")
    instagram_id: str = Field(default="", description="Identificador de Instagram (cadena vacia si no aplica)")
    image_url: str = Field(default="", description="URL de imagen principal (cadena vacia si no tiene imagen)")
    media_url: str = Field(default="", description="URL multimedia (cadena vacia si no tiene multimedia)")
    media_type: str = Field(default="", description="Tipo de medio: IMAGE, VIDEO, CAROUSEL_ALBUM o vacio")
    permalink: str = Field(default="", description="Enlace externo permanente (cadena vacia si no aplica)")
    created_at: datetime = Field(..., description="Fecha de creacion en formato ISO-8601 UTC")
    published_at: datetime = Field(..., description="Fecha de publicacion en formato ISO-8601 UTC")

    @classmethod
    def from_orm_post(cls, post: Any) -> "NewsResponse":
        raw_title = (getattr(post, "title", None) or "").strip() or "Publicacion UPA"
        raw_caption = (getattr(post, "caption", None) or "").strip()
        raw_content = (getattr(post, "content", None) or "").strip()
        full_content = raw_content or raw_caption
        summary_text = (
            raw_caption
            if raw_caption
            else (full_content[:150] + "..." if len(full_content) > 150 else full_content)
        )
        img = (getattr(post, "media_url", None) or "").strip()
        pub_date = ensure_utc_datetime(getattr(post, "created_at", None))
        return cls(
            id=int(getattr(post, "id", 0) or 0),
            title=raw_title,
            summary=summary_text,
            content=full_content,
            caption=raw_caption or summary_text,
            post_type=(getattr(post, "post_type", None) or "MANUAL").strip() or "MANUAL",
            is_pinned=bool(getattr(post, "is_pinned", False)),
            target_groups=normalize_target_groups(getattr(post, "target_groups", None)),
            instagram_id=(getattr(post, "instagram_id", None) or "").strip(),
            image_url=img,
            media_url=img,
            media_type=(getattr(post, "media_type", None) or "").strip(),
            permalink=(getattr(post, "permalink", None) or "").strip(),
            created_at=pub_date,
            published_at=pub_date,
        )
