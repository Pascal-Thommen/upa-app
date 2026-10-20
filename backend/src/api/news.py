"""News API endpoints for UPA Campus Platform.

Exposes GET /api/news with target group filtering, priority sorting,
expiration handling, and pagination.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import String, cast, desc, or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Post
from ..schemas.post import NewsResponse

router = APIRouter(prefix="/api/news", tags=["News"])


@router.get("", response_model=list[NewsResponse])
def get_news(
    group: str | None = Query(
        None, description="Filter nach Zielgruppe oder Studiengang (z.B. TIE)"
    ),
    limit: int = Query(
        20, ge=1, le=100, description="Maximale Anzahl der zurückzugebenden Beiträge"
    ),
    offset: int = Query(0, ge=0, description="Offset für Paginierung"),
    page: int | None = Query(
        None, ge=1, description="Optionale 1-basierte Seitennummer für Paginierung"
    ),
    db: Session = Depends(get_db),
):
    """Liefert alle aktiven News-Beiträge und Campus-Mitteilungen.

    - Filtert nach is_news = True.
    - Schließt abgelaufene Eilmeldungen (expires_at < jetzt) automatisch aus.
    - Sortiert priorisiert: Zuerst angepinnte Beiträge (is_pinned), danach absteigend nach Erstelldatum (created_at).
    - Filtert nach Zielgruppe / Studiengang (?group=TIE), falls angegeben. Beiträge für ALL oder ohne Einschränkung werden stets mitgeliefert.
    - Unterstützt Paginierung via limit / offset oder page.
    """
    if page is not None and offset == 0:
        offset = (page - 1) * limit

    now = datetime.now(UTC)

    # Basisabfrage: nur News und nicht abgelaufene Beiträge
    query = db.query(Post).filter(
        Post.is_news.is_(True),
        or_(Post.expires_at.is_(None), Post.expires_at > now),
    )

    # Zielgruppenfilterung
    if group:
        group_clean = group.strip()
        query = query.filter(
            or_(
                cast(Post.target_groups, String).contains(f'"{group_clean}"'),
                cast(Post.target_groups, String).contains('"ALL"'),
                cast(Post.target_groups, String) == "[]",
                Post.target_groups.is_(None),
            )
        )

    # Sortierung: zuerst angepinnte Beiträge, dann neueste zuerst
    query = query.order_by(desc(Post.is_pinned), desc(Post.created_at))

    # Paginierung direkt auf Datenbankebene
    posts = query.offset(offset).limit(limit).all()

    return [NewsResponse.from_orm_post(post) for post in posts]


@router.get("/{post_id}", response_model=NewsResponse)
def get_news_by_id(
    post_id: int,
    db: Session = Depends(get_db),
):
    """Liefert eine einzelne Campus-Nachricht anhand der ID."""
    post = db.query(Post).filter(Post.id == post_id, Post.is_news.is_(True)).first()
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Noticia con id {post_id} no encontrada",
        )
    return NewsResponse.from_orm_post(post)
