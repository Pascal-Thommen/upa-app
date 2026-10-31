import re
from datetime import UTC, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field

ASUNCION_TZ = ZoneInfo("America/Asuncion")


def parse_paraguay_datetime(raw: Any) -> datetime | None:
    """
    Convierte una cadena o datetime a UTC con soporte nativo para el formato paraguayo
    (DD/MM/YYYY y reloj de 24h HH:mm) ademas de ISO-8601.
    Las fechas sin zona horaria explicita se interpretan en America/Asuncion.
    """
    if raw is None:
        return None
    if isinstance(raw, datetime):
        if raw.tzinfo is None:
            return raw.replace(tzinfo=UTC)
        return raw.astimezone(UTC)

    clean = str(raw).strip()
    if not clean:
        return None

    # Formato paraguayo DD/MM/YYYY [HH:mm[:ss]] o DD-MM-YYYY [HH:mm[:ss]]
    py_match = re.match(
        r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})(?:[T\s,]+(\d{1,2}):(\d{2})(?::(\d{2}))?)?$",
        clean,
    )
    if py_match:
        day = int(py_match.group(1))
        month = int(py_match.group(2))
        year = int(py_match.group(3))
        hour = int(py_match.group(4)) if py_match.group(4) is not None else 0
        minute = int(py_match.group(5)) if py_match.group(5) is not None else 0
        second = int(py_match.group(6)) if py_match.group(6) is not None else 0
        try:
            local_dt = datetime(year, month, day, hour, minute, second, tzinfo=ASUNCION_TZ)
            return local_dt.astimezone(UTC)
        except ValueError as exc:
            raise ValueError(f"Fecha o hora invalida: {clean}") from exc

    # ISO-8601 YYYY-MM-DD[THH:mm[:ss][Z|+HH:MM]]
    iso_clean = clean[:-1] + "+00:00" if clean.endswith("Z") else clean
    try:
        parsed = datetime.fromisoformat(iso_clean)
    except ValueError as exc:
        raise ValueError(f"Formato de fecha no valido (use DD/MM/YYYY HH:mm o ISO-8601): {clean}") from exc

    if parsed.tzinfo is None:
        # Si viene en formato local sin zona horaria (ej. YYYY-MM-DDTHH:mm), se interpreta en UTC para compatibilidad ISO,
        # salvo cuando se indique explicitamente.
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def parse_24h_time(raw: Any) -> time | None:
    """Valida y extrae una hora en sistema de 24 horas (HH:mm o HH:mm:ss)."""
    if raw is None:
        return None
    if isinstance(raw, time):
        return raw.replace(tzinfo=None)
    if isinstance(raw, datetime):
        local_dt = raw.astimezone(ASUNCION_TZ) if raw.tzinfo else raw
        return time(local_dt.hour, local_dt.minute, local_dt.second)
    clean = str(raw).strip()
    if not clean:
        return None
    m = re.match(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$", clean)
    if not m:
        return None
    hh = int(m.group(1))
    mm = int(m.group(2))
    ss = int(m.group(3)) if m.group(3) is not None else 0
    if not (0 <= hh <= 23 and 0 <= mm <= 59 and 0 <= ss <= 59):
        raise ValueError("La hora debe estar en formato 24h valido (00:00 a 23:59).")
    return time(hh, mm, ss)


def format_paraguay_date(dt: datetime | None) -> str:
    """Formatea un datetime en DD/MM/YYYY en la zona horaria de Asuncion."""
    if dt is None:
        return ""
    local_dt = ensure_utc_datetime(dt).astimezone(ASUNCION_TZ)
    return local_dt.strftime("%d/%m/%Y")


def format_paraguay_time(dt: datetime | None) -> str:
    """Formatea un datetime en HH:mm (24h) en la zona horaria de Asuncion."""
    if dt is None:
        return ""
    local_dt = ensure_utc_datetime(dt).astimezone(ASUNCION_TZ)
    return local_dt.strftime("%H:%M")


def format_paraguay_datetime(dt: datetime | None) -> str:
    """Formatea un datetime en DD/MM/YYYY HH:mm (24h) en la zona horaria de Asuncion."""
    if dt is None:
        return ""
    local_dt = ensure_utc_datetime(dt).astimezone(ASUNCION_TZ)
    return local_dt.strftime("%d/%m/%Y %H:%M")


def ensure_utc_datetime(dt: datetime | None, fallback: datetime | None = None) -> datetime:
    """Garantiza que cualquier objeto datetime tenga zona horaria UTC y nunca sea nulo."""
    target = dt or fallback or datetime.now(UTC)
    if isinstance(target, str):
        parsed = parse_paraguay_datetime(target)
        if parsed is not None:
            return parsed
        target = fallback or datetime.now(UTC)
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
            if "DOCENTE" in upper_g or "PROF" in upper_g:
                user_groups.add("DOCENTES")
                user_groups.add("PROF")
            if "EGRESAD" in upper_g or "ALUMNI" in upper_g:
                user_groups.add("EGRESADOS")
            if "STAFF" in upper_g or "ADMINISTRATIV" in upper_g:
                user_groups.add("STAFF")
            if "ESTUDIANTE" in upper_g or "ALUMN" in upper_g:
                user_groups.add("ESTUDIANTES")

    raw_google_groups = getattr(user, "google_groups", None) or []
    for gg in raw_google_groups:
        if isinstance(gg, dict):
            for field_name in ("id", "name", "email"):
                val = str(gg.get(field_name) or "").strip()
                if val:
                    upper_val = val.upper()
                    user_groups.add(upper_val)
                    if "@" in upper_val:
                        user_groups.add(upper_val.split("@", 1)[0])
        elif gg is not None and str(gg).strip():
            upper_val = str(gg).strip().upper()
            user_groups.add(upper_val)
            if "@" in upper_val:
                user_groups.add(upper_val.split("@", 1)[0])

    return bool(post_groups & user_groups)


def matches_group_filter(raw_groups: Any, group_filter: str | None) -> bool:
    """Verifica si una publicacion coincide con el parametro de consulta group."""
    if not group_filter or not group_filter.strip():
        return True
    post_groups = {g.upper() for g in normalize_target_groups(raw_groups)}
    target = group_filter.strip().upper()
    if "ALL" in post_groups or {"DOCENTES", "EGRESADOS", "ESTUDIANTES", "STAFF"}.issubset(post_groups):
        return True
    return target in post_groups


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
