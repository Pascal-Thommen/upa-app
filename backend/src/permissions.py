"""Modelo de permisos por modulo del portal web-admin (Publicaciones, Grupos, Roles, APIs, IA, Historial)."""

from typing import Any

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from .auth import get_current_user
from .database import get_db
from .models import User, UserRole

# Claves canonicas de permiso: una por cada modulo o funcion del portal.
PERMISSION_KEYS: tuple[str, ...] = ("publicaciones", "grupos", "roles", "apis", "ia", "historial")

# Etiquetas historicas guardadas en la base de datos antes de las claves canonicas unificadas.
LEGACY_PERMISSION_LABELS: dict[str, str] = {
    "publicaciones y eventos": "publicaciones",
    "grupos y audiencias": "grupos",
    "gestión de roles": "roles",
    "gestion de roles": "roles",
    "consola de roles": "roles",
    "diagnóstico de apis": "apis",
    "diagnostico de apis": "apis",
    "diagnóstico": "apis",
    "diagnostico": "apis",
    "control de apis": "apis",
    "control": "apis",
    "vista de estudiantes": "apis",
    "estudiantes": "apis",
    "control de ia": "ia",
    "inteligencia artificial": "ia",
    "historial de cambios": "historial",
    "auditoría": "historial",
    "auditoria": "historial",
}

# Cuentas de emergencia de administracion (root fallback cuando no existe fila propia en user_roles).
ADMIN_EMAILS: frozenset[str] = frozenset(
    {
        "pascal.thommen@upa.edu.py",
        "soporte.ti@upa.edu.py",
        "admin@upa.edu.py",
    }
)

# Permiso por defecto de una cuenta de redaccion sin registro propio en la tabla de roles.
DEFAULT_EDITOR_PERMISSIONS: tuple[str, ...] = ("publicaciones",)


def parse_permission(raw: Any) -> str | None:
    """Devuelve la clave canonica de un permiso (o None si es desconocido)."""
    clean = str(raw or "").strip().lower()
    if clean in PERMISSION_KEYS:
        return clean
    return LEGACY_PERMISSION_LABELS.get(clean)


def normalize_permissions(raw_values: Any) -> list[str]:
    """Convierte una lista de permisos (claves o etiquetas historicas) a claves canonicas sin duplicados."""
    if not isinstance(raw_values, list):
        return []
    found = {key for key in (parse_permission(v) for v in raw_values) if key}
    return [key for key in PERMISSION_KEYS if key in found]


def normalize_role_record_permissions(record: UserRole) -> list[str]:
    """
    Normaliza los permisos de un registro UserRole garantizando retrocompatibilidad:
    los roles de administrador existentes que contengan los 4 modulos base pre-IA
    ("publicaciones", "grupos", "roles", "apis") conservan automaticamente el permiso 'ia'
    salvo que sus permisos ya hayan sido ajustados.
    """
    perms = normalize_permissions(record.permissions)
    raw_list = record.permissions if isinstance(record.permissions, list) else []
    raw_clean = {str(v or "").strip().lower() for v in raw_list}
    if (
        "ia" not in perms
        and "ia" not in raw_clean
        and {"publicaciones", "grupos", "roles", "apis"}.issubset(set(perms))
    ):
        perms = [key for key in PERMISSION_KEYS if key in (*perms, "ia")]
    return perms


def find_unknown_permissions(raw_values: list[str]) -> list[str]:
    """Permisos enviados por el cliente que no pertenecen al catalogo."""
    return [str(v) for v in raw_values if parse_permission(v) is None]


def effective_permissions(db: Session, user: User) -> list[str]:
    """
    Permisos vigentes del usuario (PBAC puro sin user.role como intermediario):
    1. Si existe un registro explicito en user_roles para su correo, se respetan exactamente sus permisos guardados.
    2. Si el correo pertenece a ADMIN_EMAILS, actua como root de emergencia con todos los modulos.
    3. Cualquier otro caso no tiene permisos de portal ([]).
    """
    clean_email = (getattr(user, "email", None) or "").strip().lower()
    if clean_email:
        record = db.query(UserRole).filter(UserRole.email == clean_email).first()
        if record is not None:
            return normalize_role_record_permissions(record)
        if clean_email in ADMIN_EMAILS:
            return list(PERMISSION_KEYS)

    return []


def require_permission(permission: str):
    """Dependencia FastAPI: exige el permiso de modulo indicado."""
    if permission not in PERMISSION_KEYS:
        raise ValueError(f"Permiso desconocido: {permission}")

    def dependency(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        if permission not in effective_permissions(db, current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acceso denegado: su cuenta no tiene el permiso '{permission}'.",
            )
        return current_user

    return dependency
