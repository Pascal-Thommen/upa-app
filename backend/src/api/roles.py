from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..auth import require_admin, require_editor
from ..database import get_db
from ..models import User, UserRole
from ..schemas.role import UserRoleCreate, UserRoleResponse

router = APIRouter(prefix="/api/roles", tags=["Roles"])


@router.get("", response_model=list[UserRoleResponse], summary="Listar administradores y roles asignados")
def list_roles(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_editor),
) -> list[UserRoleResponse]:
    roles = db.query(UserRole).order_by(UserRole.is_primary.desc(), UserRole.email.asc()).all()
    return roles


@router.post(
    "",
    response_model=UserRoleResponse,
    status_code=status.HTTP_200_OK,
    summary="Asignar o actualizar rol de administrador",
)
def assign_role(
    payload: UserRoleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> UserRoleResponse:
    email = payload.email.strip().lower()
    if not email.endswith("@upa.edu.py"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El correo debe pertenecer al dominio institucional @upa.edu.py",
        )

    role_record = db.query(UserRole).filter(UserRole.email == email).first()
    name = payload.name or email.split("@")[0].replace(".", " ").title()

    if role_record:
        if role_record.is_primary and payload.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El administrador principal no puede ser degradado a un rol inferior.",
            )
        role_record.name = name
        role_record.role = payload.role
        role_record.permissions = payload.permissions
    else:
        role_record = UserRole(
            email=email,
            name=name,
            role=payload.role,
            permissions=payload.permissions,
            is_primary=False,
        )
        db.add(role_record)

    # Sincronizar tabla users si el usuario ya inicio sesion previamente
    user_record = db.query(User).filter(User.email == email).first()
    if user_record:
        user_record.role = "admin" if payload.role == "admin" else "user"

    db.commit()
    db.refresh(role_record)
    return role_record


@router.put(
    "/{email}",
    response_model=UserRoleResponse,
    summary="Actualizar permisos de rol de administrador o editor",
)
def update_role_permissions(
    email: str,
    payload: UserRoleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> UserRoleResponse:
    payload.email = email
    return assign_role(payload=payload, db=db, current_user=current_user)


@router.delete("/{email}", summary="Revocar autorizacion de administrador o editor")
def revoke_role(
    email: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    norm_email = email.strip().lower()
    role_record = db.query(UserRole).filter(UserRole.email == norm_email).first()
    if not role_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado en la lista de roles")

    if role_record.is_primary or norm_email == "pascal.thommen@upa.edu.py":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se puede revocar el rol del administrador principal.",
        )

    db.delete(role_record)

    # Si existe en users, volver a role='user'
    user_record = db.query(User).filter(User.email == norm_email).first()
    if user_record:
        user_record.role = "user"

    db.commit()
    return {"message": f"Rol revocado correctamente para {norm_email}", "email": norm_email}
