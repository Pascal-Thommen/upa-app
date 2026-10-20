"""Pydantic schemas and DTO models for Events and Calendar API.

Adheres strictly to the UPA App contract and Zero Mock Doktrin.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EventBase(BaseModel):
    """Base schema for calendar events and appointments."""

    title: str = Field(..., max_length=255, description="Titel der Veranstaltung oder des Termins")
    description: str | None = Field(None, description="Beschreibung oder Inhalt des Termins")
    content: str | None = Field(None, description="Ausführlicher Beschreibungstext")
    caption: str | None = Field(None, description="Kurzbeschreibung oder Anreißer")
    event_start: datetime | None = Field(None, description="Beginn des Termins")
    event_end: datetime | None = Field(None, description="Ende des Termins")
    location: str | None = Field(None, max_length=255, description="Veranstaltungsort oder Raum")
    has_registration: bool = Field(False, description="Aktiviert Teilnehmerregistrierung")
    is_event: bool = Field(True, description="Markiert den Beitrag als Kalender-Event")
    is_pinned: bool = Field(False, description="Heftet den Termin oben an")
    target_groups: list[str] = Field(default_factory=lambda: ["ALL"], description="Zielgruppen oder Studiengänge")
    reminder_minutes_before: int | None = Field(30, description="Erinnerungsvorlauf in Minuten")
    media_url: str | None = Field(None, description="Link zu Veranstaltungsbanner oder Bild")
    permalink: str | None = Field(None, description="Weblink zur Veranstaltung")


class EventCreate(EventBase):
    """Schema for creating a new event."""

    pass


class EventUpdate(BaseModel):
    """Schema for updating an existing event."""

    title: str | None = None
    description: str | None = None
    content: str | None = None
    caption: str | None = None
    event_start: datetime | None = None
    event_end: datetime | None = None
    location: str | None = None
    has_registration: bool | None = None
    is_pinned: bool | None = None
    target_groups: list[str] | None = None
    reminder_minutes_before: int | None = None
    media_url: str | None = None
    permalink: str | None = None


class EventResponse(BaseModel):
    """Response DTO for GET /api/events with date, room, registration status and attendee counts."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None = None
    content: str | None = None
    caption: str | None = None
    event_start: datetime | None = None
    event_end: datetime | None = None
    location: str | None = None
    room: str | None = None
    has_registration: bool = False
    attendees_count: int = 0
    is_event: bool = True
    is_pinned: bool = False
    target_groups: list[str] = Field(default_factory=lambda: ["ALL"])
    reminder_minutes_before: int | None = 30
    image_url: str | None = None
    media_type: str | None = None
    media_url: str | None = None
    permalink: str | None = None
    author_id: int | None = None
    created_at: datetime
    updated_at: datetime | None = None

    @classmethod
    def from_orm_post(cls, post: Any, attendees_count: int | None = None) -> "EventResponse":
        """Maps SQLAlchemy Post model to EventResponse DTO."""
        desc = (
            post.content
            if post.content
            else (post.caption if post.caption else post.title)
        )
        img = post.media_url if getattr(post, "media_url", None) else None
        loc = getattr(post, "location", None)

        if attendees_count is None:
            regs = getattr(post, "registrations", None)
            if regs:
                attendees_count = sum(
                    1 for r in regs if getattr(r, "status", None) == "attending"
                )
            else:
                attendees_count = 0

        return cls(
            id=post.id,
            title=post.title,
            description=desc,
            content=getattr(post, "content", None),
            caption=getattr(post, "caption", None),
            event_start=post.event_start,
            event_end=post.event_end,
            location=loc,
            room=loc,
            has_registration=post.has_registration if post.has_registration is not None else False,
            attendees_count=attendees_count,
            is_event=post.is_event if post.is_event is not None else True,
            is_pinned=post.is_pinned if post.is_pinned is not None else False,
            target_groups=post.target_groups or ["ALL"],
            reminder_minutes_before=getattr(post, "reminder_minutes_before", 30),
            image_url=img,
            media_type=getattr(post, "media_type", None),
            media_url=post.media_url,
            permalink=getattr(post, "permalink", None),
            author_id=getattr(post, "author_id", None),
            created_at=post.created_at,
            updated_at=getattr(post, "updated_at", None),
        )


class EventRegistrationRequest(BaseModel):
    """Schema for registering or modifying attendance to an event."""

    user_id: int = Field(..., description="ID des Studierenden oder Nutzers")
    status: str = Field("attending", description="Teilnahmestatus: attending oder declined")


class EventRegistrationResponse(BaseModel):
    """Response DTO for event registration confirmation."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    post_id: int
    user_id: int
    status: str
    created_at: datetime
    updated_at: datetime | None = None
