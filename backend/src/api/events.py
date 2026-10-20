from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import asc
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Post
from ..schemas.event import EventResponse

router = APIRouter(prefix="/api/events", tags=["Events"])

@router.get("", response_model=list[EventResponse])
def get_events(
    group: str | None = Query(None, description="Filter nach Zielgruppe oder Studiengang (z.B. TIE)"),
    upcoming_only: bool = Query(True, description="Nur zukünftige Termine anzeigen"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """
    Liefert alle Kalendereinträge und Veranstaltungen.
    Sortiert chronologisch nach Veranstaltungsbeginn (event_start).
    """
    query = db.query(Post).filter(Post.is_event.is_(True))
    
    if upcoming_only:
        now = datetime.now(UTC)
        # Termine, die noch nicht begonnen haben oder in der Zukunft liegen
        query = query.filter(Post.event_start >= now)
        
    query = query.order_by(asc(Post.event_start))
    posts = query.offset(offset).limit(limit).all()
    
    result = []
    for post in posts:
        groups = post.target_groups or ["ALL"]
        if group:
            if "ALL" in groups or group in groups:
                result.append(EventResponse.from_orm_post(post))
        else:
            result.append(EventResponse.from_orm_post(post))
            
    return result
