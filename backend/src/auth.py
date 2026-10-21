from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import User

SESSION_COOKIE_NAME = "upa_access_token"
security = HTTPBearer(auto_error=False)

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Erzeugt einen signierten JWT-Token für die App-Session."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> dict | None:
    """Dekodiert und validiert den JWT-Token."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except jwt.PyJWTError:
        return None

async def verify_google_id_token(id_token: str) -> dict[str, Any]:
    """
    Verifiziert den Google ID Token über den offiziellen Google TokenInfo Endpunkt.
    Garantiert kryptografische Echtheit ohne externe native C-Abhängigkeiten.
    """
    url = f"https://oauth2.googleapis.com/tokeninfo?id_token={id_token}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, timeout=10.0)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Token-Validierungsdienst vorübergehend nicht erreichbar"
        ) from exc

    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültiger oder abgelaufener Google ID Token"
        )
    data = response.json()

    # Validierung des Google Client ID Audience-Targets falls konfiguriert
    allowed_client_ids = settings.allowed_google_client_ids_list
    if allowed_client_ids and data.get("aud") not in allowed_client_ids:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google Client ID stimmt nicht überein"
        )

    return data

def _extract_session_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None,
) -> str | None:
    if credentials and credentials.credentials:
        return credentials.credentials
    cookie_token = request.cookies.get(SESSION_COOKIE_NAME)
    if cookie_token:
        return cookie_token
    return None

def get_current_user_optional(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: Session = Depends(get_db)
) -> User | None:
    """Extrahiert den aktuellen Benutzer aus dem Authorization Header oder Session Cookie, falls vorhanden."""
    token = _extract_session_token(request, credentials)
    if not token:
        return None
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        return None
    user_id = payload.get("sub")
    if str(user_id).isdigit():
        return db.query(User).filter(User.id == int(user_id)).first()
    return db.query(User).filter(User.email == str(user_id)).first()

def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """Extrahiert den aktuellen Benutzer aus dem Authorization Header oder Session Cookie."""
    token = _extract_session_token(request, credentials)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentifizierung erforderlich (Bearer Token fehlt)"
        )
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültiger oder abgelaufener Session Token"
        )
    user_id = payload.get("sub")
    if str(user_id).isdigit():
        user = db.query(User).filter(User.id == int(user_id)).first()
    else:
        user = db.query(User).filter(User.email == str(user_id)).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Benutzer nicht gefunden"
        )
    return user

def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Stellt sicher, dass der anfragende Nutzer Administrator-Rechte besitzt."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Zugriff verweigert: Administrator-Rechte erforderlich"
        )
    return current_user
