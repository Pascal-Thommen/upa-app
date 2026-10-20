"""Pydantic schemas and DTO models for Posts and News API.

Adheres strictly to the UPA App contract and Zero Mock Doktrin.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PostBase(BaseModel):
    """Base schema for campus posts, announcements, and news."""

    title: str = Field(..., max_length=255, description="Titel des Beitrags")
    caption: str | None = Field(None, description="Kurzer Anreißer oder Instagram-Bildunterschrift")
    content: str | None = Field(None, description="Vollständiger Beitragstext")
    post_type: str = Field("MANUAL", description="Beitragstyp: MANUAL, INSTAGRAM, EMERGENCY_BANNER")
    is_news: bool = Field(True, description="Markiert Beitrag als Campus-Nachricht")
    is_event: bool = Field(False, description="Markiert Beitrag als Kalender-Event")
    is_pinned: bool = Field(False, description="Heftet den Beitrag ganz oben an")
    is_urgent: bool = Field(False, description="Eilmeldung mit hoher Priorität")
    expires_at: datetime | None = Field(None, description="Ablaufdatum für temporäre Eilmeldungen")
    target_groups: list[str] = Field(default_factory=lambda: ["ALL"], description="Zielgruppen oder Studiengänge")

    # Kalender & Event-Daten
    event_start: datetime | None = Field(None, description="Startzeitpunkt bei Veranstaltungen")
    event_end: datetime | None = Field(None, description="Endzeitpunkt bei Veranstaltungen")
    location: str | None = Field(None, max_length=255, description="Veranstaltungsort")
    has_registration: bool = Field(False, description="Aktiviert 1-Klick An- und Abmeldung")
    reminder_minutes_before: int | None = Field(30, description="Erinnerungsvorlauf in Minuten")

    # Instagram Metadaten
    instagram_id: str | None = Field(None, max_length=100, description="Instagram Post ID")
    media_type: str | None = Field(None, description="Medientyp: IMAGE, VIDEO, CAROUSEL_ALBUM")
    media_url: str | None = Field(None, description="Direktlink zum Bild oder Video")
    permalink: str | None = Field(None, description="Permanenter Web-Link zum Beitrag")


class PostCreate(PostBase):
    """Schema for creating a new post."""

    pass


class PostUpdate(BaseModel):
    """Schema for partial updates to a post."""

    title: str | None = None
    caption: str | None = None
    content: str | None = None
    post_type: str | None = None
    is_news: bool | None = None
    is_event: bool | None = None
    is_pinned: bool | None = None
    is_urgent: bool | None = None
    expires_at: datetime | None = None
    target_groups: list[str] | None = None
    media_url: str | None = None
    permalink: str | None = None


class NewsResponse(BaseModel):
    """Response DTO for GET /api/news items with full metadata and serialization."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    summary: str | None = None
    content: str | None = None
    caption: str | None = None
    post_type: str = "MANUAL"
    is_news: bool = True
    is_event: bool = False
    is_pinned: bool = False
    is_urgent: bool = False
    expires_at: datetime | None = None
    target_groups: list[str] = Field(default_factory=lambda: ["ALL"])

    # Instagram & Medien Metadaten
    image_url: str | None = None
    instagram_id: str | None = None
    media_type: str | None = None
    media_url: str | None = None
    permalink: str | None = None

    # Autor & Zeitstempel
    author_id: int | None = None
    created_at: datetime
    published_at: datetime
    updated_at: datetime | None = None

    @classmethod
    def from_orm_post(cls, post: Any) -> "NewsResponse":
        """Maps SQLAlchemy Post model to NewsResponse DTO."""
        summary_text = (
            post.caption
            if post.caption
            else (
                post.content[:150] + "..."
                if post.content and len(post.content) > 150
                else post.content
            )
        )
        img = post.media_url if post.media_url else None
        pub_date = post.created_at

        return cls(
            id=post.id,
            title=post.title,
            summary=summary_text,
            content=post.content or post.caption,
            caption=post.caption,
            post_type=post.post_type or "MANUAL",
            is_news=post.is_news if post.is_news is not None else True,
            is_event=post.is_event if post.is_event is not None else False,
            is_pinned=post.is_pinned if post.is_pinned is not None else False,
            is_urgent=post.is_urgent if post.is_urgent is not None else False,
            expires_at=post.expires_at,
            target_groups=post.target_groups or ["ALL"],
            image_url=img,
            instagram_id=post.instagram_id,
            media_type=post.media_type,
            media_url=post.media_url,
            permalink=post.permalink,
            author_id=post.author_id,
            created_at=post.created_at,
            published_at=pub_date,
            updated_at=post.updated_at,
        )
