from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import create_access_token, get_current_user, verify_google_id_token
from ..config import settings
from ..database import get_db
from ..models import User
from ..services.google_groups import get_google_groups_for_user, map_groups_to_logical_tags

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

class GoogleLoginRequest(BaseModel):
    id_token: str
    classroom_token: str | None = None

class GoogleGroupDetail(BaseModel):
    id: str | None = None
    name: str
    email: str
    description: str | None = None

class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    groups: list[str]
    google_groups: list[GoogleGroupDetail] = []
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
    Normale Studenten duerfen ihre internen Mailverteiler nicht direkt einsehen.
    Die vollstaendige Gruppenanzeige ist fuer das Administratoren-Konto pascal.thommen@upa.edu.py freigeschaltet.
    """
    if email.lower() == "pascal.thommen@upa.edu.py":
        return groups or []
    return []

def _filter_google_groups_for_privacy(email: str, google_groups: list[dict] | None) -> list[GoogleGroupDetail]:
    """Erzwingt exklusive Google Groups Einsicht fuer pascal.thommen@upa.edu.py."""
    if email.lower() == "pascal.thommen@upa.edu.py":
        return [GoogleGroupDetail(**g) for g in (google_groups or [])]
    return []

@router.post("/google", response_model=AuthResponse)
async def google_login(payload: GoogleLoginRequest, db: Session = Depends(get_db)):
    """
    Validiert den Google ID Token und meldet den Benutzer an.
    Erzwingt die Domänen-Sperre (@upa.edu.py).
    Fragt Google Groups über den hinterlegten Service Account ab.
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

    # 2. Google Groups über Service Account ermitteln
    raw_google_groups = await get_google_groups_for_user(email)
    mapped_tags = map_groups_to_logical_tags(raw_google_groups)

    # 3. Benutzer abfragen oder neu anlegen
    user = db.query(User).filter(User.email == email).first()
    if not user:
        # Standardrolle: Neuer Nutzer ist "user" (außer soporte.ti oder pascal.thommen erhalten initial admin)
        initial_role = "admin" if email in ["pascal.thommen@upa.edu.py", "soporte.ti@upa.edu.py"] else "user"
        user = User(
            email=email,
            full_name=full_name,
            role=initial_role,
            groups=mapped_tags,
            google_groups=raw_google_groups,
            classroom_token=payload.classroom_token
        )
        db.add(user)
    else:
        # Bestehenden Benutzer aktualisieren
        user.full_name = full_name
        user.groups = mapped_tags
        user.google_groups = raw_google_groups
        if payload.classroom_token:
            user.classroom_token = payload.classroom_token
            
    db.commit()
    db.refresh(user)

    # 4. Eigenen signierten JWT Session-Token generieren
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
            google_groups=_filter_google_groups_for_privacy(user.email, user.google_groups),
            has_classroom_token=bool(user.classroom_token),
        )
    )

@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """Liefert die Profildaten des aktuell eingeloggten Benutzers inklusive Gruppen."""
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        groups=_filter_user_groups_for_privacy(current_user.email, current_user.groups),
        google_groups=_filter_google_groups_for_privacy(current_user.email, current_user.google_groups),
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
        google_groups=_filter_google_groups_for_privacy(current_user.email, current_user.google_groups),
        has_classroom_token=bool(current_user.classroom_token),
    )

@router.get("/groups", response_model=list[GoogleGroupDetail])
def get_my_groups(current_user: User = Depends(get_current_user)):
    """Liefert die synchronisierten Google Groups des Benutzers (exklusiv fuer pascal.thommen@upa.edu.py)."""
    return _filter_google_groups_for_privacy(current_user.email, current_user.google_groups)
