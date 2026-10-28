from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AdminAuditLog, User
from ..permissions import require_permission
from ..services.audit import AUDIT_TARGET_GROUP, AUDIT_TARGET_POST, AUDIT_TARGET_ROLE, action_verb

router = APIRouter(prefix="/api/history", tags=["History"])

NUMERIC_TARGETS = {AUDIT_TARGET_POST}
KEYED_TARGETS = {AUDIT_TARGET_GROUP, AUDIT_TARGET_ROLE}
POST_TARGET_TYPES = (AUDIT_TARGET_POST, "event")


class HistoryEntry(BaseModel):
    id: int
    action: str
    verb: str = Field(..., description="Verbo legible: creó, modificó, eliminó...")
    admin_email: str
    admin_name: str
    target_id: int | None = None
    target_key: str = ""
    target_label: str = ""
    changes: list[str] = Field(default_factory=list, description="Campos modificados (solo en modificaciones)")
    created_at: datetime | None = None


def _serialize_rows(rows: list[tuple[AdminAuditLog, User]]) -> list[HistoryEntry]:
    entries: list[HistoryEntry] = []
    for log, user in rows:
        details = log.details if isinstance(log.details, dict) else {}
        changes = details.get("changes")
        target_label = str(
            details.get("title")
            or details.get("name")
            or log.target_key
            or (f"#{log.target_id}" if log.target_id is not None else "")
        )
        entries.append(
            HistoryEntry(
                id=log.id,
                action=log.action,
                verb=action_verb(log.action),
                admin_email=user.email,
                admin_name=(user.full_name or user.email),
                target_id=log.target_id,
                target_key=str(log.target_key or ""),
                target_label=target_label,
                changes=[str(c) for c in changes] if isinstance(changes, list) else [],
                created_at=log.created_at,
            )
        )
    return entries


@router.get(
    "/{entity_type}",
    response_model=list[HistoryEntry],
    summary="Historial reciente de un modulo completo (post, group o role; requiere permiso historial)",
)
def get_module_history(
    entity_type: str = Path(..., description="post, group o role"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: User = Depends(require_permission("historial")),
) -> list[HistoryEntry]:
    query = db.query(AdminAuditLog, User).join(User, User.id == AdminAuditLog.admin_id)
    if entity_type == AUDIT_TARGET_POST:
        query = query.filter(AdminAuditLog.target_type.in_(POST_TARGET_TYPES))
    elif entity_type in KEYED_TARGETS:
        query = query.filter(AdminAuditLog.target_type == entity_type)
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tipo de entidad no válido.")

    rows = query.order_by(desc(AdminAuditLog.created_at), desc(AdminAuditLog.id)).limit(limit).all()
    return _serialize_rows(rows)


@router.get(
    "/{entity_type}/{key:path}",
    response_model=list[HistoryEntry],
    summary="Historial de cambios de una publicacion, grupo o rol especifico (requiere permiso historial)",
)
def get_history(
    entity_type: str = Path(..., description="post, group o role"),
    key: str = Path(..., description="ID de la publicacion, ID del grupo o correo del rol"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: User = Depends(require_permission("historial")),
) -> list[HistoryEntry]:
    query = db.query(AdminAuditLog, User).join(User, User.id == AdminAuditLog.admin_id)
    if entity_type in NUMERIC_TARGETS:
        if not key.isdigit():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El identificador debe ser numérico.")
        query = query.filter(
            AdminAuditLog.target_type.in_(POST_TARGET_TYPES),
            AdminAuditLog.target_id == int(key),
        )
    elif entity_type in KEYED_TARGETS:
        query = query.filter(AdminAuditLog.target_type == entity_type, AdminAuditLog.target_key == key.strip().lower())
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tipo de entidad no válido.")

    rows = query.order_by(desc(AdminAuditLog.created_at), desc(AdminAuditLog.id)).limit(limit).all()
    return _serialize_rows(rows)
