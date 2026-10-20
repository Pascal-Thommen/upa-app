from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_
from typing import Optional
from datetime import datetime, timezone

from ..database import get_db
from ..models import Post, User
from ..schemas.feed import FeedResponse, FeedItemResponse
from ..services.instagram import instagram_service
from ..auth import require_admin

router = APIRouter(prefix="/api/v1/feed", tags=["Feed"])


@router.get("", response_model=FeedResponse)
def get_feed(
    group: Optional[str] = Query(None, description="Filter nach Zielgruppe oder Studiengang (z.B. TIE)"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """
    Liefert den aggregierten Campus-Feed:
    - urgent_banners: Aktive Eilmeldungen (EMERGENCY_BANNER), solange nicht abgelaufen.
    - posts: Reguläre News, Campus-Events und synchronisierte Instagram-Beiträge (@upalemana).
    Unterstützt Zielgruppenfilterung (z.B. ?group=TIE) und Pagination.
    """
    now = datetime.now(timezone.utc)

    # 1. Urgent banners (Avisos de Emergencia)
    banners_query = db.query(Post).filter(
        Post.post_type == "EMERGENCY_BANNER",
        Post.is_news == True,
        or_(Post.expires_at == None, Post.expires_at > now)
    ).order_by(desc(Post.is_pinned), desc(Post.created_at))

    raw_banners = banners_query.all()
    banners = []
    for b in raw_banners:
        groups = b.target_groups or ["ALL"]
        if not group or "ALL" in groups or group in groups:
            banners.append(FeedItemResponse.from_orm_post(b))

    # 2. Campus Posts (News, Instagram, Events)
    posts_query = db.query(Post).filter(
        Post.post_type != "EMERGENCY_BANNER",
        or_(Post.is_news == True, Post.is_event == True),
        or_(Post.expires_at == None, Post.expires_at > now)
    ).order_by(desc(Post.is_pinned), desc(Post.created_at))

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
