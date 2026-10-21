from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import DeviceToken, User
from ..schemas.feed import ErrorResponse
from ..schemas.post import ensure_utc_datetime

router = APIRouter(prefix="/api/users", tags=["Users"])

ALLOWED_PLATFORMS = {"android", "ios", "web"}


class DeviceTokenRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "device_token": "fcm_token_android_d8a92b3c4e5f6a7b8c9d0e1f2a3b4c5d",
                "platform": "android",
            }
        }
    )

    device_token: str = Field(
        ...,
        description="Token FCM o identificador de dispositivo movil para notificaciones push",
    )
    platform: str = Field(
        default="android",
        description="Plataforma del dispositivo: android, ios o web",
    )


class DeviceTokenResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_id": 1,
                "device_token": "fcm_token_android_d8a92b3c4e5f6a7b8c9d0e1f2a3b4c5d",
                "platform": "android",
                "has_device_token": True,
                "updated_at": "2026-10-21T17:00:00Z",
            }
        }
    )

    user_id: int = Field(..., description="ID del usuario propietario del dispositivo")
    device_token: str = Field(..., description="Token FCM registrado en el servidor")
    platform: str = Field(default="android", description="Plataforma registrada: android, ios o web")
    has_device_token: bool = Field(default=True, description="Indica que el dispositivo esta activo para push")
    updated_at: datetime = Field(..., description="Fecha y hora de registro en formato ISO-8601 UTC")


@router.post(
    "/device-token",
    response_model=DeviceTokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Registrar token FCM de dispositivo movil para notificaciones push",
    responses={
        400: {"model": ErrorResponse, "description": "Token de dispositivo vacio o plataforma invalida"},
        401: {"model": ErrorResponse, "description": "Token JWT ausente, invalido o expirado"},
    },
)
def register_device_token(
    payload: DeviceTokenRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DeviceTokenResponse:
    """
    Almacena de forma persistente e idempotente el token FCM / Android del dispositivo
    asociado al usuario autenticado para el envio de notificaciones push.
    """
    cleaned_token = (payload.device_token or "").strip()
    if not cleaned_token or len(cleaned_token) < 8 or len(cleaned_token) > 512 or any(c.isspace() for c in cleaned_token):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El token de dispositivo (device_token) es invalido o esta vacio.",
        )

    cleaned_platform = (payload.platform or "android").strip().lower()
    if cleaned_platform not in ALLOWED_PLATFORMS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Plataforma de dispositivo invalida. Valores permitidos: android, ios, web.",
        )

    now = datetime.now(UTC)
    current_user.device_token = cleaned_token

    existing = (
        db.query(DeviceToken)
        .filter(
            DeviceToken.user_id == current_user.id,
            DeviceToken.device_token == cleaned_token,
        )
        .first()
    )
    if existing:
        existing.platform = cleaned_platform
        existing.updated_at = now
        record = existing
    else:
        record = DeviceToken(
            user_id=current_user.id,
            device_token=cleaned_token,
            platform=cleaned_platform,
            updated_at=now,
        )
        db.add(record)

    db.commit()
    db.refresh(current_user)
    db.refresh(record)

    return DeviceTokenResponse(
        user_id=int(current_user.id),
        device_token=cleaned_token,
        platform=cleaned_platform,
        has_device_token=True,
        updated_at=ensure_utc_datetime(record.updated_at, fallback=now),
    )
