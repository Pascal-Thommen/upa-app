from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime


class FeedItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    caption: Optional[str] = None
    content: Optional[str] = None
    summary: Optional[str] = None
    post_type: str
    is_news: bool
    is_event: bool
    is_pinned: bool
    expires_at: Optional[datetime] = None
    event_start: Optional[datetime] = None
    event_end: Optional[datetime] = None
    location: Optional[str] = None
    has_registration: bool = False
    target_groups: List[str] = ["ALL"]
    instagram_id: Optional[str] = None
    media_type: Optional[str] = None
    media_url: Optional[str] = None
    image_url: Optional[str] = None
    permalink: Optional[str] = None
    created_at: datetime
    published_at: datetime

    @classmethod
    def from_orm_post(cls, post):
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
        return cls(
            id=post.id,
            title=post.title,
            caption=post.caption,
            content=post.content or post.caption,
            summary=summary_text,
            post_type=post.post_type,
            is_news=post.is_news,
            is_event=post.is_event,
            is_pinned=post.is_pinned,
            expires_at=post.expires_at,
            event_start=post.event_start,
            event_end=post.event_end,
            location=post.location,
            has_registration=post.has_registration,
            target_groups=post.target_groups or ["ALL"],
            instagram_id=post.instagram_id,
            media_type=post.media_type,
            media_url=img,
            image_url=img,
            permalink=post.permalink,
            created_at=post.created_at,
            published_at=post.created_at,
        )


class FeedResponse(BaseModel):
    urgent_banners: List[FeedItemResponse]
    posts: List[FeedItemResponse]
