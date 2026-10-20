from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime

class PostBase(BaseModel):
    title: str
    caption: Optional[str] = None
    content: Optional[str] = None
    post_type: str = "MANUAL"
    is_news: bool = True
    is_event: bool = False
    is_pinned: bool = False
    expires_at: Optional[datetime] = None
    target_groups: List[str] = ["ALL"]
    
    # Event fields
    event_start: Optional[datetime] = None
    event_end: Optional[datetime] = None
    location: Optional[str] = None
    has_registration: bool = False
    reminder_minutes_before: Optional[int] = 30
    
    # Instagram fields
    instagram_id: Optional[str] = None
    media_type: Optional[str] = None
    media_url: Optional[str] = None
    permalink: Optional[str] = None

class PostCreate(PostBase):
    pass

class NewsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    summary: Optional[str] = None
    content: Optional[str] = None
    post_type: str
    is_pinned: bool
    target_groups: List[str]
    instagram_id: Optional[str] = None
    image_url: Optional[str] = None
    media_url: Optional[str] = None
    media_type: Optional[str] = None
    permalink: Optional[str] = None
    created_at: datetime
    published_at: datetime

    @classmethod
    def from_orm_post(cls, post):
        summary_text = post.caption if post.caption else (post.content[:150] + "..." if post.content and len(post.content) > 150 else post.content)
        img = post.media_url if post.media_url else None
        pub_date = post.created_at
        return cls(
            id=post.id,
            title=post.title,
            summary=summary_text,
            content=post.content or post.caption,
            post_type=post.post_type,
            is_pinned=post.is_pinned,
            target_groups=post.target_groups or ["ALL"],
            instagram_id=post.instagram_id,
            image_url=img,
            media_url=img,
            media_type=post.media_type,
            permalink=post.permalink,
            created_at=post.created_at,
            published_at=pub_date
        )
