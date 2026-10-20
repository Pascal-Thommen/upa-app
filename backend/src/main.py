from fastapi import FastAPI, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from typing import Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_

from .config import settings
from .database import engine, Base, get_db
from .models import Post
from .schemas.post import NewsResponse
from .api.news import router as news_router
from .api.events import router as events_router
from .api.auth import router as auth_router
from .api.classroom import router as classroom_router
from .api.social import router as social_router
from .seed import seed_database

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Tabellen bei Start sicherstellen und Seed-Daten laden
    try:
        Base.metadata.create_all(bind=engine)
        seed_database()
    except Exception as e:
        print(f"[Lifespan Warning] Datenbank-Initialisierung: {e}")
    yield

app = FastAPI(
    title="UPA App API",
    description="Backend API fuer die Campus-Plattform der Universidad Paraguayo Alemana",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API-Router einbinden
app.include_router(auth_router)
app.include_router(news_router)
app.include_router(events_router)
app.include_router(classroom_router)
app.include_router(social_router)

@app.get("/health", tags=["Health"])
def health_check():
    return {
        "status": "healthy",
        "environment": settings.APP_ENV,
        "service": "upa-app-backend"
    }

@app.get("/api/v1/feed", tags=["Feed"])
def get_feed(
    group: Optional[str] = Query(None, description="Zielgruppe z.B. TIE"),
    db: Session = Depends(get_db)
):
    """Liefert Campus-News, Eilmeldungen und Posts basierend auf den Zielgruppen des Nutzers."""
    try:
        now = datetime.now(timezone.utc)
        banners = db.query(Post).filter(
            Post.is_pinned == True,
            or_(Post.expires_at == None, Post.expires_at > now)
        ).order_by(desc(Post.created_at)).all()

        all_posts = db.query(Post).filter(
            Post.is_news == True,
            or_(Post.expires_at == None, Post.expires_at > now)
        ).order_by(desc(Post.is_pinned), desc(Post.created_at)).limit(50).all()

        def matches_group(post_groups):
            if not group or not post_groups:
                return True
            return "ALL" in post_groups or group in post_groups

        urgent_banners = [
            NewsResponse.from_orm_post(b).model_dump()
            for b in banners if matches_group(b.target_groups)
        ]
        posts = [
            NewsResponse.from_orm_post(p).model_dump()
            for p in all_posts if matches_group(p.target_groups)
        ]

        return {
            "urgent_banners": urgent_banners,
            "posts": posts
        }
    except Exception:
        return {
            "urgent_banners": [],
            "posts": []
        }

@app.get("/api/v1/agenda", tags=["Agenda"])
def get_agenda():
    """Liefert Kalendertermine, Veranstaltungen und synchronisierte Classroom-Fristen."""
    return {
        "events": [],
        "deadlines": []
    }
