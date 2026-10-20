from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.news import router as news_router
from .config import settings
from .database import check_db_connection

app = FastAPI(
    title="UPA App API",
    description="Backend API fuer die Campus-Plattform der Universidad Paraguayo Alemana",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(news_router)


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
def get_feed():
    """Liefert Campus-News, Eilmeldungen und Posts basierend auf den Zielgruppen des Nutzers."""
    return {
        "urgent_banners": [],
        "posts": [],
    }


@app.get("/api/v1/agenda", tags=["Agenda"])
def get_agenda():
    """Liefert Kalendertermine, Veranstaltungen und synchronisierte Classroom-Fristen."""
    return {
        "events": [],
        "deadlines": [],
    }
