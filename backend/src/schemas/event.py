"""Pydantic schemas and DTO models for Events and Calendar API.

Adheres strictly to the UPA App contract and Zero Mock Doktrin.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EventBase(BaseModel):
    """Base schema for campus events and calendar appointments."""

    title: str = Field(..., max_length=255, description="Titel der Veranstaltung")
    caption: str | None = Field(None, description="Thema oder Kurzbeschreibung")
    content: str | None = Field(None, description="Vollständige Veranstaltungsbeschreibung")
    post_type: str = Field("MANUAL", description="Beitragstyp: MANUAL, GOOGLE_CLASSROOM")
    is_news: bool = Field(True, description="Markiert Event auch als News-Beitrag")
    is_event: bool = Field(True, description="Markiert Beitrag als Kalender-Event")
    event_start: datetime | None = Field(None, description="Startzeitpunkt")
    event_end: datetime | None = Field(None, description="Endzeitpunkt")
    location: str | None = Field(None, max_length=255, description="Veranstaltungsort")
    target_groups: list[str] = Field(default_factory=lambda: ["ALL"], description="Zielgruppen oder Studiengänge")
    has_registration: bool = Field(False, description="Aktiviert Teilnehmerregistrierung")
    reminder_minutes_before: int | None = Field(30, description="Erinnerungsvorlauf in Minuten")
    media_type: str | None = Field(None, description="Medientyp")
    media_url: str | None = Field(None, description="Event-Banner oder Bild-URL")


class EventCreate(EventBase):
    """Schema for creating a new event."""

    pass


class EventUpdate(BaseModel):
    """Schema for updating an existing event."""

    title: str | None = None
    caption: str | None = None
    content: str | None = None
    event_start: datetime | None = None
    event_end: datetime | None = None
    location: str | None = None
    target_groups: list[str] | None = None
    has_registration: bool | None = None
    media_url: str | None = None


class EventResponse(BaseModel):
    """Response DTO for GET /api/events items with full metadata and registration count."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    caption: str | None = None
    content: str | None = None
    post_type: str = "MANUAL"
    is_news: bool = True
    is_event: bool = True
    event_start: datetime | None = None
    event_end: datetime | None = None
    location: str | None = None
    target_groups: list[str] = Field(default_factory=lambda: ["ALL"])
    has_registration: bool = False
    media_type: str | None = None
    media_url: str | None = None
    image_url: str | None = None
    attendee_count: int = 0
    author_id: int | None = None
    created_at: datetime
    updated_at: datetime | None = None

    @classmethod
    def from_orm_post(cls, post: Any, attendee_count: int = 0) -> "EventResponse":
        img = post.media_url if post.media_url else None
        return cls(
            id=post.id,
            title=post.title,
            caption=post.caption,
            content=post.content,
            post_type=post.post_type or "MANUAL",
            is_news=post.is_news if post.is_news is not None else True,
            is_event=post.is_event if post.is_event is not None else True,
            event_start=post.event_start,
            event_end=post.event_end,
            location=post.location,
            target_groups=post.target_groups or ["ALL"],
            has_registration=post.has_registration if post.has_registration is not None else False,
            media_type=post.media_type,
            media_url=post.media_url,
            image_url=img,
            attendee_count=attendee_count,
            author_id=post.author_id,
            created_at=post.created_at,
            updated_at=post.updated_at,
        )
