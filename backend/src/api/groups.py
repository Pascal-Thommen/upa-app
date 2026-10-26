import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..auth import get_current_user_optional, require_editor
from ..database import get_db
from ..models import AudienceGroup, User
from ..schemas.group import AudienceGroupCreate, AudienceGroupResponse, AudienceGroupUpdate

router = APIRouter(prefix="/api/groups", tags=["Groups"])


def sanitize_group_id(raw: str) -> str:
    cleaned = re.sub(r"[^a-z0-9_]", "_", raw.lower().strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or "grupo_custom"


@router.get("", response_model=list[AudienceGroupResponse], summary="Listar grupos de audiencia institucionales")
def list_groups(
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
) -> list[AudienceGroupResponse]:
    groups = db.query(AudienceGroup).order_by(AudienceGroup.is_system.desc(), AudienceGroup.name.asc()).all()
    return groups


@router.post(
    "",
    response_model=AudienceGroupResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear nuevo grupo de audiencia",
)
def create_group(
    payload: AudienceGroupCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_editor),
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
        badge_class=payload.badge_class or "bg-slate-100 text-slate-800 border-slate-200",
        google_group=payload.google_group.strip() if payload.google_group else None,
        emails=payload.emails or [f"{target_id}@upa.edu.py"],
        is_system=False,
    )
    db.add(new_group)
    db.commit()
    db.refresh(new_group)
    return new_group


@router.put(
    "/{group_id}",
    response_model=AudienceGroupResponse,
    summary="Actualizar grupo de audiencia",
)
def update_group(
    group_id: str,
    payload: AudienceGroupUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_editor),
) -> AudienceGroupResponse:
    group = db.query(AudienceGroup).filter(AudienceGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grupo no encontrado")

    if payload.name is not None:
        group.name = payload.name.strip()
    if payload.description is not None:
        group.description = payload.description.strip() if payload.description else None
    if payload.badge_class is not None:
        group.badge_class = payload.badge_class.strip()
    if payload.google_group is not None:
        group.google_group = payload.google_group.strip() if payload.google_group else None
    if payload.emails is not None:
        group.emails = payload.emails

    db.commit()
    db.refresh(group)
    return group


@router.delete("/{group_id}", summary="Eliminar grupo de audiencia")
def delete_group(
    group_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    group = db.query(AudienceGroup).filter(AudienceGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grupo no encontrado")

    if group.is_system:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se puede eliminar un grupo institucional del sistema.",
        )

    db.delete(group)
    db.commit()
    return {"message": "Grupo eliminado correctamente", "id": group_id}
