"""API unificada de Publicaciones (Noticia, Evento o ambos simultaneamente)."""

import base64
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path as FilePath
from typing import Any

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path, Query, Request, status
from sqlalchemy import asc, desc
from sqlalchemy.orm import Session, selectinload

from ..auth import get_current_user
from ..config import settings
from ..database import get_db
from ..models import AudienceGroup, EventRegistration, Post, PostView, User
from ..permissions import require_permission
from ..schemas.event import EventRegistrationEntry
from ..schemas.post import (
    DeleteResponse,
    effective_published_at,
    effective_reminders,
    ensure_utc_datetime,
    normalize_category,
    normalize_target_groups,
    user_can_access_post,
)
from ..schemas.publication import (
    PublicationRegistrationsResponse,
    PublicationResponse,
    PublicationRsvpRequest,
    PublicationUpdate,
    PublicationWrite,
    clean_group_codes,
    extract_instagram_teaser,
)
from ..services import gemini
from ..services.audit import AUDIT_TARGET_POST, changed_fields, log_audit
from ..services.push import (
    EMERGENCY_BANNER,
    build_emergency_message,
    collect_recipient_tokens,
    dispatch_emergency_push,
)
from .media import get_upload_dir, sniff_content_type

router = APIRouter(prefix="/api/publications", tags=["Publications"])

MANUAL_TYPES = {"MANUAL", "EMERGENCY_BANNER"}


def record_post_view(db: Session, post_id: int, user_id: int) -> bool:
    """Registra de forma idempotente la visualizacion unica de una publicacion por un usuario."""
    existing = (
        db.query(PostView)
        .filter(PostView.post_id == post_id, PostView.user_id == user_id)
        .first()
    )
    if existing is not None:
        return False
    db.add(PostView(post_id=post_id, user_id=user_id))
    db.commit()
    return True


def _filter_subset_groups(selected: list[str], target_groups: list[str]) -> list[str]:
    """Restringe los grupos de notificacion a los grupos destinatarios seleccionados."""
    cleaned = clean_group_codes(selected)
    if not cleaned:
        return []
    allowed_upper = {g.upper() for g in target_groups}
    if "ALL" in allowed_upper:
        return cleaned
    return [g for g in cleaned if g.upper() in allowed_upper]


def _snapshot_post(post: Post) -> dict:
    return {
        "title": post.title or "",
        "caption": post.caption or "",
        "content": post.content or "",
        "detail_text": post.detail_text or "",
        "post_type": post.post_type or "MANUAL",
        "category": post.category or "",
        "is_news": bool(post.is_news),
        "is_event": bool(post.is_event),
        "is_pinned": bool(post.is_pinned),
        "has_registration": bool(post.has_registration),
        "target_groups": list(post.target_groups or []),
        "notify_groups": list(post.notify_groups or []),
        "event_notify_groups": list(post.event_notify_groups or []),
        "published_at": effective_published_at(post).isoformat(),
        "expires_at": ensure_utc_datetime(post.expires_at).isoformat() if post.expires_at else "",
        "event_start": ensure_utc_datetime(post.event_start).isoformat() if post.event_start else "",
        "event_end": ensure_utc_datetime(post.event_end).isoformat() if post.event_end else "",
        "location": post.location or "",
        "reminders": effective_reminders(post),
        "media_url": post.media_url or "",
        "link_url": post.link_url or "",
        "link_label": post.link_label or "",
    }


def _infer_media_type(media_url: str | None, declared_type: str | None) -> str | None:
    if declared_type and declared_type.strip():
        return declared_type.strip().upper()
    if not media_url or not media_url.strip():
        return None
    lower = media_url.strip().lower().split("?")[0]
    if lower.endswith((".mp4", ".webm", ".mov")):
        return "VIDEO"
    if lower.endswith((".jpg", ".jpeg", ".png", ".webp")):
        return "IMAGE"
    return None


def _validate_and_apply(post: Post, payload: PublicationWrite, *, is_create: bool) -> None:
    clean_title = (payload.title or "").strip()
    if not clean_title:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El título de la publicación no puede estar vacío.",
        )

    requested_type = (payload.post_type or "MANUAL").strip().upper()
    if is_create:
        if requested_type not in MANUAL_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Tipo de publicación no válido. Use MANUAL o EMERGENCY_BANNER.",
            )
        final_type = requested_type
    else:
        current_type = (post.post_type or "MANUAL").strip().upper()
        if current_type == "INSTAGRAM":
            if requested_type != "INSTAGRAM":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Las publicaciones de Instagram conservan su tipo original y no pueden cambiarse.",
                )
            final_type = "INSTAGRAM"
        else:
            if requested_type not in MANUAL_TYPES:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No se puede convertir una publicación manual en Instagram.",
                )
            final_type = requested_type

    is_news = bool(payload.is_news)
    is_event = bool(payload.is_event)

    if final_type == "INSTAGRAM" and not is_news:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Las publicaciones de Instagram siempre permanecen activas como Noticia.",
        )

    if final_type == EMERGENCY_BANNER:
        if not is_news:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Un aviso urgente (Eilmeldung) siempre permanece activo como Noticia.",
            )
        if is_event:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Los avisos urgentes no admiten sección de Evento.",
            )

    if not is_news and not is_event:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Active al menos una sección: Noticia o Evento.",
        )

    is_pinned = bool(payload.is_pinned)
    if is_pinned and payload.expires_at is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Las publicaciones fijadas requieren una fecha de vigencia (expires_at).",
        )

    try:
        clean_category = normalize_category(payload.category)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    target_groups = normalize_target_groups(payload.target_groups)
    notify_groups = _filter_subset_groups(payload.notify_groups, target_groups) if is_news else []

    now = datetime.now(UTC)
    was_already_published = (
        not is_create
        and post.published_at is not None
        and ensure_utc_datetime(post.published_at) <= now
    )
    if final_type == "INSTAGRAM" and not is_create:
        published_at = post.published_at or post.created_at or now
    elif was_already_published:
        published_at = ensure_utc_datetime(post.published_at)
    elif payload.published_at is not None:
        candidate_pub = ensure_utc_datetime(payload.published_at)
        if candidate_pub < now - timedelta(minutes=2):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La fecha de publicación programada no puede estar en el pasado.",
            )
        published_at = candidate_pub
    elif not is_create and post.published_at is not None:
        published_at = ensure_utc_datetime(post.published_at)
    else:
        published_at = now

    event_start: datetime | None = None
    event_end: datetime | None = None
    location: str | None = None
    reminders: list[int] = []
    event_notify_groups: list[str] = []

    if is_event:
        if payload.event_start is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Indique la fecha y hora de inicio del evento.",
            )
        event_start = ensure_utc_datetime(payload.event_start)
        if payload.event_end is not None:
            event_end = ensure_utc_datetime(payload.event_end)
            if event_end < event_start:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="La fecha de finalización del evento no puede ser anterior al inicio.",
                )
        else:
            event_end = event_start + timedelta(hours=1)

        location = payload.location.strip() if payload.location and payload.location.strip() else None
        event_notify_groups = _filter_subset_groups(payload.event_notify_groups, target_groups)
        if payload.reminders is None:
            reminders = [30]
        else:
            reminders = list(payload.reminders)

    clean_link_url = payload.link_url.strip() if payload.link_url and payload.link_url.strip() else None
    clean_link_label = payload.link_label.strip() if payload.link_label and payload.link_label.strip() else None
    if final_type == "INSTAGRAM":
        insta_permalink = (post.permalink or payload.permalink or "").strip()
        if insta_permalink:
            clean_link_url = insta_permalink
        if clean_link_url and not clean_link_label:
            clean_link_label = "Ver en Instagram"

    post.title = clean_title
    post.post_type = final_type
    post.category = clean_category
    post.is_news = is_news
    post.is_event = is_event
    post.is_pinned = is_pinned
    post.is_edited = True
    post.has_registration = bool(payload.has_registration)
    post.target_groups = target_groups
    post.notify_groups = notify_groups
    post.event_notify_groups = event_notify_groups
    post.published_at = published_at
    post.expires_at = ensure_utc_datetime(payload.expires_at) if is_pinned and payload.expires_at else (
        ensure_utc_datetime(payload.expires_at) if payload.expires_at else None
    )

    if final_type == "INSTAGRAM" and not is_create:
        raw_ig_text = post.content or post.caption or ""
        post.caption = extract_instagram_teaser(raw_ig_text) or None
    else:
        post.caption = payload.caption.strip() if payload.caption and payload.caption.strip() else None
        post.content = payload.content.strip() if payload.content and payload.content.strip() else None
        post.detail_text = payload.detail_text.strip() if payload.detail_text and payload.detail_text.strip() else None

    if final_type != "INSTAGRAM" or is_create:
        if payload.media_url is not None:
            post.media_url = payload.media_url.strip() or None
        post.media_type = _infer_media_type(post.media_url, payload.media_type)
        if payload.permalink is not None:
            post.permalink = payload.permalink.strip() or None

    post.link_url = clean_link_url
    post.link_label = clean_link_label

    post.event_start = event_start
    post.event_end = event_end
    post.location = location
    post.reminders = reminders
    post.reminder_minutes_before = reminders[0] if reminders else None


@router.get(
    "",
    response_model=list[PublicationResponse],
    summary="Listar todas las publicaciones unificadas del portal editorial",
)
def list_publications(
    kind: str | None = Query(None, description="Filtro opcional: news, event, instagram, urgent, pending"),
    limit: int = Query(100, ge=1, le=300),
    db: Session = Depends(get_db),
    editor: User = Depends(require_permission("publicaciones")),
) -> list[PublicationResponse]:
    query = db.query(Post).options(
        selectinload(Post.registrations),
        selectinload(Post.views),
    )
    if kind == "news":
        query = query.filter(Post.is_news.is_(True))
    elif kind == "event":
        query = query.filter(Post.is_event.is_(True))
    elif kind == "instagram":
        query = query.filter(Post.post_type == "INSTAGRAM")
    elif kind == "urgent":
        query = query.filter(Post.post_type == EMERGENCY_BANNER)
    elif kind == "pending":
        query = query.filter(Post.is_edited.is_(False))

    rows = query.order_by(desc(Post.is_pinned), desc(Post.created_at), desc(Post.id)).limit(limit).all()
    return [PublicationResponse.from_orm_post(row) for row in rows]


AI_SUPPORTED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}


def _normalize_autocomplete_form(raw: dict[str, Any]) -> dict[str, Any]:
    """Normaliza las claves del formulario (snake_case o camelCase) recibidas para autocompletar con IA."""
    raw_groups = raw.get("target_groups") if "target_groups" in raw else raw.get("targetGroups")
    if isinstance(raw_groups, str):
        stripped = raw_groups.strip()
        if stripped.startswith("["):
            try:
                raw_groups = json.loads(stripped)
            except ValueError:
                raw_groups = [stripped]
        elif stripped:
            raw_groups = [g.strip() for g in stripped.split(",") if g.strip()]
        else:
            raw_groups = []
    return {
        "title": str(raw.get("title") or "").strip(),
        "caption": str(raw.get("caption") or "").strip(),
        "content": str(raw.get("content") or "").strip(),
        "detail_text": str(raw.get("detail_text") if "detail_text" in raw else (raw.get("detailText") or "")).strip(),
        "location": str(raw.get("location") or "").strip(),
        "event_start": str(
            raw.get("event_start") if "event_start" in raw else (raw.get("eventStart") or "")
        ).strip(),
        "event_end": str(raw.get("event_end") if "event_end" in raw else (raw.get("eventEnd") or "")).strip(),
        "target_groups": clean_group_codes(raw_groups),
        "category": str(raw.get("category") or "").strip(),
        "link_label": str(raw.get("link_label") if "link_label" in raw else (raw.get("linkLabel") or "")).strip(),
        "link_url": str(raw.get("link_url") if "link_url" in raw else (raw.get("linkUrl") or "")).strip(),
        "media_url": str(
            raw.get("media_url") or raw.get("image_url") or raw.get("imageUrl") or ""
        ).strip(),
        "post_type": str(raw.get("post_type") or raw.get("postType") or "MANUAL").strip().upper(),
        "is_news": bool(raw.get("is_news") if "is_news" in raw else raw.get("isNews", True)),
        "is_event": bool(raw.get("is_event") if "is_event" in raw else raw.get("isEvent", False)),
        "has_registration": bool(
            raw.get("has_registration") if "has_registration" in raw else raw.get("hasRegistration", False)
        ),
        "image_base64": raw.get("image_base64") or raw.get("imageBase64") or "",
    }


def _resolve_media_bytes(form_data: dict[str, Any]) -> tuple[bytes | None, str | None]:
    """Obtiene los bytes y el tipo MIME de la imagen desde base64, almacenamiento local (/uploads) o URL HTTP."""
    b64_raw = str(form_data.get("image_base64") or "").strip()
    if b64_raw:
        if "," in b64_raw and b64_raw.lower().startswith("data:"):
            b64_raw = b64_raw.split(",", 1)[1].strip()
        try:
            decoded = base64.b64decode(b64_raw, validate=False)
        except ValueError:
            decoded = b""
        if decoded:
            mime = sniff_content_type(decoded)
            if mime in AI_SUPPORTED_MIME_TYPES:
                return decoded, mime

    media_url = str(form_data.get("media_url") or "").strip()
    if not media_url:
        return None, None

    clean_path = media_url.split("?", 1)[0].split("#", 1)[0]
    if "/uploads/" in clean_path:
        fname = clean_path.rsplit("/uploads/", 1)[-1].strip("/")
        if fname and FilePath(fname).name == fname:
            try:
                local_file = get_upload_dir() / fname
                if local_file.is_file():
                    raw_bytes = local_file.read_bytes()
                    mime = sniff_content_type(raw_bytes)
                    if mime in AI_SUPPORTED_MIME_TYPES:
                        return raw_bytes, mime
            except OSError:
                pass

    if media_url.startswith(("http://", "https://")):
        try:
            resp = httpx.get(media_url, timeout=settings.GEMINI_TIMEOUT_SECONDS)
            if resp.status_code == 200 and resp.content:
                mime = sniff_content_type(resp.content)
                if mime not in AI_SUPPORTED_MIME_TYPES:
                    header_mime = resp.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                    if header_mime in AI_SUPPORTED_MIME_TYPES:
                        mime = header_mime
                if mime in AI_SUPPORTED_MIME_TYPES:
                    return resp.content, mime
        except httpx.HTTPError:
            pass

    return None, None


@router.post(
    "/autocomplete-ai",
    summary="Autocompletar campos vacíos de una publicación mediante IA multimodal (Google Gemini Flash)",
)
async def autocomplete_publication_ai(
    request: Request,
    db: Session = Depends(get_db),
    editor: User = Depends(require_permission("publicaciones")),
) -> dict[str, Any]:
    content_type = (request.headers.get("content-type") or "").lower()
    raw_dict: dict[str, Any] = {}
    uploaded_bytes: bytes | None = None
    uploaded_mime: str | None = None

    if "multipart/form-data" in content_type:
        form = await request.form()
        for json_key in ("data", "form", "payload"):
            raw_json = form.get(json_key)
            if isinstance(raw_json, str) and raw_json.strip():
                try:
                    parsed = json.loads(raw_json)
                    if isinstance(parsed, dict):
                        raw_dict.update(parsed)
                except ValueError as exc:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="El JSON enviado en el formulario no es válido.",
                    ) from exc
        direct_keys = (
            "title",
            "caption",
            "content",
            "detail_text",
            "detailText",
            "location",
            "event_start",
            "eventStart",
            "event_end",
            "eventEnd",
            "target_groups",
            "targetGroups",
            "category",
            "link_label",
            "linkLabel",
            "link_url",
            "linkUrl",
            "media_url",
            "image_url",
            "imageUrl",
            "post_type",
            "postType",
            "is_news",
            "isNews",
            "is_event",
            "isEvent",
            "has_registration",
            "hasRegistration",
        )
        for key in direct_keys:
            if key in form:
                val = form.get(key)
                if isinstance(val, str):
                    raw_dict[key] = val
        upload_obj = form.get("file") or form.get("image")
        if upload_obj is not None and hasattr(upload_obj, "read"):
            data_bytes = await upload_obj.read(settings.MAX_UPLOAD_SIZE_BYTES + 1)
            if len(data_bytes) > settings.MAX_UPLOAD_SIZE_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="El archivo supera el tamaño máximo permitido de 10 MB.",
                )
            if data_bytes:
                sniffed = sniff_content_type(data_bytes)
                if sniffed not in AI_SUPPORTED_MIME_TYPES:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="El archivo adjunto no coincide con un formato válido (JPG, PNG, WEBP, PDF).",
                    )
                uploaded_bytes = data_bytes
                uploaded_mime = sniffed
    else:
        body_bytes = await request.body()
        if body_bytes.strip():
            try:
                parsed = json.loads(body_bytes)
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="El cuerpo JSON de la solicitud no es válido.",
                ) from exc
            if not isinstance(parsed, dict):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Se esperaba un objeto JSON con los datos del formulario.",
                )
            raw_dict = parsed

    normalized_form = _normalize_autocomplete_form(raw_dict)
    if uploaded_bytes is None:
        uploaded_bytes, uploaded_mime = _resolve_media_bytes(normalized_form)

    api_key, _source = gemini.resolve_api_key(db)
    db_groups = db.query(AudienceGroup).all()
    available_groups = [
        {"id": str(g.id).strip(), "name": str(g.name or g.id).strip()}
        for g in db_groups
        if getattr(g, "id", None)
    ]

    result = gemini.autocomplete_publication(
        api_key,
        form_data=normalized_form,
        available_groups=available_groups,
        image_bytes=uploaded_bytes,
        image_mime_type=uploaded_mime,
    )
    if not result.ok:
        err_status = (
            status.HTTP_400_BAD_REQUEST
            if result.code in ("NO_KEY", "INVALID_KEY", "FORBIDDEN")
            else status.HTTP_502_BAD_GATEWAY
        )
        raise HTTPException(status_code=err_status, detail=result.message)

    return result.suggestions


@router.get(
    "/{publication_id}",
    response_model=PublicationResponse,
    summary="Obtener detalle completo de una publicacion unificada",
)
def get_publication(
    publication_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    editor: User = Depends(require_permission("publicaciones")),
) -> PublicationResponse:
    post = (
        db.query(Post)
        .options(selectinload(Post.registrations), selectinload(Post.views))
        .filter(Post.id == publication_id)
        .first()
    )
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Publicación no encontrada.")
    return PublicationResponse.from_orm_post(post)


@router.post(
    "",
    response_model=PublicationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una nueva publicacion unificada (Noticia, Evento o ambos)",
)
def create_publication(
    payload: PublicationWrite,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    editor: User = Depends(require_permission("publicaciones")),
) -> PublicationResponse:
    post = Post(author_id=editor.id)
    _validate_and_apply(post, payload, is_create=True)
    db.add(post)
    db.flush()

    log_audit(
        db,
        editor,
        "CREATE_POST",
        AUDIT_TARGET_POST,
        target_id=post.id,
        details={"title": post.title, "post_type": post.post_type},
    )

    push_groups: list[str] = []
    if post.post_type == EMERGENCY_BANNER:
        push_groups = list(post.target_groups or ["ALL"])
    elif post.is_news and post.notify_groups:
        push_groups = list(post.notify_groups)

    push_tokens: list[str] = []
    if push_groups:
        push_tokens = collect_recipient_tokens(db, push_groups)
        post.send_push_notification = True

    db.commit()
    db.refresh(post)

    if push_groups:
        title, body, data = build_emergency_message(post)
        background_tasks.add_task(dispatch_emergency_push, push_tokens, title, body, data)

    return PublicationResponse.from_orm_post(post)


def _merge_update_into_write(post: Post, patch: PublicationUpdate) -> tuple[PublicationWrite, bool]:
    """Combina un payload parcial sobre el estado persistido del post para validacion integral."""
    provided = patch.model_fields_set
    reset_publish_to_now = "published_at" in provided and patch.published_at is None
    merged = PublicationWrite(
        title=patch.title if "title" in provided and patch.title is not None else (post.title or ""),
        post_type=patch.post_type if "post_type" in provided and patch.post_type is not None else (post.post_type or "MANUAL"),
        has_registration=patch.has_registration if "has_registration" in provided and patch.has_registration is not None else bool(post.has_registration),
        target_groups=patch.target_groups if "target_groups" in provided and patch.target_groups is not None else list(post.target_groups or ["ALL"]),
        published_at=patch.published_at if "published_at" in provided else post.published_at,
        is_news=patch.is_news if "is_news" in provided and patch.is_news is not None else bool(post.is_news),
        notify_groups=patch.notify_groups if "notify_groups" in provided and patch.notify_groups is not None else list(post.notify_groups or []),
        caption=patch.caption if "caption" in provided else post.caption,
        content=patch.content if "content" in provided else post.content,
        detail_text=patch.detail_text if "detail_text" in provided else post.detail_text,
        category=patch.category if "category" in provided else post.category,
        is_pinned=patch.is_pinned if "is_pinned" in provided and patch.is_pinned is not None else bool(post.is_pinned),
        expires_at=patch.expires_at if "expires_at" in provided else post.expires_at,
        media_url=patch.media_url if "media_url" in provided else post.media_url,
        media_type=patch.media_type if "media_type" in provided else post.media_type,
        link_label=patch.link_label if "link_label" in provided else post.link_label,
        link_url=patch.link_url if "link_url" in provided else post.link_url,
        permalink=patch.permalink if "permalink" in provided else post.permalink,
        is_event=patch.is_event if "is_event" in provided and patch.is_event is not None else bool(post.is_event),
        event_start=patch.event_start if "event_start" in provided else post.event_start,
        event_end=patch.event_end if "event_end" in provided else post.event_end,
        location=patch.location if "location" in provided else post.location,
        event_notify_groups=patch.event_notify_groups if "event_notify_groups" in provided and patch.event_notify_groups is not None else list(post.event_notify_groups or []),
        reminders=patch.reminders if "reminders" in provided else (list(post.reminders) if isinstance(post.reminders, list) else None),
    )
    return merged, reset_publish_to_now


@router.put(
    "/{publication_id}",
    response_model=PublicationResponse,
    summary="Actualizar una publicacion unificada existente",
)
def update_publication(
    payload: PublicationUpdate,
    background_tasks: BackgroundTasks,
    publication_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    editor: User = Depends(require_permission("publicaciones")),
) -> PublicationResponse:
    post = (
        db.query(Post)
        .options(selectinload(Post.registrations), selectinload(Post.views))
        .filter(Post.id == publication_id)
        .first()
    )
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Publicación no encontrada.")

    before = _snapshot_post(post)
    prev_notify_groups = set(post.notify_groups or [])
    was_future_scheduled = (
        post.published_at is not None and ensure_utc_datetime(post.published_at) > datetime.now(UTC)
    )
    merged_write, reset_publish_to_now = _merge_update_into_write(post, payload)
    if reset_publish_to_now and was_future_scheduled and (post.post_type or "").upper() != "INSTAGRAM":
        post.published_at = None
    _validate_and_apply(post, merged_write, is_create=False)
    changes = changed_fields(before, _snapshot_post(post))

    log_audit(
        db,
        editor,
        "UPDATE_POST",
        AUDIT_TARGET_POST,
        target_id=post.id,
        details={"title": post.title, "changes": changes},
    )

    # Para publicaciones de Instagram o nuevos grupos de notificacion, despachar aviso al guardar
    newly_notified = [g for g in (post.notify_groups or []) if g not in prev_notify_groups]
    if post.post_type == "INSTAGRAM" and post.notify_groups:
        newly_notified = list(post.notify_groups)

    push_tokens: list[str] = []
    if newly_notified:
        push_tokens = collect_recipient_tokens(db, newly_notified)
        post.send_push_notification = True

    db.commit()
    db.refresh(post)

    if newly_notified:
        title, body, data = build_emergency_message(post)
        background_tasks.add_task(dispatch_emergency_push, push_tokens, title, body, data)

    return PublicationResponse.from_orm_post(post)


@router.delete(
    "/{publication_id}",
    response_model=DeleteResponse,
    summary="Eliminar una publicacion unificada",
)
def delete_publication(
    publication_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    editor: User = Depends(require_permission("publicaciones")),
) -> DeleteResponse:
    post = db.query(Post).filter(Post.id == publication_id).first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Publicación no encontrada.")

    log_audit(
        db,
        editor,
        "DELETE_POST",
        AUDIT_TARGET_POST,
        target_id=publication_id,
        details={"title": post.title},
    )
    db.delete(post)
    db.commit()
    return DeleteResponse(
        status="deleted",
        id=publication_id,
        detail="Publicación eliminada correctamente.",
    )


@router.get(
    "/{publication_id}/registrations",
    response_model=PublicationRegistrationsResponse,
    summary="Listar inscripciones y bajas (RSVP) de una publicacion o evento",
)
def get_publication_registrations(
    publication_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    editor: User = Depends(require_permission("publicaciones")),
) -> PublicationRegistrationsResponse:
    post = db.query(Post).filter(Post.id == publication_id).first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Publicación no encontrada.")

    rows = (
        db.query(EventRegistration, User)
        .join(User, User.id == EventRegistration.user_id)
        .filter(EventRegistration.post_id == publication_id)
        .order_by(asc(EventRegistration.created_at), asc(EventRegistration.id))
        .all()
    )
    entries = [
        EventRegistrationEntry(
            user_id=user.id,
            full_name=(user.full_name or "").strip(),
            email=(user.email or "").strip(),
            status=(reg.status or "attending"),
            registered_at=ensure_utc_datetime(reg.created_at),
        )
        for reg, user in rows
    ]
    attending = sum(1 for e in entries if e.status == "attending")
    declined = sum(1 for e in entries if e.status == "declined")
    return PublicationRegistrationsResponse(
        publication_id=post.id,
        title=(post.title or "").strip(),
        has_registration=bool(post.has_registration),
        attending_count=attending,
        declined_count=declined,
        registrations=entries,
    )


@router.post(
    "/{publication_id}/rsvp",
    response_model=PublicationResponse,
    summary="Confirmar asistencia o darse de baja en una publicacion o evento con RSVP habilitado",
)
def submit_publication_rsvp(
    payload: PublicationRsvpRequest,
    publication_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PublicationResponse:
    post = (
        db.query(Post)
        .options(selectinload(Post.registrations), selectinload(Post.views))
        .filter(Post.id == publication_id)
        .first()
    )
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Publicación no encontrada.")
    if not user_can_access_post(current_user, post.target_groups):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado: no pertenece al grupo destinatario de esta publicación.",
        )
    if not post.has_registration and not post.is_event:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Esta publicación no tiene habilitada la inscripción.",
        )

    existing = (
        db.query(EventRegistration)
        .filter(EventRegistration.post_id == publication_id, EventRegistration.user_id == current_user.id)
        .first()
    )
    if existing:
        existing.status = payload.status
        existing.updated_at = datetime.now(UTC)
    else:
        db.add(
            EventRegistration(
                post_id=publication_id,
                user_id=current_user.id,
                status=payload.status,
            )
        )
    db.commit()
    db.refresh(post)
    return PublicationResponse.from_orm_post(post)


@router.post(
    "/{publication_id}/view",
    response_model=PublicationResponse,
    summary="Registrar visualizacion unica de una publicacion por un estudiante o usuario",
)
def mark_publication_viewed(
    publication_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PublicationResponse:
    post = (
        db.query(Post)
        .options(selectinload(Post.registrations), selectinload(Post.views))
        .filter(Post.id == publication_id)
        .first()
    )
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Publicación no encontrada.")
    if not user_can_access_post(current_user, post.target_groups):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado: no pertenece al grupo destinatario de esta publicación.",
        )
    record_post_view(db, publication_id, current_user.id)
    db.refresh(post)
    return PublicationResponse.from_orm_post(post)
