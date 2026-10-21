from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import desc, or_
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_admin
from ..database import get_db
from ..models import Post, User
from ..schemas.feed import ErrorResponse
from ..schemas.post import (
    NewsResponse,
    PostCreate,
    ensure_utc_datetime,
    matches_group_filter,
    normalize_target_groups,
    user_can_access_post,
)
from ..services.instagram import instagram_service

router = APIRouter(prefix="/api/news", tags=["News"])

ALLOWED_POST_TYPES = {"MANUAL", "INSTAGRAM", "EMERGENCY_BANNER"}


@router.get(
    "",
    response_model=list[NewsResponse],
    summary="Listar noticias y comunicados institucionales",
    responses={
        401: {"model": ErrorResponse, "description": "Token JWT ausente, invalido o expirado"},
    },
)
def get_news(
    group: str | None = Query(None, description="Filtro opcional por carrera o grupo (ej. TIE)"),
    limit: int = Query(20, ge=1, le=100, description="Cantidad maxima de elementos a retornar"),
    offset: int = Query(0, ge=0, description="Desplazamiento para paginacion"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[NewsResponse]:
    """
    Retorna las noticias y comunicados activos ordenados por prioridad (fijados primero) y fecha.
    Aplica filtrado estricto en servidor segun el rol y los grupos del usuario autenticado.
    """
    now = datetime.now(UTC)

    query = db.query(Post).filter(
        Post.is_news.is_(True),
        or_(Post.expires_at.is_(None), Post.expires_at > now),
    )

    posts = query.order_by(desc(Post.is_pinned), desc(Post.created_at)).all()

    filtered: list[NewsResponse] = []
    for post in posts:
        if not user_can_access_post(current_user, post.target_groups):
            continue
        if not matches_group_filter(post.target_groups, group):
            continue
        filtered.append(NewsResponse.from_orm_post(post))

    return filtered[offset : offset + limit]


@router.get(
    "/{post_id}",
    response_model=NewsResponse,
    summary="Obtener detalle de una noticia por ID",
    responses={
        401: {"model": ErrorResponse, "description": "Token JWT ausente, invalido o expirado"},
        403: {"model": ErrorResponse, "description": "Sin permisos para el grupo de esta noticia"},
        404: {"model": ErrorResponse, "description": "Noticia no encontrada o expirada"},
    },
)
def get_news_by_id(
    post_id: int = Path(..., ge=1, description="Identificador unico de la noticia"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NewsResponse:
    """Retorna una noticia especifica verificando permisos de grupo en el servidor."""
    now = datetime.now(UTC)
    post = (
        db.query(Post)
        .filter(
            Post.id == post_id,
            Post.is_news.is_(True),
            or_(Post.expires_at.is_(None), Post.expires_at > now),
        )
        .first()
    )
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Publicacion de noticias no encontrada.",
        )
    if not user_can_access_post(current_user, post.target_groups):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado: No pertenece al grupo destinatario de esta publicacion.",
        )
    return NewsResponse.from_orm_post(post)


@router.post(
    "",
    response_model=NewsResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear nueva publicacion o noticia institucional (Solo Admin)",
    responses={
        400: {"model": ErrorResponse, "description": "Datos de publicacion invalidos"},
        401: {"model": ErrorResponse, "description": "Token JWT ausente, invalido o expirado"},
        403: {"model": ErrorResponse, "description": "Permisos de administrador requeridos"},
    },
)
def create_news(
    payload: PostCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> NewsResponse:
    """
    Crea una nueva publicacion en el sistema.
    Protegido: Solo usuarios con rol 'admin' pueden publicar contenido.
    """
    clean_title = (payload.title or "").strip()
    if not clean_title:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El titulo de la publicacion no puede estar vacio.",
        )

    clean_type = (payload.post_type or "MANUAL").strip().upper()
    if clean_type not in ALLOWED_POST_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tipo de publicacion invalido. Valores permitidos: MANUAL, INSTAGRAM, EMERGENCY_BANNER.",
        )

    if payload.event_start and payload.event_end:
        if ensure_utc_datetime(payload.event_end) < ensure_utc_datetime(payload.event_start):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La fecha de finalizacion del evento no puede ser anterior a la fecha de inicio.",
            )

    new_post = Post(
        title=clean_title,
        caption=payload.caption.strip() if payload.caption else None,
        content=payload.content.strip() if payload.content else None,
        post_type=clean_type,
        is_news=payload.is_news,
        is_event=payload.is_event,
        is_pinned=payload.is_pinned,
        expires_at=payload.expires_at,
        event_start=payload.event_start,
        event_end=payload.event_end,
        location=payload.location.strip() if payload.location else None,
        target_groups=normalize_target_groups(payload.target_groups),
        has_registration=payload.has_registration,
        reminder_minutes_before=payload.reminder_minutes_before,
        instagram_id=payload.instagram_id.strip() if payload.instagram_id else None,
        media_type=payload.media_type.strip() if payload.media_type else None,
        media_url=payload.media_url.strip() if payload.media_url else None,
        permalink=payload.permalink.strip() if payload.permalink else None,
        author_id=admin.id,
    )
    db.add(new_post)
    db.commit()
    db.refresh(new_post)
    return NewsResponse.from_orm_post(new_post)


@router.post(
    "/sync-instagram",
    status_code=status.HTTP_200_OK,
    summary="Sincronizar publicaciones de Instagram manualmente (Solo Admin)",
    responses={
        401: {"model": ErrorResponse, "description": "Token JWT ausente, invalido o expirado"},
        403: {"model": ErrorResponse, "description": "Permisos de administrador requeridos"},
    },
)
async def sync_instagram_posts(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> dict[str, Any]:
    """
    Ejecuta la sincronizacion manual de publicaciones de Instagram (@upalemana).
    Protegido: Solo administradores autorizados.
    """
    result = await instagram_service.sync_instagram(db, author_id=admin.id)
    return result
