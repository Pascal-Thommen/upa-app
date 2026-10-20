from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio

from .config import settings
from .database import engine, Base
from .api.news import router as news_router
from .api.events import router as events_router
from .api.auth import router as auth_router
from .api.classroom import router as classroom_router
from .api.feed import router as feed_router
from .seed import seed_database
from .services.scheduler import start_feed_sync_scheduler, stop_feed_sync_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Tabellen bei Start sicherstellen und Seed-Daten laden
    try:
        Base.metadata.create_all(bind=engine)
        seed_database()
    except Exception as e:
        print(f"[Lifespan Warning] Datenbank-Initialisierung: {e}")

    # Periodischen Feed-Synchronisations-Worker starten
    scheduler_task = start_feed_sync_scheduler()

    yield

    # Periodischen Worker ordnungsgemäß stoppen
    stop_feed_sync_scheduler()
    if scheduler_task and not scheduler_task.done():
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass


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

# API-Router einbinden
app.include_router(auth_router)
app.include_router(news_router)
app.include_router(events_router)
app.include_router(classroom_router)
app.include_router(feed_router)


@app.get("/health", tags=["Health"])
def health_check():
    return {
        "status": "healthy",
        "environment": settings.APP_ENV,
        "service": "upa-app-backend",
    }


@app.get("/api/v1/agenda", tags=["Agenda"])
def get_agenda():
    """Liefert Kalendertermine, Veranstaltungen und synchronisierte Classroom-Fristen."""
    return {
        "events": [],
        "deadlines": [],
    }
