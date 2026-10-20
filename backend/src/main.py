import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from .api.auth import router as auth_router
from .api.classroom import router as classroom_router
from .api.events import router as events_router
from .api.feed import router as feed_router
from .api.news import router as news_router
from .auth import get_current_user_optional
from .config import settings
from .database import Base, engine, get_db
from .models import Post, User
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


@app.get("/api/v1/app-state", tags=["Mobile App API"])
def get_app_state(
    current_user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """Liefert das voll aggregierte JSON-Datenpaket fuer die mobile UPA App."""
    posts = (
        db.query(Post)
        .order_by(Post.is_pinned.desc(), Post.created_at.desc())
        .limit(20)
        .all()
    )
    user_data = None
    if current_user:
        user_data = {
            "id": current_user.id,
            "email": current_user.email,
            "full_name": current_user.full_name,
            "role": current_user.role,
            "groups": current_user.groups if current_user.email == "pascal.thommen@upa.edu.py" else [],
        }
    return {
        "portal": "UPA Mobile Campus Platform",
        "api_version": "1.0.0",
        "user": user_data,
        "feed": [
            {
                "id": p.id,
                "title": p.title,
                "summary": p.caption or p.content or "",
                "image_url": p.image_url,
                "permalink": p.permalink,
                "published_at": p.published_at.isoformat() if p.published_at else None,
            }
            for p in posts
        ],
    }


# Static Dashboard Web-Admin Mounten
candidate_static_dirs = [
    Path(__file__).resolve().parent / "static",
    Path(__file__).resolve().parent.parent.parent / "web-admin",
    Path("/app/src/static"),
    Path("/app/web-admin"),
]
active_static_dir = None
for candidate in candidate_static_dirs:
    if candidate.exists() and (candidate / "index.html").exists():
        active_static_dir = candidate
        break

if active_static_dir:
    app.mount("/dashboard", StaticFiles(directory=str(active_static_dir), html=True), name="dashboard")
    app.mount("/admin", StaticFiles(directory=str(active_static_dir), html=True), name="admin")


@app.get("/", include_in_schema=False)
def root():
    if active_static_dir:
        return RedirectResponse(url="/dashboard/")
    return {
        "status": "healthy",
        "service": "upa-app-backend",
        "docs": "/docs",
    }
