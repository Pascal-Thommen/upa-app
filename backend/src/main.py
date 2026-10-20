from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from .config import settings
from .database import engine, Base
from .api.news import router as news_router
from .api.events import router as events_router
from .api.auth import router as auth_router
from .api.classroom import router as classroom_router
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

@app.get("/health", tags=["Health"])
def health_check():
    return {
        "status": "healthy",
        "environment": settings.APP_ENV,
        "service": "upa-app-backend"
    }
