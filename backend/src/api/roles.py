from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, UserRole
from ..permissions import (
    PERMISSION_KEYS,
    find_unknown_permissions,
    normalize_permissions,
    require_permission,
)
from ..schemas.role import UserRoleCreate, UserRoleResponse, UserRoleUpdate
from ..services.audit import AUDIT_TARGET_ROLE, changed_fields, log_audit, permissions_diff

router = APIRouter(prefix="/api/roles", tags=["Roles"])


def _to_response(record: UserRole) -> UserRoleResponse:
    """Respuesta con permisos siempre expresados como claves canonicas de modulo."""
    perms = normalize_permissions(record.permissions)
    derived_role = "admin" if "roles" in perms else "editor"
    return UserRoleResponse(
        id=record.id,
        email=record.email,
        name=record.name,
        role=derived_role,
        permissions=perms,
        is_primary=bool(record.is_primary),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _resolve_permissions(role: str | None, requested: list[str] | None) -> list[str]:
    """
    Resuelve la lista exacta de permisos solicitada sin forzar todos los modulos.
    Por principio de privilegio minimo, si se omite 'permissions' y no se exige 'admin',
    la cuenta nueva inicia sin casillas marcadas ([]).
    """
    if requested is None:
        if role == "admin":
            return list(PERMISSION_KEYS)
        return []

    unknown = find_unknown_permissions(requested)
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Permisos desconocidos: " + ", ".join(unknown) + ". Válidos: " + ", ".join(PERMISSION_KEYS) + ".",
        )
    return normalize_permissions(requested)


def _derive_role(permissions: list[str]) -> str:
    """Deriva el rol interno segun si la cuenta administra el modulo de Roles."""
    return "admin" if "roles" in permissions else "editor"


def _count_other_roles_managers(db: Session, exclude_email: str) -> int:
    """Cuenta cuantas cuentas distintas conservan el permiso 'roles'."""
    target = exclude_email.strip().lower()
    rows = db.query(UserRole).all()
    count = 0
    for row in rows:
        if (row.email or "").strip().lower() == target:
            continue
        if "roles" in normalize_permissions(row.permissions):
            count += 1
    return count


def _ensure_at_least_one_roles_manager(
    db: Session,
    email: str,
    current_record: UserRole | None,
    new_permissions: list[str] | None,
) -> None:
    """Garantiza que nunca quede el sistema con 0 cuentas con acceso al modulo Roles."""
    had_roles = current_record is not None and "roles" in normalize_permissions(current_record.permissions)
    will_have_roles = new_permissions is not None and "roles" in new_permissions
    if had_roles and not will_have_roles:
        if _count_other_roles_managers(db, email) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Debe quedar al menos una cuenta con permiso en Roles.",
            )


def _snapshot(record: UserRole) -> dict:
    return {
        "name": record.name,
        "permissions": normalize_permissions(record.permissions),
    }


def _sync_user_table(db: Session, email: str, permissions: list[str]) -> None:
    """Sincroniza la tabla users si la persona ya inicio sesion."""
    user_record = db.query(User).filter(User.email == email).first()
    if user_record:
        if not permissions:
            user_record.role = "user"
        else:
            user_record.role = _derive_role(permissions)


@router.get("", response_model=list[UserRoleResponse], summary="Listar cuentas autorizadas y matriz de permisos")
def list_roles(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("roles")),
) -> list[UserRoleResponse]:
    roles = db.query(UserRole).order_by(UserRole.email.asc()).all()
    return [_to_response(r) for r in roles]


@router.post(
    "",
    response_model=UserRoleResponse,
    status_code=status.HTTP_200_OK,
    summary="Autorizar cuenta institucional o actualizar su matriz de permisos",
)
def assign_role(
    payload: UserRoleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("roles")),
) -> UserRoleResponse:
    email = payload.email.strip().lower()
    if not email.endswith("@upa.edu.py"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El correo debe pertenecer al dominio institucional @upa.edu.py",
        )

    role_record = db.query(UserRole).filter(UserRole.email == email).first()
    name = (
        payload.name.strip()
        if payload.name and payload.name.strip()
        else (role_record.name if role_record and role_record.name else email.split("@")[0].replace(".", " ").title())
    )
    permissions = _resolve_permissions(payload.role, payload.permissions)
    derived_role = _derive_role(permissions)

    if role_record:
        _ensure_at_least_one_roles_manager(db, email, role_record, permissions)
        before = _snapshot(role_record)
        role_record.name = name
        role_record.role = derived_role
        role_record.permissions = permissions
        log_audit(
            db,
            current_user,
            "UPDATE_ROLE",
            AUDIT_TARGET_ROLE,
            target_key=email,
            details={"name": email, "changes": changed_fields(before, _snapshot(role_record))},
        )
    else:
        role_record = UserRole(
            email=email,
            name=name,
            role=derived_role,
            permissions=permissions,
            is_primary=False,
        )
        db.add(role_record)
        log_audit(
            db,
            current_user,
            "CREATE_ROLE",
            AUDIT_TARGET_ROLE,
            target_key=email,
            details={"name": email, "permissions": permissions},
        )

    _sync_user_table(db, email, permissions)
    db.commit()
    db.refresh(role_record)
    return _to_response(role_record)


@router.put(
    "/{email}",
    response_model=UserRoleResponse,
    summary="Actualizar permisos de una cuenta ya autorizada",
)
def update_role(
    email: str,
    payload: UserRoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("roles")),
) -> UserRoleResponse:
    norm_email = email.strip().lower()
    role_record = db.query(UserRole).filter(UserRole.email == norm_email).first()
    if not role_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado en la lista de roles")

    permissions = _resolve_permissions(payload.role, payload.permissions)
    _ensure_at_least_one_roles_manager(db, norm_email, role_record, permissions)
    derived_role = _derive_role(permissions)

    before = _snapshot(role_record)
    if payload.name and payload.name.strip():
        role_record.name = payload.name.strip()
    role_record.role = derived_role
    role_record.permissions = permissions

    log_audit(
        db,
        current_user,
        "UPDATE_ROLE",
        AUDIT_TARGET_ROLE,
        target_key=norm_email,
        details={
            "name": norm_email,
            "changes": changed_fields(before, _snapshot(role_record)),
            "diff": permissions_diff(before["permissions"], permissions),
        },
    )
    _sync_user_table(db, norm_email, permissions)
    db.commit()
    db.refresh(role_record)
    return _to_response(role_record)


@router.delete("/{email}", summary="Revocar autorizacion de una cuenta")
def revoke_role(
    email: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("roles")),
):
    norm_email = email.strip().lower()
    role_record = db.query(UserRole).filter(UserRole.email == norm_email).first()
    if not role_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado en la lista de roles")

    _ensure_at_least_one_roles_manager(db, norm_email, role_record, None)

    log_audit(
        db,
        current_user,
        "DELETE_ROLE",
        AUDIT_TARGET_ROLE,
        target_key=norm_email,
        details={"name": norm_email},
    )
    db.delete(role_record)

    user_record = db.query(User).filter(User.email == norm_email).first()
    if user_record:
        user_record.role = "user"

    db.commit()
    return {"message": f"Rol revocado correctamente para {norm_email}", "email": norm_email}
