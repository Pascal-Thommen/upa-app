"""Events and Calendar API endpoints for UPA Campus Platform.

Exposes GET /api/events with chronological ordering, room and location metadata,
registration status, attendee counts, and target group filtering.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import String, and_, asc, cast, or_
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..models import EventRegistration, Post, User
from ..schemas.event import (
    EventRegistrationRequest,
    EventRegistrationResponse,
    EventResponse,
)

router = APIRouter(prefix="/api/events", tags=["Events"])


@router.get("", response_model=list[EventResponse])
def get_events(
    group: str | None = Query(
        None, description="Filter nach Zielgruppe oder Studiengang (z.B. TIE)"
    ),
    upcoming_only: bool = Query(
        True, description="Nur anstehende Termine und zukünftige Veranstaltungen anzeigen"
    ),
    limit: int = Query(
        20, ge=1, le=100, description="Maximale Anzahl der zurückzugebenden Termine"
    ),
    offset: int = Query(0, ge=0, description="Offset für Paginierung"),
    page: int | None = Query(
        None, ge=1, description="Optionale 1-basierte Seitennummer für Paginierung"
    ),
    db: Session = Depends(get_db),
):
    """Liefert alle Kalendereinträge und Termine.

    - Filtert nach is_event = True.
    - Sortiert chronologisch nach Veranstaltungsbeginn (event_start).
    - Berücksichtigt Zielgruppen und Studiengänge (?group=TIE).
    - Berechnet die Anzahl angemeldeter Teilnehmer (attendees_count) dynamisch.
    - Liefert Raum, Ort und Anmeldestatus (has_registration).
    """
    if page is not None and offset == 0:
        offset = (page - 1) * limit

    now = datetime.now(UTC)

    query = db.query(Post).filter(Post.is_event.is_(True))

    if upcoming_only:
        query = query.filter(
            or_(
                Post.event_end >= now,
                and_(Post.event_end.is_(None), Post.event_start >= now),
            )
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

    # Chronologische Sortierung nach Startzeitpunkt
    query = query.order_by(asc(Post.event_start).nullslast(), asc(Post.id))

    # Eager loading der Teilnehmer-Registrierungen zur Vermeidung von N+1 Abfragen
    query = query.options(selectinload(Post.registrations))

    posts = query.offset(offset).limit(limit).all()

    return [EventResponse.from_orm_post(post) for post in posts]


@router.get("/{event_id}", response_model=EventResponse)
def get_event_by_id(
    event_id: int,
    db: Session = Depends(get_db),
):
    """Liefert ein einzelnes Event anhand seiner ID."""
    post = (
        db.query(Post)
        .options(selectinload(Post.registrations))
        .filter(Post.id == event_id, Post.is_event.is_(True))
        .first()
    )
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evento con id {event_id} no encontrado",
        )
    return EventResponse.from_orm_post(post)


@router.post(
    "/{event_id}/register",
    response_model=EventRegistrationResponse,
    status_code=status.HTTP_200_OK,
)
def register_for_event(
    event_id: int,
    registration: EventRegistrationRequest,
    db: Session = Depends(get_db),
):
    """Registriert einen Nutzer für eine Veranstaltung mit 1-Klick An- oder Abmeldung."""
    post = db.query(Post).filter(Post.id == event_id, Post.is_event.is_(True)).first()
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evento con id {event_id} no encontrado",
        )

    if not post.has_registration:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Este evento no admite registros de participantes",
        )

    user = db.query(User).filter(User.id == registration.user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Usuario con id {registration.user_id} no encontrado",
        )

    existing_reg = (
        db.query(EventRegistration)
        .filter(
            EventRegistration.post_id == event_id,
            EventRegistration.user_id == registration.user_id,
        )
        .first()
    )

    if existing_reg:
        existing_reg.status = registration.status
        db.commit()
        db.refresh(existing_reg)
        return existing_reg

    new_reg = EventRegistration(
        post_id=event_id,
        user_id=registration.user_id,
        status=registration.status,
    )
    db.add(new_reg)
    db.commit()
    db.refresh(new_reg)
    return new_reg
