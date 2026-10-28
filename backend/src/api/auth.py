import logging
import re
import urllib.parse
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from ..auth import create_access_token, get_current_user, verify_google_id_token
from ..config import settings
from ..database import get_db
from ..models import User, UserRole
from ..permissions import effective_permissions, normalize_permissions
from ..schemas.feed import ErrorResponse
from ..services.google_groups import get_google_groups_for_user, map_groups_to_logical_tags
from .classroom import clear_classroom_cache

logger = logging.getLogger("upa.auth")

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

ADMIN_EMAILS = {
    "pascal.thommen@upa.edu.py",
    "soporte.ti@upa.edu.py",
    "admin@upa.edu.py",
}


def _resolve_user_role(db: Session, email: str, existing_user: User | None = None) -> str:
    assigned_role = db.query(UserRole).filter(UserRole.email == email).first()
    if assigned_role:
        perms = normalize_permissions(assigned_role.permissions)
        if "roles" in perms:
            return "admin"
        if perms:
            return "editor"
        return "user"
    if existing_user and existing_user.role in ("admin", "editor"):
        return existing_user.role
    if email in ADMIN_EMAILS:
        return "admin"
    return "user"


class GoogleLoginRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id_token": "eyJhbGciOiJSUzI1NiIsImtpZCI6IjEifQ...",
                "classroom_token": "ya29.a0AfH6SM...",
                "classroom_refresh_token": "1//0gSampleRefreshToken...",
            }
        }
    )

    id_token: str = Field(..., description="Google ID Token emitido por Google Sign-In")
    classroom_token: str | None = Field(default=None, description="Token OAuth 2.0 opcional para Google Classroom")
    classroom_refresh_token: str | None = Field(
        default=None,
        description="Refresh Token OAuth 2.0 opcional para renovacion automatica de Classroom",
    )


class DevLoginRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "pascal.thommen@upa.edu.py",
                "full_name": "Pascal Thommen",
            }
        }
    )

    email: str = Field(
        ...,
        description="Correo institucional (@upa.edu.py) para generar sesion JWT de desarrollo",
    )
    full_name: str | None = Field(
        default=None,
        description="Nombre completo opcional del usuario",
    )
    classroom_token: str | None = Field(
        default=None,
        description="Token OAuth opcional para sincronizacion con Google Classroom",
    )
    classroom_refresh_token: str | None = Field(
        default=None,
        description="Refresh Token OAuth 2.0 opcional para auto-refresh de Google Classroom",
    )


class GoogleGroupDetail(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "01abc234def",
                "name": "Estudiantes TIE",
                "email": "estudiantes.tie@upa.edu.py",
                "description": "Grupo institucional de Ingenieria Empresarial",
            }
        }
    )

    id: str = Field(default="", description="ID del grupo en Google Workspace (nunca nulo)")
    name: str = Field(default="", description="Nombre del grupo institucional (nunca nulo)")
    email: str = Field(default="", description="Correo de la lista de distribucion (nunca nulo)")
    description: str = Field(default="", description="Descripcion del grupo (nunca nulo)")


class UserResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": 1,
                "email": "pascal.thommen@upa.edu.py",
                "full_name": "Pascal Thommen",
                "role": "admin",
                "groups": ["ALL", "Semester_4", "TIE"],
                "google_groups": [
                    {
                        "id": "01abc234def",
                        "name": "Estudiantes TIE",
                        "email": "estudiantes.tie@upa.edu.py",
                        "description": "Grupo institucional de Ingenieria Empresarial",
                    }
                ],
                "has_classroom_token": False,
            }
        }
    )

    id: int = Field(..., description="Identificador unico del usuario en la base de datos")
    email: str = Field(..., description="Correo institucional @upa.edu.py")
    full_name: str = Field(..., description="Nombre completo del usuario (nunca nulo)")
    role: str = Field(..., description="Rol de autorizacion en el sistema: user o admin")
    groups: list[str] = Field(
        default_factory=list,
        description="Etiquetas de grupos visibles segun politica de privacidad",
    )
    google_groups: list[GoogleGroupDetail] = Field(
        default_factory=list,
        description="Detalle de grupos de Google Workspace (exclusivo para cuenta autorizada)",
    )
    has_classroom_token: bool = Field(
        default=False,
        description="Indica si el usuario tiene un token de Google Classroom registrado",
    )
    permissions: list[str] = Field(
        default_factory=list,
        description="Modulos del portal habilitados: publicaciones, grupos, roles, apis",
    )


class ClassroomTokenRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "classroom_token": "ya29.a0AfH6SM_sample_classroom_oauth_token",
                "classroom_refresh_token": "1//0gSampleRefreshToken...",
            }
        }
    )

    classroom_token: str = Field(..., description="Token OAuth de acceso a Google Classroom")
    classroom_refresh_token: str | None = Field(
        default=None,
        description="Refresh Token OAuth 2.0 opcional para auto-refresh de Google Classroom",
    )


class AuthResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "user": {
                    "id": 1,
                    "email": "pascal.thommen@upa.edu.py",
                    "full_name": "Pascal Thommen",
                    "role": "admin",
                    "groups": ["ALL", "Semester_4", "TIE"],
                    "google_groups": [],
                    "has_classroom_token": False,
                },
            }
        }
    )

    access_token: str = Field(..., description="Token JWT firmado para enviar en Authorization: Bearer <token>")
    token_type: str = Field(default="bearer", description="Esquema de autenticacion (siempre bearer)")
    user: UserResponse = Field(..., description="Perfil completo del usuario autenticado")


def _filter_user_groups_for_privacy(email: str, groups: list[Any] | None) -> list[str]:
    """
    Aplica la politica de privacidad de grupos:
    Los estudiantes regulares no visualizan directamente las listas internas de distribucion.
    La vista completa esta habilitada exclusivamente para pascal.thommen@upa.edu.py.
    """
    if (email or "").strip().lower() == "pascal.thommen@upa.edu.py":
        return [str(g).strip() for g in (groups or []) if g is not None and str(g).strip()]
    return []


def _filter_google_groups_for_privacy(email: str, google_groups: list[Any] | None) -> list[GoogleGroupDetail]:
    """Garantiza visibilidad exclusiva de Google Groups para pascal.thommen@upa.edu.py sin valores nulos."""
    if (email or "").strip().lower() != "pascal.thommen@upa.edu.py":
        return []
    sanitized: list[GoogleGroupDetail] = []
    for g in google_groups or []:
        if isinstance(g, dict):
            sanitized.append(
                GoogleGroupDetail(
                    id=str(g.get("id") or ""),
                    name=str(g.get("name") or ""),
                    email=str(g.get("email") or ""),
                    description=str(g.get("description") or ""),
                )
            )
    return sanitized


def _derive_full_name(email: str, provided_name: str | None = None) -> str:
    """Genera un nombre completo limpio a partir del nombre provisto o del correo."""
    if provided_name and provided_name.strip():
        return provided_name.strip()
    local_part = (email or "usuario").split("@")[0]
    parts = [p.capitalize() for p in local_part.replace("_", ".").replace("-", ".").split(".") if p]
    return " ".join(parts) if parts else local_part


def _validate_and_normalize_email(raw_email: str) -> str:
    """Valida el formato del correo electronico y el dominio institucional @upa.edu.py."""
    email = (raw_email or "").strip().lower()
    if not email or " " in email or "@" not in email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Formato de correo electronico invalido.",
        )
    parts = email.split("@")
    if len(parts) != 2 or not parts[0] or not parts[1] or "." not in parts[1]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Formato de correo electronico invalido.",
        )
    if parts[1] != settings.ALLOWED_EMAIL_DOMAIN.lower():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Acceso denegado: Solo se permiten correos institucionales @{settings.ALLOWED_EMAIL_DOMAIN}.",
        )
    return email


def _build_user_response(user: User, permissions: list[str] | None = None) -> UserResponse:
    """Construye un UserResponse libre de valores nulos y con filtrado de privacidad."""
    clean_email = (user.email or "").strip().lower()
    clean_name = (user.full_name or "").strip() or _derive_full_name(clean_email)
    clean_role = (user.role or "user").strip() or "user"
    has_token = bool(
        (user.classroom_token and str(user.classroom_token).strip())
        or (getattr(user, "classroom_refresh_token", None) and str(user.classroom_refresh_token).strip())
    )
    return UserResponse(
        id=int(user.id),
        email=clean_email,
        full_name=clean_name,
        role=clean_role,
        groups=_filter_user_groups_for_privacy(clean_email, user.groups),
        google_groups=_filter_google_groups_for_privacy(clean_email, user.google_groups),
        has_classroom_token=has_token,
        permissions=list(permissions or []),
    )


DEFAULT_GOOGLE_REDIRECT_URI = "https://upa.eu1.netbird.services/api/auth/google"
_HOST_PATTERN = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?(:\d{1,5})?$")


def resolve_google_redirect_uri(request: Request) -> str:
    """Ermittelt die OAuth redirect_uri: Setting, dann Forwarded-Header, sonst sicherer Fallback."""
    configured = (settings.GOOGLE_REDIRECT_URI or "").strip()
    if configured:
        return configured

    proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    host = (request.headers.get("x-forwarded-host") or "").split(",")[0].strip().lower()
    if proto in ("http", "https") and host and _HOST_PATTERN.match(host):
        return f"{proto}://{host}/api/auth/google"
    if proto or host:
        logger.warning("Ungueltige Forwarded-Header fuer OAuth redirect_uri, nutze Fallback.")
    return DEFAULT_GOOGLE_REDIRECT_URI


@router.get("/login-google", summary="Iniciar flujo web OAuth 2.0 con Google")
def login_google(request: Request, force_consent: bool = False):
    """Inicia el flujo oficial de redireccion Google OAuth 2.0 Web con permisos de Classroom."""
    client_id = (settings.GOOGLE_CLIENT_ID or "").strip()
    if not client_id:
        logger.error(
            "Error de configuracion Google OAuth: GOOGLE_CLIENT_ID esta ausente o vacio. "
            "Se cancela la redireccion a accounts.google.com para evitar una URL incompleta (400 invalid_request)."
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Configuracion OAuth incompleta: falta GOOGLE_CLIENT_ID.",
        )

    prompt_val = "consent select_account" if force_consent else "select_account"
    params = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "redirect_uri": resolve_google_redirect_uri(request),
            "response_type": "code",
            "scope": "openid email profile https://www.googleapis.com/auth/classroom.courses.readonly https://www.googleapis.com/auth/classroom.coursework.me.readonly",
            "access_type": "offline",
            "prompt": prompt_val,
            "hd": settings.ALLOWED_EMAIL_DOMAIN,
        }
    )
    return RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{params}")


@router.get("/google", summary="Callback OAuth 2.0 de Google")
async def google_callback(
    request: Request,
    code: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    """
    Recibe el codigo de autorizacion OAuth 2.0 de Google, lo intercambia por tokens,
    verifica el dominio institucional y redirige al portal con el JWT de sesion.
    """
    if error or not code:
        return RedirectResponse(f"/dashboard/?auth_error={error or 'missing_code'}")

    client_id = (settings.GOOGLE_CLIENT_ID or "").strip()
    client_secret = (settings.GOOGLE_CLIENT_SECRET or "").strip()
    if not client_id:
        logger.error("Error de configuracion Google OAuth en callback: GOOGLE_CLIENT_ID esta ausente o vacio.")
        return RedirectResponse("/dashboard/?auth_error=missing_client_id")

    try:
        async with httpx.AsyncClient(timeout=10.0) as http_client:
            token_resp = await http_client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": resolve_google_redirect_uri(request),
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=10.0,
            )
    except httpx.HTTPError:
        return RedirectResponse("/dashboard/?auth_error=token_exchange_failed")

    if token_resp.status_code != 200:
        return RedirectResponse("/dashboard/?auth_error=token_exchange_failed")

    token_data = token_resp.json()
    id_token = token_data.get("id_token")
    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")

    if not id_token:
        return RedirectResponse("/dashboard/?auth_error=missing_id_token")

    try:
        google_data = await verify_google_id_token(id_token)
    except HTTPException:
        return RedirectResponse("/dashboard/?auth_error=invalid_id_token")

    email = (google_data.get("email") or "").strip().lower()
    full_name = _derive_full_name(email, google_data.get("name"))

    if not email.endswith(f"@{settings.ALLOWED_EMAIL_DOMAIN}"):
        return RedirectResponse("/dashboard/?auth_error=forbidden_domain")

    raw_google_groups = await get_google_groups_for_user(email)
    mapped_tags = map_groups_to_logical_tags(raw_google_groups)

    user = db.query(User).filter(User.email == email).first()
    resolved_role = _resolve_user_role(db, email, existing_user=user)
    if not user:
        user = User(
            email=email,
            full_name=full_name,
            role=resolved_role,
            groups=mapped_tags,
            google_groups=raw_google_groups,
            classroom_token=access_token,
            classroom_refresh_token=refresh_token.strip() if refresh_token and str(refresh_token).strip() else None,
        )
        db.add(user)
    else:
        user.full_name = full_name
        user.role = resolved_role
        user.groups = mapped_tags
        user.google_groups = raw_google_groups
        if access_token:
            user.classroom_token = access_token
            clear_classroom_cache(email)
        if refresh_token and str(refresh_token).strip():
            user.classroom_refresh_token = str(refresh_token).strip()

    db.commit()
    db.refresh(user)

    session_token = create_access_token(data={"sub": str(user.id), "email": user.email, "role": user.role})
    return RedirectResponse(f"/dashboard/?token={session_token}")


@router.post(
    "/google",
    response_model=AuthResponse,
    summary="Autenticar con Google ID Token",
    responses={
        400: {"model": ErrorResponse, "description": "ID Token vacio o malformado"},
        401: {"model": ErrorResponse, "description": "Google ID Token invalido o expirado"},
        403: {"model": ErrorResponse, "description": "Correo fuera del dominio institucional @upa.edu.py"},
        503: {"model": ErrorResponse, "description": "Timeout o error de red con Google OAuth"},
    },
)
async def google_login(payload: GoogleLoginRequest, db: Session = Depends(get_db)) -> AuthResponse:
    """
    Valida el Google ID Token, aplica la restriccion de dominio @upa.edu.py,
    consulta Google Groups mediante Service Account y emite el JWT de sesion.
    """
    google_data = await verify_google_id_token(payload.id_token)
    raw_email = (google_data.get("email") or "").strip().lower()
    email = _validate_and_normalize_email(raw_email)
    full_name = _derive_full_name(email, google_data.get("name"))

    raw_google_groups = await get_google_groups_for_user(email)
    mapped_tags = map_groups_to_logical_tags(raw_google_groups)

    user = db.query(User).filter(User.email == email).first()
    resolved_role = _resolve_user_role(db, email, existing_user=user)
    if not user:
        user = User(
            email=email,
            full_name=full_name,
            role=resolved_role,
            groups=mapped_tags,
            google_groups=raw_google_groups,
            classroom_token=payload.classroom_token.strip()
            if payload.classroom_token and payload.classroom_token.strip()
            else None,
            classroom_refresh_token=(
                payload.classroom_refresh_token.strip()
                if payload.classroom_refresh_token and payload.classroom_refresh_token.strip()
                else None
            ),
        )
        db.add(user)
    else:
        user.full_name = full_name
        user.role = resolved_role
        user.groups = mapped_tags
        user.google_groups = raw_google_groups
        if payload.classroom_token and payload.classroom_token.strip():
            user.classroom_token = payload.classroom_token.strip()
            clear_classroom_cache(email)
        if payload.classroom_refresh_token and payload.classroom_refresh_token.strip():
            user.classroom_refresh_token = payload.classroom_refresh_token.strip()

    db.commit()
    db.refresh(user)

    session_token = create_access_token(data={"sub": str(user.id), "email": user.email, "role": user.role})

    return AuthResponse(
        access_token=session_token,
        token_type="bearer",
        user=_build_user_response(user, effective_permissions(db, user)),
    )


@router.post(
    "/dev-login",
    response_model=AuthResponse,
    summary="Login provisorio de desarrollo mediante correo institucional",
    responses={
        400: {"model": ErrorResponse, "description": "Formato de correo electronico invalido"},
        403: {"model": ErrorResponse, "description": "Dominio no permitido (solo @upa.edu.py)"},
    },
)
async def dev_login(payload: DevLoginRequest, db: Session = Depends(get_db)) -> AuthResponse:
    """
    Genera una sesion JWT real y completa a partir de un correo institucional @upa.edu.py
    sin requerir configuracion de Google Cloud Console OAuth en el cliente.
    Entrega exactamente la misma estructura AuthResponse y persistencia en base de datos
    que el flujo OAuth estandar.
    """
    email = _validate_and_normalize_email(payload.email)
    raw_google_groups = await get_google_groups_for_user(email)

    user = db.query(User).filter(User.email == email).first()

    if raw_google_groups:
        mapped_tags = map_groups_to_logical_tags(raw_google_groups)
    elif user and user.groups:
        mapped_tags = [str(g).strip() for g in user.groups if g is not None and str(g).strip()]
        if "ALL" not in mapped_tags:
            mapped_tags.append("ALL")
        mapped_tags = sorted(set(mapped_tags))
        raw_google_groups = list(user.google_groups or [])
    else:
        default_tags = ["ALL", "Semester_4", "TIE"] if email == "pascal.thommen@upa.edu.py" else ["ALL"]
        mapped_tags = sorted(set(default_tags))

    resolved_role = _resolve_user_role(db, email, existing_user=user)
    if not user:
        full_name = _derive_full_name(email, payload.full_name)
        user = User(
            email=email,
            full_name=full_name,
            role=resolved_role,
            groups=mapped_tags,
            google_groups=raw_google_groups,
            classroom_token=(
                payload.classroom_token.strip() if payload.classroom_token and payload.classroom_token.strip() else None
            ),
            classroom_refresh_token=(
                payload.classroom_refresh_token.strip()
                if payload.classroom_refresh_token and payload.classroom_refresh_token.strip()
                else None
            ),
        )
        db.add(user)
    else:
        if payload.full_name and payload.full_name.strip():
            user.full_name = payload.full_name.strip()
        elif not user.full_name or not user.full_name.strip():
            user.full_name = _derive_full_name(email)
        user.role = resolved_role
        user.groups = mapped_tags
        if raw_google_groups:
            user.google_groups = raw_google_groups
        elif user.google_groups is None:
            user.google_groups = []
        if payload.classroom_token and payload.classroom_token.strip():
            user.classroom_token = payload.classroom_token.strip()
            clear_classroom_cache(email)
        if payload.classroom_refresh_token and payload.classroom_refresh_token.strip():
            user.classroom_refresh_token = payload.classroom_refresh_token.strip()

    db.commit()
    db.refresh(user)

    session_token = create_access_token(data={"sub": str(user.id), "email": user.email, "role": user.role})

    return AuthResponse(
        access_token=session_token,
        token_type="bearer",
        user=_build_user_response(user, effective_permissions(db, user)),
    )


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Obtener perfil del usuario autenticado",
    responses={
        401: {"model": ErrorResponse, "description": "Token JWT ausente, invalido o expirado"},
    },
)
def get_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserResponse:
    """Retorna los datos de perfil, grupos y modulos habilitados del usuario autenticado actualmente."""
    return _build_user_response(current_user, effective_permissions(db, current_user))


@router.post(
    "/classroom-token",
    response_model=UserResponse,
    summary="Actualizar token OAuth de Google Classroom",
    responses={
        400: {"model": ErrorResponse, "description": "Token de Classroom vacio"},
        401: {"model": ErrorResponse, "description": "Token JWT ausente, invalido o expirado"},
    },
)
def update_classroom_token(
    payload: ClassroomTokenRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserResponse:
    """
    Actualiza el token de Google Classroom para el usuario autenticado
    e invalida la cache previa de cursos y tareas.
    """
    cleaned_token = (payload.classroom_token or "").strip()
    if not cleaned_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El token de Google Classroom no puede estar vacio.",
        )
    current_user.classroom_token = cleaned_token
    if payload.classroom_refresh_token is not None:
        cleaned_refresh = payload.classroom_refresh_token.strip()
        if cleaned_refresh:
            current_user.classroom_refresh_token = cleaned_refresh
    db.commit()
    db.refresh(current_user)
    clear_classroom_cache(current_user.email)
    return _build_user_response(current_user, effective_permissions(db, current_user))


@router.get(
    "/groups",
    response_model=list[GoogleGroupDetail],
    summary="Obtener grupos de Google Workspace sincronizados",
    responses={
        401: {"model": ErrorResponse, "description": "Token JWT ausente, invalido o expirado"},
    },
)
def get_my_groups(current_user: User = Depends(get_current_user)) -> list[GoogleGroupDetail]:
    """Retorna los grupos de Google Workspace sincronizados (exclusivo para pascal.thommen@upa.edu.py)."""
    return _filter_google_groups_for_privacy(current_user.email, current_user.google_groups)
