from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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


@app.get("/health", tags=["Health"])
def health_check():
    """Liveness probe verifying that the HTTP server process is running."""
    return {
        "status": "healthy",
        "environment": settings.APP_ENV,
        "service": "upa-app-backend",
    }


@app.get("/ready", tags=["Health"])
def readiness_check():
    """Readiness probe verifying that backend dependencies (database) are operational."""
    db_ok = check_db_connection()
    return {
        "status": "ready" if db_ok else "not_ready",
        "database": "connected" if db_ok else "unavailable",
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
