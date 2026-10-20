"""Pydantic DTO schemas package for UPA App backend."""

from .event import (
    EventBase,
    EventCreate,
    EventRegistrationRequest,
    EventRegistrationResponse,
    EventResponse,
    EventUpdate,
)
from .post import NewsResponse, PostBase, PostCreate, PostUpdate

__all__ = [
    "PostBase",
    "PostCreate",
    "PostUpdate",
    "NewsResponse",
    "EventBase",
    "EventCreate",
    "EventUpdate",
    "EventResponse",
    "EventRegistrationRequest",
    "EventRegistrationResponse",
]
