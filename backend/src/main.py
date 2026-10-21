import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import Depends, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import desc, or_
from sqlalchemy.orm import Session

from .api.auth import (
    _derive_full_name,
    _filter_google_groups_for_privacy,
    _filter_user_groups_for_privacy,
)
from .api.auth import (
    router as auth_router,
)
from .api.classroom import router as classroom_router
from .api.events import router as events_router
from .api.feed import router as feed_router
from .api.news import router as news_router
from .auth import get_current_user_optional
from .config import settings
from .database import Base, engine, get_db
from .models import Post, User
from .schemas.feed import (
    AgendaResponse,
    AppStateFeedItem,
    AppStateResponse,
    AppStateUser,
    HealthResponse,
)
from .schemas.post import matches_group_filter, user_can_access_post
from .seed import seed_database
from .services.scheduler import start_feed_sync_scheduler, stop_feed_sync_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        Base.metadata.create_all(bind=engine)
        seed_database()
    except Exception as e:
        print(f"[Lifespan Warning] Inicializacion de base de datos: {e}")

    scheduler_task = start_feed_sync_scheduler()

    yield

    stop_feed_sync_scheduler()
    if scheduler_task and not scheduler_task.done():
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="UPA App API",
    description=(
        "API REST oficial para la Plataforma Universitaria de la Universidad Paraguayo Alemana (UPA). "
        "Incluye autenticacion OAuth 2.0 y Dev-Login JWT, noticias, calendario de eventos, "
        "sincronizacion con Google Classroom y feed hibrido de Instagram."
    ),
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

app.include_router(auth_router)
app.include_router(news_router)
app.include_router(events_router)
app.include_router(classroom_router)
app.include_router(feed_router)


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["Health"],
    summary="Verificar estado operativo del servicio",
)
def health_check() -> HealthResponse:
    """Verifica la disponibilidad operativa del microservicio backend."""
    return HealthResponse(
        status="healthy",
        environment=settings.APP_ENV,
        service="upa-app-backend",
    )


@app.get(
    "/api/v1/agenda",
    response_model=AgendaResponse,
    tags=["Agenda"],
    summary="Obtener estructura consolidada de agenda y plazos",
)
def get_agenda() -> AgendaResponse:
    """Retorna la estructura base de eventos de calendario y plazos sincronizados."""
    return AgendaResponse(
        events=[],
        deadlines=[],
    )


@app.get(
    "/api/v1/app-state",
    response_model=AppStateResponse,
    tags=["Mobile App API"],
    summary="Obtener estado inicial consolidado para la aplicacion movil",
)
def get_app_state(
    group: str | None = Query(None, description="Filtro opcional por carrera o grupo (ej. TIE)"),
    limit: int = Query(20, ge=1, le=100, description="Cantidad maxima de publicaciones en el feed"),
    current_user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> AppStateResponse:
    """
    Entrega el paquete JSON consolidado para la carga inicial de la app movil UPA.
    Garantiza ausencia de valores nulos en los elementos del feed y aplica filtrado
    estricto en servidor segun autenticacion, rol y pertenencia a grupos.
    """
    now = datetime.now(UTC)

    query = db.query(Post).filter(
        or_(Post.expires_at.is_(None), Post.expires_at > now)
    )
    if current_user is None:
        query = query.filter(Post.post_type == "INSTAGRAM")

    raw_posts = query.order_by(desc(Post.is_pinned), desc(Post.created_at)).all()

    filtered_feed: list[AppStateFeedItem] = []
    for p in raw_posts:
        if not user_can_access_post(current_user, p.target_groups):
            continue
        if not matches_group_filter(p.target_groups, group):
            continue
        filtered_feed.append(AppStateFeedItem.from_orm_post(p))
        if len(filtered_feed) >= limit:
            break

    user_data: AppStateUser | None = None
    if current_user is not None:
        clean_email = (current_user.email or "").strip().lower()
        clean_name = (current_user.full_name or "").strip() or _derive_full_name(clean_email)
        clean_role = (current_user.role or "user").strip() or "user"
        user_data = AppStateUser(
            id=int(current_user.id),
            email=clean_email,
            full_name=clean_name,
            role=clean_role,
            groups=_filter_user_groups_for_privacy(clean_email, current_user.groups),
            google_groups=[
                g.model_dump()
                for g in _filter_google_groups_for_privacy(clean_email, current_user.google_groups)
            ],
            has_classroom_token=bool(
                current_user.classroom_token and str(current_user.classroom_token).strip()
            ),
        )

    return AppStateResponse(
        portal="UPA Mobile Campus Platform",
        api_version="1.0.0",
        authenticated=current_user is not None,
        user=user_data,
        feed=filtered_feed,
    )


# Montaje del portal estatico Web-Admin
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
