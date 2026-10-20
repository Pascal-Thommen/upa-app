from datetime import datetime

from pydantic import BaseModel, ConfigDict


class EventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None = None
    event_start: datetime | None = None
    event_end: datetime | None = None
    location: str | None = None
    has_registration: bool
    is_pinned: bool
    target_groups: list[str]
    image_url: str | None = None
    permalink: str | None = None
    created_at: datetime

    @classmethod
    def from_orm_post(cls, post):
        desc = post.content or post.caption
        img = post.media_url if post.media_url else None
        return cls(
            id=post.id,
            title=post.title,
            description=desc,
            event_start=post.event_start,
            event_end=post.event_end,
            location=post.location,
            has_registration=post.has_registration,
            is_pinned=post.is_pinned,
            target_groups=post.target_groups or ["ALL"],
            image_url=img,
            permalink=post.permalink,
            created_at=post.created_at
        )
