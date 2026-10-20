"""Events API endpoints for UPA Campus Platform.

Exposes GET /api/events with chronological sorting, target group filtering,
and registration metrics.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import String, cast, desc, or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import EventRegistration, Post
from ..schemas.event import EventResponse

router = APIRouter(prefix="/api/events", tags=["Events"])


@router.get("", response_model=list[EventResponse])
def get_events(
    group: str | None = Query(
        None, description="Filter nach Zielgruppe oder Studiengang (z.B. TIE)"
    ),
    upcoming_only: bool = Query(
        False, description="Nur zukünftige Veranstaltungen abrufen"
    ),
    limit: int = Query(
        50, ge=1, le=100, description="Maximale Anzahl der zurückzugebenden Events"
    ),
    offset: int = Query(0, ge=0, description="Offset für Paginierung"),
    page: int | None = Query(
        None, ge=1, description="Optionale 1-basierte Seitennummer für Paginierung"
    ),
    db: Session = Depends(get_db),
):
    """Liefert alle Campus-Veranstaltungen und Termine.

    - Filtert nach is_event = True.
    - Sortiert chronologisch nach event_start (oder created_at falls event_start None).
    - Ermittelt attendee_count aus realen EventRegistration-Einträgen.
    - Filtert optional nach Zielgruppe (?group=TIE).
    - Unterstützt Paginierung via limit / offset oder page.
    """
    if page is not None and offset == 0:
        offset = (page - 1) * limit

    query = db.query(Post).filter(Post.is_event.is_(True))

    if upcoming_only:
        now = datetime.now(UTC)
        query = query.filter(
            or_(
                Post.event_start.is_(None),
                Post.event_start >= now,
            )
        )

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

    # Sortierung: Veranstaltungen nach event_start asc (oder neueste zuerst falls kein event_start)
    query = query.order_by(
        Post.event_start.asc().nullslast(),
        desc(Post.created_at),
    )

    posts = query.offset(offset).limit(limit).all()

    # Berechne attendee_counts für zurückgegebene Events
    results = []
    for post in posts:
        count = (
            db.query(EventRegistration)
            .filter(
                EventRegistration.post_id == post.id,
                EventRegistration.status == "attending",
            )
            .count()
        )
        results.append(EventResponse.from_orm_post(post, attendee_count=count))

    return results


@router.get("/{event_id}", response_model=EventResponse)
def get_event_by_id(
    event_id: int,
    db: Session = Depends(get_db),
):
    """Liefert ein einzelnes Campus-Event anhand der ID."""
    post = db.query(Post).filter(Post.id == event_id, Post.is_event.is_(True)).first()
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evento con id {event_id} no encontrado",
        )
    count = (
        db.query(EventRegistration)
        .filter(
            EventRegistration.post_id == post.id,
            EventRegistration.status == "attending",
        )
        .count()
    )
    return EventResponse.from_orm_post(post, attendee_count=count)
