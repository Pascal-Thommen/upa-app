from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import User

security = HTTPBearer(auto_error=False)


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    """Genera un token JWT firmado para la sesion de la aplicacion."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> dict[str, Any] | None:
    """Decodifica y valida la firma y expiracion del token JWT."""
    if not token or not token.strip():
        return None
    try:
        payload = jwt.decode(token.strip(), settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except jwt.PyJWTError:
        return None


async def verify_google_id_token(id_token: str) -> dict[str, Any]:
    """
    Verifica el Google ID Token contra el endpoint oficial de Google TokenInfo
    con manejo explicito de timeouts y errores de red.
    """
    cleaned_token = (id_token or "").strip()
    if not cleaned_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El token de Google (id_token) no puede estar vacio.",
        )

    url = f"https://oauth2.googleapis.com/tokeninfo?id_token={cleaned_token}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, timeout=10.0)
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Tiempo de espera agotado al verificar el token con Google OAuth.",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Error de comunicacion con el servicio de validacion de Google OAuth.",
        ) from exc

    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google ID Token invalido o expirado.",
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Respuesta invalida del servidor de tokens de Google.",
        ) from exc

    allowed_client_ids = settings.allowed_google_client_ids_list
    if allowed_client_ids and data.get("aud") not in allowed_client_ids:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="El Client ID de Google no coincide con la aplicacion autorizada.",
        )

    return data


def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: Session = Depends(get_db),
) -> User | None:
    """Extrae el usuario actual del encabezado Authorization si esta presente y es valido."""
    if not credentials or not credentials.credentials:
        return None
    payload = decode_access_token(credentials.credentials)
    if not payload or "sub" not in payload:
        return None
    user_id = payload.get("sub")
    if user_id is None:
        return None
    if str(user_id).isdigit():
        return db.query(User).filter(User.id == int(user_id)).first()
    return db.query(User).filter(User.email == str(user_id).lower()).first()


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """Extrae y valida obligatoriamente el usuario autenticado mediante Bearer Token."""
    if not credentials or not credentials.credentials or not credentials.credentials.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticacion requerida (Bearer Token ausente)",
        )
    payload = decode_access_token(credentials.credentials)
    if not payload or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de sesion invalido o expirado",
        )
    user_id = payload.get("sub")
    if str(user_id).isdigit():
        user = db.query(User).filter(User.id == int(user_id)).first()
    else:
        user = db.query(User).filter(User.email == str(user_id).lower()).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario de la sesion no encontrado",
        )
    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Garantiza que el usuario autenticado posea rol de administrador."""
    if (current_user.role or "user") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado: Se requieren permisos de administrador (Administrator-Rechte erforderlich)",
        )
    return current_user
