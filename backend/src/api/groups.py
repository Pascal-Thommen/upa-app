import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..auth import require_editor
from ..database import get_db
from ..models import AudienceGroup, User
from ..permissions import effective_permissions, require_permission
from ..schemas.group import (
    EMAIL_PATTERN,
    AudienceGroupCreate,
    AudienceGroupResponse,
    AudienceGroupUpdate,
    WorkspaceGroupItem,
    WorkspaceGroupsResponse,
)
from ..services.audit import AUDIT_TARGET_GROUP, changed_fields, log_audit
from ..services.google_groups import WorkspaceDirectoryUnavailable, list_workspace_groups

router = APIRouter(prefix="/api/groups", tags=["Groups"])


def sanitize_group_id(raw: str) -> str:
    cleaned = re.sub(r"[^a-z0-9_]", "_", raw.lower().strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or "grupo_custom"


def _snapshot(group: AudienceGroup) -> dict:
    return {
        "name": group.name,
        "description": group.description or "",
        "google_groups": list(group.google_groups or []),
        "emails": list(group.emails or []),
    }


@router.get("", response_model=list[AudienceGroupResponse], summary="Listar grupos de audiencia institucionales")
def list_groups(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_editor),
) -> list[AudienceGroupResponse]:
    groups = sorted(
        db.query(AudienceGroup).all(),
        key=lambda g: ((g.name or "").strip().lower(), (g.id or "").lower()),
    )
    can_view_emails = "grupos" in effective_permissions(db, current_user)
    return [
        AudienceGroupResponse.model_validate(g).model_copy(
            update={"emails": list(g.emails or []) if can_view_emails else []}
        )
        for g in groups
    ]


@router.get(
    "/google-workspace",
    response_model=WorkspaceGroupsResponse,
    summary="Grupos de Google Workspace disponibles para vincular a un grupo",
)
async def list_google_workspace_groups(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("grupos")),
) -> WorkspaceGroupsResponse:
    """
    Lista los grupos reales del dominio desde la Google Directory API. Si Google Directory no esta disponible
    (sin credenciales, red o permisos) devuelve los grupos ya sincronizados en usuarios y grupos locales.
    """
    try:
        groups = await list_workspace_groups()
        return WorkspaceGroupsResponse(
            source="directory",
            groups=[WorkspaceGroupItem(**g) for g in groups],
        )
    except WorkspaceDirectoryUnavailable as exc:
        known: dict[str, WorkspaceGroupItem] = {}
        for (raw_groups,) in db.query(User.google_groups).all():
            for item in raw_groups or []:
                if not isinstance(item, dict):
                    continue
                email = str(item.get("email") or "").strip().lower()
                if email and email not in known:
                    known[email] = WorkspaceGroupItem(
                        id=str(item.get("id") or ""),
                        name=str(item.get("name") or email),
                        email=email,
                        description=str(item.get("description") or ""),
                    )

        for grp in db.query(AudienceGroup).all():
            for email_raw in list(grp.google_groups or []):
                email = str(email_raw or "").strip().lower()
                if email and EMAIL_PATTERN.match(email) and email not in known:
                    known[email] = WorkspaceGroupItem(
                        id=grp.id,
                        name=f"{grp.name} ({email})",
                        email=email,
                        description=grp.description or "",
                    )

        return WorkspaceGroupsResponse(
            source="known_users",
            message=f"{exc} Se muestran los grupos ya registrados; también puede agregar correos manualmente.",
            groups=sorted(known.values(), key=lambda g: (g.name.lower(), g.email.lower())),
        )


@router.post(
    "",
    response_model=AudienceGroupResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear nuevo grupo de audiencia",
)
def create_group(
    payload: AudienceGroupCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("grupos")),
) -> AudienceGroupResponse:
    target_id = sanitize_group_id(payload.id or payload.name)
    existing = db.query(AudienceGroup).filter(AudienceGroup.id == target_id).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"El identificador de grupo '{target_id}' ya existe.",
        )

    new_group = AudienceGroup(
        id=target_id,
        name=payload.name.strip(),
        description=payload.description.strip() if payload.description else None,
        google_groups=list(payload.google_groups),
        emails=payload.emails,
    )
    db.add(new_group)
    log_audit(
        db,
        current_user,
        "CREATE_GROUP",
        AUDIT_TARGET_GROUP,
        target_key=target_id,
        details={"name": new_group.name},
    )
    db.commit()
    db.refresh(new_group)
    return new_group


@router.put(
    "/{group_id}",
    response_model=AudienceGroupResponse,
    summary="Actualizar nombre, descripcion y miembros de un grupo de audiencia",
)
def update_group(
    group_id: str,
    payload: AudienceGroupUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("grupos")),
) -> AudienceGroupResponse:
    group = db.query(AudienceGroup).filter(AudienceGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grupo no encontrado")

    clean_name = payload.name.strip()
    if len(clean_name) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El nombre del grupo debe tener al menos 2 caracteres.",
        )

    before = _snapshot(group)
    group.name = clean_name
    group.description = payload.description.strip() if payload.description and payload.description.strip() else None
    group.google_groups = payload.google_groups
    group.emails = payload.emails

    changes = changed_fields(before, _snapshot(group))
    log_audit(
        db,
        current_user,
        "UPDATE_GROUP",
        AUDIT_TARGET_GROUP,
        target_key=group.id,
        details={"name": group.name, "changes": changes},
    )
    db.commit()
    db.refresh(group)
    return group


@router.delete("/{group_id}", summary="Eliminar grupo de audiencia")
def delete_group(
    group_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("grupos")),
):
    group = db.query(AudienceGroup).filter(AudienceGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grupo no encontrado")

    log_audit(
        db,
        current_user,
        "DELETE_GROUP",
        AUDIT_TARGET_GROUP,
        target_key=group.id,
        details={"name": group.name},
    )
    db.delete(group)
    db.commit()
    return {"message": "Grupo eliminado correctamente", "id": group_id}
