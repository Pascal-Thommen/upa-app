from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import asc, or_
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import Post, User
from ..schemas.event import EventResponse
from ..schemas.feed import ErrorResponse
from ..schemas.post import matches_group_filter, user_can_access_post

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
        filtered.append(EventResponse.from_orm_post(post))

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
    return EventResponse.from_orm_post(post)
