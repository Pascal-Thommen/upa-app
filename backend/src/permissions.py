"""Modelo de permisos por modulo del portal web-admin (Publicaciones, Grupos, Roles, APIs)."""

from typing import Any

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from .auth import get_current_user
from .database import get_db
from .models import User, UserRole

# Claves canonicas de permiso: una por cada modulo (pestana) del portal.
PERMISSION_KEYS: tuple[str, ...] = ("publicaciones", "grupos", "roles", "apis")

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
}

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


def find_unknown_permissions(raw_values: list[str]) -> list[str]:
    """Permisos enviados por el cliente que no pertenecen al catalogo."""
    return [str(v) for v in raw_values if parse_permission(v) is None]


def effective_permissions(db: Session, user: User) -> list[str]:
    """
    Permisos vigentes del usuario:
    1. Si existe un registro explicito en user_roles para su correo, se respetan exactamente sus permisos guardados.
    2. Sin fila en user_roles: admin = todos los modulos; editor = publicaciones; resto = ninguno.
    """
    clean_email = (user.email or "").strip().lower()
    if clean_email:
        record = db.query(UserRole).filter(UserRole.email == clean_email).first()
        if record is not None:
            return normalize_permissions(record.permissions)

    role = (user.role or "user").strip()
    if role == "admin":
        return list(PERMISSION_KEYS)
    if role == "editor":
        return list(DEFAULT_EDITOR_PERMISSIONS)
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
