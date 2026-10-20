from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_, func
from typing import List, Optional
from datetime import datetime, timezone

from ..database import get_db
from ..models import Post
from ..schemas.post import NewsResponse

router = APIRouter(prefix="/api/news", tags=["News"])

@router.get("", response_model=List[NewsResponse])
def get_news(
    group: Optional[str] = Query(None, description="Filter nach Zielgruppe oder Studiengang (z.B. TIE)"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """
    Liefert alle aktiven News-Beiträge und Ankündigungen.
    Abgelaufene Eilmeldungen (expires_at) werden automatisch gefiltert.
    Angepinnte Beiträge (is_pinned) stehen ganz oben.
    """
    now = datetime.now(timezone.utc)
    
    query = db.query(Post).filter(
        Post.is_news == True,
        or_(Post.expires_at == None, Post.expires_at > now)
    )
    
    # Sortierung: zuerst angepinnte Beiträge, dann neueste zuerst
    query = query.order_by(desc(Post.is_pinned), desc(Post.created_at))
    
    posts = query.offset(offset).limit(limit).all()
    
    # Client-/Gruppenfilterung im Speicher für JSON-Listen
    result = []
    for post in posts:
        groups = post.target_groups or ["ALL"]
        if group:
            if "ALL" in groups or group in groups:
                result.append(NewsResponse.from_orm_post(post))
        else:
            result.append(NewsResponse.from_orm_post(post))
            
    return result
