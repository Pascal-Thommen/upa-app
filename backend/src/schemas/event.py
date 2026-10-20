from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime

class EventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: Optional[str] = None
    event_start: Optional[datetime] = None
    event_end: Optional[datetime] = None
    location: Optional[str] = None
    has_registration: bool
    is_pinned: bool
    target_groups: List[str]
    image_url: Optional[str] = None
    permalink: Optional[str] = None
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
