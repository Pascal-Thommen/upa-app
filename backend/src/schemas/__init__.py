"""Pydantic DTO schemas package for UPA App backend."""

from .event import EventBase, EventCreate, EventResponse, EventUpdate
from .post import NewsResponse, PostBase, PostCreate, PostUpdate

__all__ = [
    "EventBase",
    "EventCreate",
    "EventResponse",
    "EventUpdate",
    "NewsResponse",
    "PostBase",
    "PostCreate",
    "PostUpdate",
]
