
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import create_access_token, get_current_user, verify_google_id_token
from ..config import settings
from ..database import get_db
from ..models import User

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

class GoogleLoginRequest(BaseModel):
    id_token: str
    classroom_token: str | None = None

class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    groups: list[str]
    has_classroom_token: bool = False

class ClassroomTokenRequest(BaseModel):
    classroom_token: str

class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse

def _filter_user_groups_for_privacy(email: str, groups: list[str] | None) -> list[str]:
    """
    Erzwingt die Datenschutz- und Berechtigungs-Vorgabe:
    Normale Studenten duerfen ihre Mailgruppen nicht direkt sehen.
    Die Gruppenanzeige ist strikt auf das Konto pascal.thommen@upa.edu.py beschraenkt.
    """
    if email.lower() == "pascal.thommen@upa.edu.py":
        return groups or ["ALL"]
    return []

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
            groups=_filter_user_groups_for_privacy(user.email, user.groups),
            has_classroom_token=bool(user.classroom_token),
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
        groups=_filter_user_groups_for_privacy(current_user.email, current_user.groups),
        has_classroom_token=bool(current_user.classroom_token),
    )

@router.post("/classroom-token", response_model=UserResponse)
def update_classroom_token(
    payload: ClassroomTokenRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Actualiza el token de Google Classroom para el usuario autenticado.
    Permite activar la integracion de Classroom si no se concedio durante el login inicial.
    """
    current_user.classroom_token = payload.classroom_token
    db.commit()
    db.refresh(current_user)
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        groups=_filter_user_groups_for_privacy(current_user.email, current_user.groups),
        has_classroom_token=bool(current_user.classroom_token),
    )
