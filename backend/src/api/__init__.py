"""API routers package for UPA App backend."""

from .events import router as events_router
from .news import router as news_router

__all__ = ["news_router", "events_router"]
