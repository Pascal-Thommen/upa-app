from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..auth import get_current_user_optional
from ..database import get_db
from ..models import Post, User
from ..permissions import effective_permissions
from ..schemas.feed import FeedItemResponse, FeedResponse
from ..schemas.post import matches_group_filter, user_can_access_post
from .publications import record_post_views

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
    user_perms = set(effective_permissions(db, user)) if user is not None else set()

    banner_posts: list[Post] = []
    if user is not None:
        banners_query = (
            db.query(Post)
            .filter(
                Post.post_type == "EMERGENCY_BANNER",
                Post.is_news.is_(True),
                or_(Post.published_at.is_(None), Post.published_at <= now),
                or_(Post.expires_at.is_(None), Post.expires_at > now),
            )
            .order_by(Post.is_pinned.desc(), Post.created_at.desc())
        )

        for b in banners_query.all():
            if not user_can_access_post(user, b.target_groups, user_permissions=user_perms):
                continue
            if not matches_group_filter(b.target_groups, group):
                continue
            banner_posts.append(b)

    posts_query = db.query(Post).filter(
        Post.post_type != "EMERGENCY_BANNER",
        or_(Post.published_at.is_(None), Post.published_at <= now),
        or_(Post.expires_at.is_(None), Post.expires_at > now),
    )

    if user is None:
        posts_query = posts_query.filter(Post.post_type == "INSTAGRAM")
    else:
        posts_query = posts_query.filter(or_(Post.is_news.is_(True), Post.is_event.is_(True)))

    posts_query = posts_query.order_by(Post.is_pinned.desc(), Post.created_at.desc())

    filtered_posts: list[Post] = []
    for p in posts_query.all():
        if not user_can_access_post(user, p.target_groups, user_permissions=user_perms):
            continue
        if not matches_group_filter(p.target_groups, group):
            continue
        filtered_posts.append(p)

    paginated_posts = filtered_posts[offset : offset + limit]

    if user is not None:
        delivered_ids = [
            int(post_obj.id)
            for post_obj in (*banner_posts, *paginated_posts)
            if getattr(post_obj, "id", None) is not None
        ]
        if delivered_ids:
            record_post_views(db, delivered_ids, user.id)
            for post_obj in (*banner_posts, *paginated_posts):
                db.expire(post_obj, ["views"])

    current_user_id = user.id if user is not None else None
    banners = [FeedItemResponse.from_orm_post(b, current_user_id=current_user_id) for b in banner_posts]
    posts = [FeedItemResponse.from_orm_post(p, current_user_id=current_user_id) for p in paginated_posts]

    return FeedResponse(
        urgent_banners=banners,
        posts=posts,
    )
