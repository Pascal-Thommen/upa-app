import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import Depends, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import asc, desc, or_
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException

from .api.auth import (
    _derive_full_name,
    _filter_google_groups_for_privacy,
    _filter_user_groups_for_privacy,
)
from .api.auth import (
    router as auth_router,
)
from .api.classroom import fetch_user_classroom_deadlines
from .api.classroom import router as classroom_router
from .api.events import router as events_router
from .api.feed import router as feed_router
from .api.media import UploadsStaticFiles, get_upload_dir
from .api.media import router as media_router
from .api.news import router as news_router
from .api.users import router as users_router
from .auth import get_current_user_optional
from .config import settings
from .database import Base, engine, ensure_schema_upgrades, get_db
from .models import Post, User
from .schemas.classroom import ClassroomDeadlineResponse
from .schemas.event import EventResponse
from .schemas.feed import (
    AgendaItemResponse,
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
        ensure_schema_upgrades(engine)
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
        "inscripcion RSVP, sincronizacion con Google Classroom con auto-refresh y notificaciones push."
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
app.include_router(users_router)
app.include_router(news_router)
app.include_router(events_router)
app.include_router(classroom_router)
app.include_router(feed_router)
app.include_router(media_router)


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


def _query_upcoming_events(
    db: Session,
    current_user: User | None,
    group: str | None = None,
    upcoming_only: bool = True,
    limit: int = 50,
) -> list[EventResponse]:
    """Consulta eventos reales de la base de datos ordenados cronologicamente con filtrado de acceso."""
    now = datetime.now(UTC)
    query = db.query(Post).filter(
        Post.is_event.is_(True),
        or_(Post.expires_at.is_(None), Post.expires_at > now),
    )
    if upcoming_only:
        query = query.filter(Post.event_start >= now)

    raw_events = query.order_by(asc(Post.event_start), asc(Post.id)).all()
    user_id = current_user.id if current_user is not None else None

    result: list[EventResponse] = []
    for post in raw_events:
        if not user_can_access_post(current_user, post.target_groups):
            continue
        if not matches_group_filter(post.target_groups, group):
            continue
        result.append(EventResponse.from_orm_post(post, current_user_id=user_id))
        if len(result) >= limit:
            break
    return result


@app.get(
    "/api/v1/agenda",
    response_model=AgendaResponse,
    tags=["Agenda"],
    summary="Obtener estructura consolidada de agenda y plazos en orden cronologico",
)
async def get_agenda(
    group: str | None = Query(None, description="Filtro opcional por carrera o grupo (ej. TIE)"),
    upcoming_only: bool = Query(True, description="Mostrar unicamente eventos futuros o en curso"),
    limit: int = Query(50, ge=1, le=200, description="Cantidad maxima de eventos a retornar"),
    current_user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> AgendaResponse:
    """
    Consolida los eventos reales del calendario universitario y los plazos academicos
    sincronizados de Google Classroom, ordenados cronologicamente.
    """
    events = _query_upcoming_events(
        db=db,
        current_user=current_user,
        group=group,
        upcoming_only=upcoming_only,
        limit=limit,
    )

    deadlines: list[ClassroomDeadlineResponse] = []
    if current_user is not None:
        deadlines = await fetch_user_classroom_deadlines(current_user=current_user, db=db)

    combined_items: list[AgendaItemResponse] = []
    for ev in events:
        sort_key = ev.event_start.strftime("%Y-%m-%d %H:%M")
        combined_items.append(
            AgendaItemResponse(
                item_type="EVENT",
                id=str(ev.id),
                title=ev.title,
                description=ev.description,
                timestamp=ev.event_start.isoformat(),
                sort_key=sort_key,
                location_or_course=ev.location,
                link=ev.permalink,
                is_registered=ev.is_registered,
                registered_count=ev.registered_count,
            )
        )

    for dl in deadlines:
        sort_key = dl.due_date_formatted if dl.due_date_formatted else "9999-99-99 23:59"
        combined_items.append(
            AgendaItemResponse(
                item_type="DEADLINE",
                id=dl.id,
                title=dl.title,
                description=dl.description,
                timestamp=dl.due_date_formatted,
                sort_key=sort_key,
                location_or_course=dl.course_name,
                link=dl.alternate_link,
                is_registered=False,
                registered_count=0,
            )
        )

    combined_items.sort(key=lambda item: (item.sort_key, item.item_type, item.id))

    return AgendaResponse(
        events=events,
        deadlines=deadlines,
        items=combined_items,
    )


@app.get(
    "/api/v1/app-state",
    response_model=AppStateResponse,
    tags=["Mobile App API"],
    summary="Obtener estado inicial consolidado para la aplicacion movil",
)
async def get_app_state(
    group: str | None = Query(None, description="Filtro opcional por carrera o grupo (ej. TIE)"),
    limit: int = Query(20, ge=1, le=100, description="Cantidad maxima de publicaciones en el feed"),
    current_user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> AppStateResponse:
    """
    Entrega el paquete JSON consolidado para la carga inicial (cold start) de la app movil UPA,
    incluyendo feed, upcoming_events y upcoming_deadlines en una sola llamada.
    Garantiza ausencia de valores nulos y aplica filtrado estricto por rol y grupo.
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

    upcoming_events: list[EventResponse] = []
    upcoming_deadlines: list[ClassroomDeadlineResponse] = []
    user_data: AppStateUser | None = None

    if current_user is not None:
        upcoming_events = _query_upcoming_events(
            db=db,
            current_user=current_user,
            group=group,
            upcoming_only=True,
            limit=limit,
        )
        upcoming_deadlines = await fetch_user_classroom_deadlines(
            current_user=current_user,
            db=db,
        )
        clean_email = (current_user.email or "").strip().lower()
        clean_name = (current_user.full_name or "").strip() or _derive_full_name(clean_email)
        clean_role = (current_user.role or "user").strip() or "user"
        has_token = bool(
            (current_user.classroom_token and str(current_user.classroom_token).strip())
            or (
                getattr(current_user, "classroom_refresh_token", None)
                and str(current_user.classroom_refresh_token).strip()
            )
        )
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
            has_classroom_token=has_token,
        )

    return AppStateResponse(
        portal="UPA Mobile Campus Platform",
        api_version="1.0.0",
        authenticated=current_user is not None,
        user=user_data,
        feed=filtered_feed,
        upcoming_events=upcoming_events,
        upcoming_deadlines=upcoming_deadlines,
    )


# Entrega de los medios subidos (carteles, banners, documentos) bajo /uploads
try:
    app.mount("/uploads", UploadsStaticFiles(directory=str(get_upload_dir())), name="uploads")
except OSError as upload_dir_error:
    print(f"[Startup Warning] Directorio de subidas no disponible, /uploads no montado: {upload_dir_error}")

class SPAStaticFiles(StaticFiles):
    """StaticFiles con soporte SPA: resuelve subrutas sin extension hacia index.html."""

    async def get_response(self, path: str, scope):
        try:
            response = await super().get_response(path, scope)
            if response.status_code == 404 and "." not in path:
                return await super().get_response("index.html", scope)
            return response
        except HTTPException as ex:
            if ex.status_code == 404 and "." not in path:
                return await super().get_response("index.html", scope)
            raise


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
    app.mount("/dashboard", SPAStaticFiles(directory=str(active_static_dir), html=True), name="dashboard")
    app.mount("/admin", SPAStaticFiles(directory=str(active_static_dir), html=True), name="admin")


@app.get("/", include_in_schema=False)
def root():
    if active_static_dir:
        return RedirectResponse(url="/dashboard/")
    return {
        "status": "healthy",
        "service": "upa-app-backend",
        "docs": "/docs",
    }
