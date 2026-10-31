from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def ensure_utc_datetime(dt: datetime | None, fallback: datetime | None = None) -> datetime:
    """Garantiza que cualquier objeto datetime tenga zona horaria UTC y nunca sea nulo."""
    target = dt or fallback or datetime.now(UTC)
    if target.tzinfo is None:
        return target.replace(tzinfo=UTC)
    return target.astimezone(UTC)


# Categorias editoriales del portal web-admin
ALLOWED_CATEGORIES = {"MELDUNG", "ANKUENDIGUNG", "VERANSTALTUNG", "STELLENANGEBOT"}


def effective_published_at(post: Any) -> datetime:
    """Fecha efectiva de publicacion en UTC (usa published_at si existe, o created_at)."""
    return ensure_utc_datetime(getattr(post, "published_at", None) or getattr(post, "created_at", None))


def normalize_category(raw_category: Any) -> str | None:
    """
    Normaliza la categoria editorial a mayusculas. Devuelve None si esta vacia.
    Lanza ValueError si el valor no pertenece al catalogo permitido.
    """
    if raw_category is None:
        return None
    clean = str(raw_category).strip().upper()
    if not clean:
        return None
    if clean not in ALLOWED_CATEGORIES:
        raise ValueError("Categoria invalida. Valores permitidos: " + ", ".join(sorted(ALLOWED_CATEGORIES)) + ".")
    return clean


def normalize_target_groups(raw_groups: Any) -> list[str]:
    """Normaliza la lista de grupos destino evitando valores nulos o vacios."""
    if not isinstance(raw_groups, list):
        return ["ALL"]
    cleaned = [str(g).strip() for g in raw_groups if g is not None and str(g).strip()]
    return cleaned if cleaned else ["ALL"]


def effective_reminders(post: Any) -> list[int]:
    """Minutos previos para recordatorios configurados en la publicacion."""
    stored = getattr(post, "reminders", None)
    if isinstance(stored, list):
        return [int(m) for m in stored]
    return []


def extra_detail_fields(post: Any) -> dict[str, str]:
    """Campos adicionales de enlace para la aplicacion movil (nunca nulos)."""
    link_url = (getattr(post, "link_url", None) or "").strip()
    if not link_url and (getattr(post, "post_type", None) or "") == "INSTAGRAM":
        link_url = (getattr(post, "permalink", None) or "").strip()
    link_label = (getattr(post, "link_label", None) or "").strip()
    if link_url and not link_label and (getattr(post, "post_type", None) or "") == "INSTAGRAM":
        link_label = "Ver en Instagram"
    return {
        "link_url": link_url,
        "link_label": link_label,
    }


def user_can_access_post(user: Any, raw_groups: Any) -> bool:
    """
    Aplica el filtrado estricto basado en roles y grupos del servidor:
    - Sin usuario autenticado: solo publicaciones dirigidas a ALL o a todas las audiencias base.
    - Rol admin/editor: acceso completo a todas las publicaciones.
    - Rol user (estudiante/docente): acceso solo si la publicacion incluye ALL
      o intersecta con los grupos asignados al usuario.
    """
    post_groups = {g.upper() for g in normalize_target_groups(raw_groups)}
    if "ALL" in post_groups or {"DOCENTES", "EGRESADOS", "ESTUDIANTES", "STAFF"}.issubset(post_groups):
        return True
    if user is None:
        return False
    if getattr(user, "role", "user") in ("admin", "editor"):
        return True
    raw_user_groups = getattr(user, "groups", None) or []
    user_groups = {"ALL", "ESTUDIANTES"}
    for g in raw_user_groups:
        if g is not None and str(g).strip():
            upper_g = str(g).strip().upper()
            user_groups.add(upper_g)
            if "TIE" in upper_g:
                user_groups.add("TIE")
    return bool(post_groups & user_groups)


def matches_group_filter(raw_groups: Any, group_filter: str | None) -> bool:
    """Verifica si una publicacion coincide con el parametro de consulta group."""
    if not group_filter or not group_filter.strip():
        return True
    post_groups = {g.upper() for g in normalize_target_groups(raw_groups)}
    target = group_filter.strip().upper()
    return "ALL" in post_groups or target in post_groups


class DeleteResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "deleted",
                "id": 1,
                "detail": "Publicacion eliminada correctamente.",
            }
        }
    )

    status: str = Field(default="deleted", description="Estado de la operacion de eliminacion")
    id: int = Field(..., description="Identificador unico del recurso eliminado")
    detail: str = Field(..., description="Mensaje de confirmacion")
