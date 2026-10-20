from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..config import settings
from ..auth import verify_google_id_token, create_access_token, get_current_user

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

class GoogleLoginRequest(BaseModel):
    id_token: str
    classroom_token: Optional[str] = None

class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    groups: List[str]

class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse

@router.post("/google", response_model=AuthResponse)
async def google_login(payload: GoogleLoginRequest, db: Session = Depends(get_db)):
    """
    Validiert den Google ID Token und meldet den Benutzer an.
    Erzwingt die Domänen-Sperre (@upa.edu.py).
    Erzeugt oder aktualisiert den lokalen Benutzerdatensatz und stellt einen Session-JWT aus.
    """
    google_data = await verify_google_id_token(payload.id_token)
    email = google_data.get("email", "").lower()
    full_name = google_data.get("name", email.split("@")[0])

    # 1. Domänen-Sperre
    if not email.endswith(f"@{settings.ALLOWED_EMAIL_DOMAIN}"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Zugang verweigert: Nur offizielle E-Mails mit @{settings.ALLOWED_EMAIL_DOMAIN} sind zugelassen."
        )

    # 2. Benutzer abfragen oder neu anlegen
    user = db.query(User).filter(User.email == email).first()
    if not user:
        # Standardrolle: Neuer Nutzer ist "user" (außer soporte.ti oder pascal.thommen erhalten initial admin)
        initial_role = "admin" if email in ["pascal.thommen@upa.edu.py", "soporte.ti@upa.edu.py"] else "user"
        user = User(
            email=email,
            full_name=full_name,
            role=initial_role,
            groups=["ALL"],
            classroom_token=payload.classroom_token
        )
        db.add(user)
    else:
        # Bestehenden Benutzer aktualisieren
        user.full_name = full_name
        if payload.classroom_token:
            user.classroom_token = payload.classroom_token
            
    db.commit()
    db.refresh(user)

    # 3. Eigenen signierten JWT Session-Token generieren
    session_token = create_access_token(data={"sub": str(user.id), "email": user.email, "role": user.role})

    return AuthResponse(
        access_token=session_token,
        token_type="bearer",
        user=UserResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            groups=user.groups or ["ALL"]
        )
    )

@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """Liefert die Profildaten des aktuell eingeloggten Benutzers."""
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        groups=current_user.groups or ["ALL"]
    )
