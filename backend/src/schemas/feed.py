from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FeedItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    caption: str | None = None
    content: str | None = None
    summary: str | None = None
    post_type: str
    is_news: bool
    is_event: bool
    is_pinned: bool
    expires_at: datetime | None = None
    event_start: datetime | None = None
    event_end: datetime | None = None
    location: str | None = None
    has_registration: bool = False
    target_groups: list[str] = ["ALL"]
    instagram_id: str | None = None
    media_type: str | None = None
    media_url: str | None = None
    image_url: str | None = None
    permalink: str | None = None
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
    urgent_banners: list[FeedItemResponse]
    posts: list[FeedItemResponse]
