import re
from datetime import UTC, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field

from ..config import settings

ASUNCION_TZ = ZoneInfo("America/Asuncion")
_SCHEMA_UPLOAD_URL_RE = re.compile(r"^https?://[^/\s]+(/uploads/\S*)$", re.IGNORECASE)


def normalize_upload_path(raw_url: Any) -> str:
    """Normaliza URLs de archivos locales subidos a '/uploads/<filename>' (o con PUBLIC_BASE_URL si se configuro)."""
    if not raw_url:
        return ""
    clean = str(raw_url).strip()
    if not clean:
        return ""
    match = _SCHEMA_UPLOAD_URL_RE.match(clean)
    if match:
        rel_path = match.group(1)
    elif clean.startswith("/uploads/"):
        rel_path = clean
    else:
        return clean

    base = (settings.PUBLIC_BASE_URL or "").strip().rstrip("/")
    if not base:
        return rel_path
    return f"{base}{rel_path}"


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


DEFAULT_INSTAGRAM_PROFILE_URL = "https://www.instagram.com/upalemana/"
_IG_POST_URL_RE = re.compile(
    r"^(https?://(?:www\.|m\.)?instagram\.com)/(?:(?!p/|reel/|reels/|tv/|stories/|explore/|accounts/|about/|developer/|legal/|direct/)[^/?#]+/)?(p|reel|reels|tv)/([A-Za-z0-9_-]+)/?(?:[?#].*)?$",
    re.IGNORECASE,
)
_IG_SHORTCODE_RE = re.compile(r"^[A-Za-z0-9_-]{5,32}$")
_IG_RESERVED_PREFIX_RE = re.compile(r"^(?:insta_|ig_|sk_)", re.IGNORECASE)


def is_likely_instagram_shortcode(raw_code: Any) -> bool:
    """Detecta si un instagram_id corresponde a un shortcode real de Instagram (no un ID numerico ni de prueba)."""
    clean = str(raw_code or "").strip()
    if not clean or clean.isdigit() or _IG_RESERVED_PREFIX_RE.match(clean):
        return False
    return bool(_IG_SHORTCODE_RE.match(clean))


def normalize_instagram_url(
    raw_url: Any,
    *,
    instagram_id: Any = None,
    media_type: Any = None,
    is_instagram: bool = False,
    fallback_if_generic: bool = False,
) -> str:
    """
    Normaliza enlaces de Instagram eliminando el segmento de usuario intermedio (ej. /upalemana/p/CODE/ -> /p/CODE/)
    para garantizar compatibilidad con Android App Links, Universal Links de iOS y vistas web moviles.
    Si el enlace falta o es invalido en una publicacion de Instagram, reconstruye el enlace desde instagram_id
    o aplica fallback al perfil oficial @upalemana.
    """
    clean = str(raw_url or "").strip()
    if re.match(r"^(?:www\.|m\.)?instagram\.com/", clean, re.IGNORECASE):
        clean = f"https://{clean}"

    valid_url = clean if (re.match(r"^https?://", clean, re.IGNORECASE) or clean.startswith("/uploads/")) else ""
    if valid_url:
        m = _IG_POST_URL_RE.match(valid_url)
        if m:
            host = re.sub(r"^https?://m\.instagram\.com$", "https://www.instagram.com", m.group(1), flags=re.IGNORECASE)
            kind = m.group(2).lower()
            if kind == "reels":
                kind = "reel"
            shortcode = m.group(3)
            return f"{host}/{kind}/{shortcode}/"
        is_generic_profile = bool(
            re.match(r"^https?://(?:www\.|m\.)?instagram\.com/upalemana/?$", valid_url, re.IGNORECASE)
        )
        if not (fallback_if_generic and is_generic_profile):
            return valid_url

    if is_likely_instagram_shortcode(instagram_id):
        code = str(instagram_id).strip()
        is_video = bool(re.search(r"video|reel", str(media_type or ""), re.IGNORECASE))
        kind = "reel" if is_video else "p"
        return f"https://www.instagram.com/{kind}/{code}/"

    if valid_url:
        return valid_url
    if is_instagram:
        return DEFAULT_INSTAGRAM_PROFILE_URL
    return ""


def effective_permalink(post: Any) -> str:
    """Devuelve el permalink normalizado de una publicacion (con fallback seguro para Instagram)."""
    is_ig = (getattr(post, "post_type", None) or "").strip().upper() == "INSTAGRAM"
    raw_permalink = (getattr(post, "permalink", None) or "").strip()
    if is_ig or "instagram.com" in raw_permalink.lower():
        return normalize_instagram_url(
            raw_permalink or getattr(post, "link_url", None),
            instagram_id=getattr(post, "instagram_id", None),
            media_type=getattr(post, "media_type", None),
            is_instagram=is_ig,
            fallback_if_generic=True,
        )
    return raw_permalink


def extra_detail_fields(post: Any) -> dict[str, str]:
    """Campos adicionales de enlace para la aplicacion movil (nunca nulos)."""
    is_ig = (getattr(post, "post_type", None) or "").strip().upper() == "INSTAGRAM"
    ig_id = getattr(post, "instagram_id", None)
    media_type = getattr(post, "media_type", None)
    permalink = effective_permalink(post)
    link_url = normalize_upload_path(getattr(post, "link_url", None))
    if is_ig:
        if not link_url or "instagram.com" in link_url.lower():
            link_url = permalink or normalize_instagram_url(
                link_url,
                instagram_id=ig_id,
                media_type=media_type,
                is_instagram=True,
                fallback_if_generic=True,
            )
        else:
            link_url = normalize_instagram_url(
                link_url,
                instagram_id=ig_id,
                media_type=media_type,
                is_instagram=True,
            )
    elif "instagram.com" in link_url.lower():
        link_url = normalize_instagram_url(link_url, instagram_id=ig_id, media_type=media_type)
    link_label = (getattr(post, "link_label", None) or "").strip()
    if link_url and not link_label and is_ig:
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
