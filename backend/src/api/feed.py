from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import desc, or_
from sqlalchemy.orm import Session

from ..auth import get_current_user_optional, require_admin
from ..database import get_db
from ..models import Post, User
from ..schemas.feed import FeedItemResponse, FeedResponse
from ..services.instagram import instagram_service

router = APIRouter(prefix="/api/v1/feed", tags=["Feed"])


@router.get("", response_model=FeedResponse)
def get_feed(
    group: str | None = Query(None, description="Filter nach Zielgruppe oder Studiengang (z.B. TIE)"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional)
):
    """
    Liefert den aggregierten Campus-Feed:
    - Ohne Authentifizierung: Ausschließlich öffentliche Instagram-Beiträge (@upalemana).
    - Mit Authentifizierung (UPA-Login): Eilmeldungen, interne Campus-News, Events und Instagram-Beiträge.
    Unterstützt Zielgruppenfilterung (z.B. ?group=TIE) und Pagination.
    """
    now = datetime.now(UTC)

    # 1. Urgent banners (Avisos de Emergencia) - nur für angemeldete Universitätsmitglieder
    banners = []
    if user is not None:
        banners_query = db.query(Post).filter(
            Post.post_type == "EMERGENCY_BANNER",
            Post.is_news.is_(True),
            or_(Post.expires_at.is_(None), Post.expires_at > now)
        ).order_by(desc(Post.is_pinned), desc(Post.created_at))

        raw_banners = banners_query.all()
        for b in raw_banners:
            groups = b.target_groups or ["ALL"]
            if not group or "ALL" in groups or group in groups:
                banners.append(FeedItemResponse.from_orm_post(b))

    # 2. Campus Posts (News, Instagram, Events)
    # Nicht angemeldete Nutzer erhalten strikt nur öffentliche Instagram-Posts
    posts_query = db.query(Post).filter(
        Post.post_type != "EMERGENCY_BANNER",
        or_(Post.expires_at.is_(None), Post.expires_at > now)
    )

    if user is None:
        posts_query = posts_query.filter(Post.post_type == "INSTAGRAM")
    else:
        posts_query = posts_query.filter(
            or_(Post.is_news.is_(True), Post.is_event.is_(True))
        )

    posts_query = posts_query.order_by(desc(Post.is_pinned), desc(Post.created_at))

    raw_posts = posts_query.all()
    filtered_posts = []
    for p in raw_posts:
        groups = p.target_groups or ["ALL"]
        if not group or "ALL" in groups or group in groups:
            filtered_posts.append(FeedItemResponse.from_orm_post(p))

    paginated_posts = filtered_posts[offset:offset + limit]

    return FeedResponse(
        urgent_banners=banners,
        posts=paginated_posts
    )


@router.post("/sync", status_code=status.HTTP_200_OK)
async def sync_feed(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    """
    Manuelle Synchronisation des Social Feeds (@upalemana).
    Geschützt: Nur autorisierte Administratoren dürfen den Sync ausführen.
    """
    result = await instagram_service.sync_instagram(db, author_id=admin.id)
    return result
