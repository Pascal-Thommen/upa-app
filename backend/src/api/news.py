from typing import Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from ..auth import require_editor
from ..database import get_db
from ..models import User
from ..schemas.feed import ErrorResponse
from ..services.instagram import instagram_service

router = APIRouter(prefix="/api/news", tags=["News"])


@router.post(
    "/sync-instagram",
    status_code=status.HTTP_200_OK,
    summary="Sincronizar publicaciones de Instagram manualmente",
    responses={
        401: {"model": ErrorResponse, "description": "Token JWT ausente, invalido o expirado"},
        403: {"model": ErrorResponse, "description": "Permisos de administrador o redaccion requeridos"},
    },
)
async def sync_instagram_posts(
    db: Session = Depends(get_db),
    admin: User = Depends(require_editor),
) -> dict[str, Any]:
    """
    Ejecuta la sincronizacion manual de publicaciones de Instagram (@upalemana).
    Protegido: Exclusivo para administradores o redaccion.
    """
    return await instagram_service.sync_instagram(db, author_id=admin.id)
