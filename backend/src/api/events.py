from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import EventRegistration, Post, User
from ..schemas.event import EventResponse
from ..schemas.feed import ErrorResponse
from ..schemas.post import user_can_access_post

router = APIRouter(prefix="/api/events", tags=["Events"])


@router.post(
    "/{event_id}/register",
    response_model=EventResponse,
    status_code=status.HTTP_200_OK,
    summary="Inscribirse a un evento institucional (RSVP)",
    responses={
        401: {"model": ErrorResponse, "description": "Token JWT ausente, invalido o expirado"},
        403: {"model": ErrorResponse, "description": "Sin permisos para el grupo destinatario del evento"},
        404: {"model": ErrorResponse, "description": "Evento no encontrado"},
    },
)
def register_for_event(
    event_id: int = Path(..., ge=1, description="Identificador unico del evento"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EventResponse:
    """
    Registra de forma vinculante e idempotente la asistencia del usuario autenticado al evento
    en la tabla event_registrations y retorna el estado actualizado del evento.
    """
    now = datetime.now(UTC)
    post = (
        db.query(Post)
        .filter(
            Post.id == event_id,
            Post.is_event.is_(True),
            or_(Post.expires_at.is_(None), Post.expires_at > now),
        )
        .first()
    )
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evento no encontrado.",
        )
    if not user_can_access_post(current_user, post.target_groups):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado: No pertenece al grupo destinatario de este evento.",
        )

    existing = (
        db.query(EventRegistration)
        .filter(
            EventRegistration.post_id == event_id,
            EventRegistration.user_id == current_user.id,
        )
        .first()
    )
    if existing:
        if existing.status != "attending":
            existing.status = "attending"
            existing.updated_at = now
    else:
        registration = EventRegistration(
            post_id=event_id,
            user_id=current_user.id,
            status="attending",
        )
        db.add(registration)

    db.commit()
    db.refresh(post)
    return EventResponse.from_orm_post(post, current_user_id=current_user.id)


@router.delete(
    "/{event_id}/register",
    response_model=EventResponse,
    status_code=status.HTTP_200_OK,
    summary="Cancelar inscripcion a un evento institucional (RSVP)",
    responses={
        401: {"model": ErrorResponse, "description": "Token JWT ausente, invalido o expirado"},
        403: {"model": ErrorResponse, "description": "Sin permisos para el grupo destinatario del evento"},
        404: {"model": ErrorResponse, "description": "Evento no encontrado"},
    },
)
def unregister_from_event(
    event_id: int = Path(..., ge=1, description="Identificador unico del evento"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EventResponse:
    """
    Cancela la inscripcion del usuario autenticado en el evento indicado
    eliminando el registro de event_registrations y retornando el evento actualizado.
    """
    now = datetime.now(UTC)
    post = (
        db.query(Post)
        .filter(
            Post.id == event_id,
            Post.is_event.is_(True),
            or_(Post.expires_at.is_(None), Post.expires_at > now),
        )
        .first()
    )
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evento no encontrado.",
        )
    if not user_can_access_post(current_user, post.target_groups):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado: No pertenece al grupo destinatario de este evento.",
        )

    existing = (
        db.query(EventRegistration)
        .filter(
            EventRegistration.post_id == event_id,
            EventRegistration.user_id == current_user.id,
        )
        .first()
    )
    if existing:
        db.delete(existing)
        db.commit()
        db.refresh(post)

    return EventResponse.from_orm_post(post, current_user_id=current_user.id)
