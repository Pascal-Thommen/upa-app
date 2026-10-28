"""Historial de auditoria (quien creo, modifico o elimino cada publicacion, grupo o rol)."""

from typing import Any

from sqlalchemy.orm import Session

from ..models import AdminAuditLog, User

AUDIT_TARGET_POST = "post"
AUDIT_TARGET_GROUP = "group"
AUDIT_TARGET_ROLE = "role"

ACTION_VERBS = {
    "CREATE": "creó",
    "UPDATE": "modificó",
    "DELETE": "eliminó",
    "ASSIGN": "autorizó",
    "REVOKE": "revocó",
    "TRIGGER": "notificó",
}

FIELD_LABELS = {
    "title": "título",
    "caption": "resumen",
    "content": "texto principal",
    "detail_text": "texto en app",
    "post_type": "tipo",
    "category": "categoría",
    "is_news": "noticia",
    "is_event": "evento",
    "is_pinned": "fijado",
    "target_groups": "grupos destino",
    "notify_groups": "notificación al publicar",
    "event_notify_groups": "grupos a recordar",
    "published_at": "fecha de publicación",
    "expires_at": "vencimiento",
    "event_start": "inicio del evento",
    "event_end": "fin del evento",
    "location": "ubicación",
    "has_registration": "inscripción",
    "reminders": "recordatorios",
    "media_url": "imagen",
    "link_url": "enlace",
    "link_label": "etiqueta de enlace",
    "name": "nombre",
    "description": "descripción",
    "google_groups": "grupos de Google",
    "emails": "correos manuales",
    "role": "rol",
    "permissions": "permisos",
}


def log_audit(
    db: Session,
    admin: User,
    action: str,
    target_type: str,
    *,
    target_id: int | None = None,
    target_key: str | None = None,
    details: dict[str, Any] | None = None,
) -> AdminAuditLog:
    """Agrega una entrada de auditoria a la sesion (el commit lo realiza el llamador, misma transaccion)."""
    entry = AdminAuditLog(
        admin_id=admin.id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        target_key=target_key,
        details=details or {},
    )
    db.add(entry)
    return entry


def action_verb(action: str) -> str:
    """Verbo legible para una accion de auditoria (CREATE_POST -> 'creó')."""
    prefix = (action or "").split("_", 1)[0].upper()
    return ACTION_VERBS.get(prefix, (action or "").lower())


def changed_fields(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    """Etiquetas legibles en espanol de los campos cuyo valor cambio entre dos instantaneas."""
    raw_keys = sorted(key for key in after if before.get(key) != after.get(key))
    return [FIELD_LABELS.get(key, key) for key in raw_keys]


def permissions_diff(before: list[str] | None, after: list[str] | None) -> str:
    """Resumen exacto de permisos otorgados/retirados, p. ej. 'permisos: +publicaciones, -historial'."""
    old, new = set(before or []), set(after or [])
    parts = [f"+{key}" for key in sorted(new - old)] + [f"-{key}" for key in sorted(old - new)]
    return "permisos: " + ", ".join(parts) if parts else ""
