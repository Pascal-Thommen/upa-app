from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import desc, or_
from sqlalchemy.orm import Session

from ..auth import get_current_user_optional, require_admin
from ..database import get_db
from ..models import Post, User
from ..schemas.feed import ErrorResponse, FeedItemResponse, FeedResponse
from ..schemas.post import matches_group_filter, user_can_access_post
from ..services.instagram import instagram_service

router = APIRouter(prefix="/api/v1/feed", tags=["Feed"])


@router.get(
    "",
    response_model=FeedResponse,
    summary="Obtener feed hibrido del campus (publico y autenticado)",
)
def get_feed(
    group: str | None = Query(None, description="Filtro opcional por carrera o grupo (ej. TIE)"),
    limit: int = Query(20, ge=1, le=100, description="Cantidad maxima de publicaciones"),
    offset: int = Query(0, ge=0, description="Desplazamiento para paginacion"),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
) -> FeedResponse:
    """
    Entrega el feed agregado del campus UPA:
    - Sin autenticacion: Unicamente publicaciones publicas de Instagram (@upalemana).
    - Con autenticacion: Avisos de emergencia, noticias internas, eventos e Instagram,
      filtrados estrictamente segun el rol y los grupos del usuario.
    """
    now = datetime.now(UTC)

    banners: list[FeedItemResponse] = []
    if user is not None:
        banners_query = (
            db.query(Post)
            .filter(
                Post.post_type == "EMERGENCY_BANNER",
                Post.is_news.is_(True),
                or_(Post.published_at.is_(None), Post.published_at <= now),
                or_(Post.expires_at.is_(None), Post.expires_at > now),
            )
            .order_by(desc(Post.is_pinned), desc(Post.created_at))
        )

        for b in banners_query.all():
            if not user_can_access_post(user, b.target_groups):
                continue
            if not matches_group_filter(b.target_groups, group):
                continue
            banners.append(FeedItemResponse.from_orm_post(b))

    posts_query = db.query(Post).filter(
        Post.post_type != "EMERGENCY_BANNER",
        or_(Post.published_at.is_(None), Post.published_at <= now),
        or_(Post.expires_at.is_(None), Post.expires_at > now),
    )

    if user is None:
        posts_query = posts_query.filter(Post.post_type == "INSTAGRAM")
    else:
        posts_query = posts_query.filter(or_(Post.is_news.is_(True), Post.is_event.is_(True)))

    posts_query = posts_query.order_by(desc(Post.is_pinned), desc(Post.created_at))

    filtered_posts: list[FeedItemResponse] = []
    for p in posts_query.all():
        if not user_can_access_post(user, p.target_groups):
            continue
        if not matches_group_filter(p.target_groups, group):
            continue
        filtered_posts.append(FeedItemResponse.from_orm_post(p))

    paginated_posts = filtered_posts[offset : offset + limit]

    return FeedResponse(
        urgent_banners=banners,
        posts=paginated_posts,
    )


@router.post(
    "/sync",
    status_code=status.HTTP_200_OK,
    summary="Sincronizar feed social de Instagram (Solo Admin)",
    responses={
        401: {"model": ErrorResponse, "description": "Token JWT ausente, invalido o expirado"},
        403: {"model": ErrorResponse, "description": "Permisos de administrador requeridos"},
    },
)
async def sync_feed(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> dict[str, Any]:
    """
    Sincronizacion manual del feed social (@upalemana).
    Protegido: Solo administradores autorizados.
    """
    result = await instagram_service.sync_instagram(db, author_id=admin.id)
    return result
