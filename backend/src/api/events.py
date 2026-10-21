from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import asc, or_
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_admin
from ..database import get_db
from ..models import AdminAuditLog, EventRegistration, Post, User
from ..schemas.event import EventResponse, EventUpdate
from ..schemas.feed import ErrorResponse
from ..schemas.post import (
    DeleteResponse,
    ensure_utc_datetime,
    matches_group_filter,
    normalize_target_groups,
    user_can_access_post,
)

router = APIRouter(prefix="/api/events", tags=["Events"])


@router.get(
    "",
    response_model=list[EventResponse],
    summary="Listar eventos academicos e institucionales del calendario",
    responses={
        401: {"model": ErrorResponse, "description": "Token JWT ausente, invalido o expirado"},
    },
)
def get_events(
    group: str | None = Query(None, description="Filtro opcional por carrera o grupo (ej. TIE)"),
    upcoming_only: bool = Query(True, description="Mostrar unicamente eventos futuros o en curso"),
    limit: int = Query(20, ge=1, le=100, description="Cantidad maxima de eventos a retornar"),
    offset: int = Query(0, ge=0, description="Desplazamiento para paginacion"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[EventResponse]:
    """
    Retorna los eventos de calendario ordenados cronologicamente por fecha de inicio.
    Aplica filtrado estricto de autorizacion por rol y grupo en el servidor.
    """
    now = datetime.now(UTC)
    query = db.query(Post).filter(
        Post.is_event.is_(True),
        or_(Post.expires_at.is_(None), Post.expires_at > now),
    )

    if upcoming_only:
        query = query.filter(Post.event_start >= now)

    posts = query.order_by(asc(Post.event_start), asc(Post.id)).all()

    filtered: list[EventResponse] = []
    for post in posts:
        if not user_can_access_post(current_user, post.target_groups):
            continue
        if not matches_group_filter(post.target_groups, group):
            continue
        filtered.append(EventResponse.from_orm_post(post, current_user_id=current_user.id))

    return filtered[offset : offset + limit]


@router.get(
    "/{event_id}",
    response_model=EventResponse,
    summary="Obtener detalle de un evento por ID",
    responses={
        401: {"model": ErrorResponse, "description": "Token JWT ausente, invalido o expirado"},
        403: {"model": ErrorResponse, "description": "Sin permisos para el grupo destinatario"},
        404: {"model": ErrorResponse, "description": "Evento no encontrado"},
    },
)
def get_event_by_id(
    event_id: int = Path(..., ge=1, description="Identificador unico del evento"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EventResponse:
    """Retorna el detalle de un evento especifico verificando permisos de grupo en el servidor."""
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
    return EventResponse.from_orm_post(post, current_user_id=current_user.id)


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


@router.put(
    "/{event_id}",
    response_model=EventResponse,
    status_code=status.HTTP_200_OK,
    summary="Actualizar un evento existente (Solo Admin)",
    responses={
        400: {"model": ErrorResponse, "description": "Datos de actualizacion invalidos"},
        401: {"model": ErrorResponse, "description": "Token JWT ausente, invalido o expirado"},
        403: {"model": ErrorResponse, "description": "Permisos de administrador requeridos"},
        404: {"model": ErrorResponse, "description": "Evento no encontrado"},
    },
)
def update_event(
    payload: EventUpdate,
    event_id: int = Path(..., ge=1, description="Identificador unico del evento"),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> EventResponse:
    """
    Actualiza los campos de un evento institucional existente.
    Protegido: Exclusivo para administradores autorizados.
    """
    post = (
        db.query(Post)
        .filter(Post.id == event_id, Post.is_event.is_(True))
        .first()
    )
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evento no encontrado.",
        )

    if payload.title is not None:
        clean_title = payload.title.strip()
        if not clean_title:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El titulo del evento no puede estar vacio.",
            )
        post.title = clean_title

    new_content = payload.content if payload.content is not None else payload.description
    if new_content is not None:
        post.content = new_content.strip()

    new_caption = payload.caption if payload.caption is not None else payload.summary
    if new_caption is not None:
        post.caption = new_caption.strip()

    new_start = payload.event_start if payload.event_start is not None else post.event_start
    new_end = payload.event_end if payload.event_end is not None else post.event_end
    if new_start and new_end:
        if ensure_utc_datetime(new_end) < ensure_utc_datetime(new_start):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La fecha de finalizacion del evento no puede ser anterior a la fecha de inicio.",
            )

    if payload.event_start is not None:
        post.event_start = payload.event_start
    if payload.event_end is not None:
        post.event_end = payload.event_end
    if payload.location is not None:
        post.location = payload.location.strip()
    if payload.has_registration is not None:
        post.has_registration = payload.has_registration
    if payload.is_pinned is not None:
        post.is_pinned = payload.is_pinned
    if payload.is_news is not None:
        post.is_news = payload.is_news
    if payload.target_groups is not None:
        post.target_groups = normalize_target_groups(payload.target_groups)

    new_media_url = payload.media_url if payload.media_url is not None else payload.image_url
    if new_media_url is not None:
        post.media_url = new_media_url.strip()
    if payload.media_type is not None:
        post.media_type = payload.media_type.strip()
    if payload.permalink is not None:
        post.permalink = payload.permalink.strip()
    if payload.reminder_minutes_before is not None:
        post.reminder_minutes_before = payload.reminder_minutes_before
    if payload.expires_at is not None:
        post.expires_at = payload.expires_at

    audit = AdminAuditLog(
        admin_id=admin.id,
        action="UPDATE_EVENT",
        target_type="event",
        target_id=post.id,
        details={"title": post.title},
    )
    db.add(audit)
    db.commit()
    db.refresh(post)
    return EventResponse.from_orm_post(post, current_user_id=admin.id)


@router.delete(
    "/{event_id}",
    response_model=DeleteResponse,
    status_code=status.HTTP_200_OK,
    summary="Eliminar un evento existente (Solo Admin)",
    responses={
        401: {"model": ErrorResponse, "description": "Token JWT ausente, invalido o expirado"},
        403: {"model": ErrorResponse, "description": "Permisos de administrador requeridos"},
        404: {"model": ErrorResponse, "description": "Evento no encontrado"},
    },
)
def delete_event(
    event_id: int = Path(..., ge=1, description="Identificador unico del evento"),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> DeleteResponse:
    """
    Elimina permanentemente un evento del calendario y sus inscripciones asociadas.
    Protegido: Exclusivo para administradores autorizados.
    """
    post = (
        db.query(Post)
        .filter(Post.id == event_id, Post.is_event.is_(True))
        .first()
    )
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evento no encontrado.",
        )

    audit = AdminAuditLog(
        admin_id=admin.id,
        action="DELETE_EVENT",
        target_type="event",
        target_id=event_id,
        details={"title": post.title},
    )
    db.add(audit)
    db.delete(post)
    db.commit()
    return DeleteResponse(
        status="deleted",
        id=event_id,
        detail="Evento eliminado correctamente.",
    )
