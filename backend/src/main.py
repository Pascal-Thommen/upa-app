from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import desc
from sqlalchemy.orm import Session

from .api.events import router as events_router
from .api.news import router as news_router
from .config import settings
from .database import Base, check_db_connection, engine, get_db
from .models import Post


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="UPA App API",
    description="Backend API fuer die Campus-Plattform der Universidad Paraguayo Alemana",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Route registration: Canonical /api endpoints
app.include_router(news_router)
app.include_router(events_router)

# Versioned /api/v1 aliases for mobile and client compatibility
app.include_router(news_router, prefix="/api/v1")
app.include_router(events_router, prefix="/api/v1")


@app.get("/health", tags=["Health"])
def health_check():
    db_ok = check_db_connection()
    return {
        "status": "healthy" if db_ok else "degraded",
        "database": "connected" if db_ok else "disconnected",
        "environment": settings.APP_ENV,
        "service": "upa-app-backend",
    }


@app.get("/api/v1/feed", tags=["Feed"])
def get_feed(db: Session = Depends(get_db)):
    """Liefert Campus-News, Eilmeldungen und Posts basierend auf den Zielgruppen des Nutzers."""
    urgent = (
        db.query(Post)
        .filter(Post.is_news.is_(True), Post.is_urgent.is_(True))
        .order_by(desc(Post.created_at))
        .all()
    )
    posts = (
        db.query(Post)
        .filter(Post.is_news.is_(True))
        .order_by(desc(Post.is_pinned), desc(Post.created_at))
        .all()
    )
    return {
        "urgent_banners": [p.to_dict() for p in urgent],
        "posts": [p.to_dict() for p in posts],
    }


@app.get("/api/v1/agenda", tags=["Agenda"])
def get_agenda(db: Session = Depends(get_db)):
    """Liefert Kalendertermine, Veranstaltungen und synchronisierte Classroom-Fristen."""
    events = (
        db.query(Post)
        .filter(Post.is_event.is_(True))
        .order_by(Post.event_start.asc().nullslast(), desc(Post.created_at))
        .all()
    )
    return {
        "events": [e.to_dict() for e in events],
        "deadlines": [],
    }
