from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import desc, or_
from sqlalchemy.orm import Session

from ..auth import require_admin
from ..database import get_db
from ..models import Post, User
from ..schemas.post import NewsResponse, PostCreate
from ..services.instagram import instagram_service

router = APIRouter(prefix="/api/news", tags=["News"])

@router.get("", response_model=list[NewsResponse])
def get_news(
    group: str | None = Query(None, description="Filter nach Zielgruppe oder Studiengang (z.B. TIE)"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """
    Liefert alle aktiven News-Beiträge und Ankündigungen.
    Abgelaufene Eilmeldungen (expires_at) werden automatisch gefiltert.
    Angepinnte Beiträge (is_pinned) stehen ganz oben.
    """
    now = datetime.now(UTC)
    
    query = db.query(Post).filter(
        Post.is_news.is_(True),
        or_(Post.expires_at.is_(None), Post.expires_at > now)
    )
    
    query = query.order_by(desc(Post.is_pinned), desc(Post.created_at))
    posts = query.offset(offset).limit(limit).all()
    
    result = []
    for post in posts:
        groups = post.target_groups or ["ALL"]
        if group:
            if "ALL" in groups or group in groups:
                result.append(NewsResponse.from_orm_post(post))
        else:
            result.append(NewsResponse.from_orm_post(post))
            
    return result

@router.post("", response_model=NewsResponse, status_code=status.HTTP_201_CREATED)
def create_news(
    payload: PostCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    """
    Erstellt einen neuen Beitrag.
    Geschützt: Nur Benutzer mit der Rolle 'admin' dürfen Beiträge veröffentlichen.
    """
    new_post = Post(
        title=payload.title,
        caption=payload.caption,
        content=payload.content,
        post_type=payload.post_type,
        is_news=payload.is_news,
        is_event=payload.is_event,
        is_pinned=payload.is_pinned,
        expires_at=payload.expires_at,
        event_start=payload.event_start,
        event_end=payload.event_end,
        location=payload.location,
        target_groups=payload.target_groups or ["ALL"],
        has_registration=payload.has_registration,
        reminder_minutes_before=payload.reminder_minutes_before,
        instagram_id=payload.instagram_id,
        media_type=payload.media_type,
        media_url=payload.media_url,
        permalink=payload.permalink,
        author_id=admin.id
    )
    db.add(new_post)
    db.commit()
    db.refresh(new_post)
    return NewsResponse.from_orm_post(new_post)

@router.post("/sync-instagram", status_code=status.HTTP_200_OK)
async def sync_instagram_posts(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
) -> dict[str, Any]:
    """
    Manuelle Synchronisation der Instagram-Beiträge (@upalemana).
    Geschützt: Nur autorisierte Administratoren dürfen die Synchronisation auslösen.
    """
    result = await instagram_service.sync_instagram(db, author_id=admin.id)
    return result
