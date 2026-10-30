import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Post
from ..schemas.publication import clean_group_codes, extract_instagram_teaser
from .ai_extractor import extract_event_from_instagram_post, to_utc_datetime

logger = logging.getLogger(__name__)


@dataclass
class NormalizedSocialPost:
    instagram_id: str
    caption: str
    media_type: str  # IMAGE, VIDEO, CAROUSEL_ALBUM
    media_url: str
    permalink: str
    timestamp: datetime | None = None


class InstagramSyncService:
    """
    Servicio de sincronizacion de publicaciones de Instagram (@upalemana).
    Soporta Meta Instagram Graph API y SociableKIT JSON API con timeouts explicitos
    y transacciones atomicas sobre PostgreSQL.
    """

    DEFAULT_PERMALINK_FALLBACK = "https://www.instagram.com/upalemana"

    def extract_title_from_caption(self, caption: str) -> str:
        """Extrae un titulo conciso a partir de la primera linea del pie de foto (maximo 200 caracteres)."""
        if not caption or not caption.strip():
            return "Instagram Post @upalemana"

        lines = [line.strip() for line in caption.strip().splitlines() if line.strip()]
        if not lines:
            return "Instagram Post @upalemana"

        first_line = lines[0]
        if len(first_line) > 200:
            return first_line[:197].rsplit(" ", 1)[0] + "..."
        return first_line

    def parse_graph_api_item(self, item: dict[str, Any]) -> NormalizedSocialPost:
        """Convierte un elemento de la Instagram Graph API a NormalizedSocialPost."""
        media_id = str(item.get("id", ""))
        caption = item.get("caption") or ""
        media_type = item.get("media_type") or "IMAGE"
        media_url = item.get("media_url") or item.get("thumbnail_url") or ""
        permalink = item.get("permalink") or self.DEFAULT_PERMALINK_FALLBACK

        timestamp = None
        raw_ts = item.get("timestamp")
        if raw_ts:
            try:
                timestamp = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
            except Exception:
                timestamp = datetime.now(UTC)

        return NormalizedSocialPost(
            instagram_id=media_id,
            caption=caption,
            media_type=media_type,
            media_url=media_url,
            permalink=permalink,
            timestamp=timestamp,
        )

    def parse_sociablekit_item(self, item: dict[str, Any]) -> NormalizedSocialPost:
        """Convierte un elemento del feed JSON de SociableKIT a NormalizedSocialPost."""
        media_id = str(item.get("post_id") or item.get("id") or item.get("code") or "")
        caption = (
            item.get("pic_text_raw")
            or item.get("pic_text")
            or item.get("content")
            or item.get("caption")
            or item.get("message")
            or ""
        )
        media_type = item.get("pic_type") or item.get("media_type") or ("VIDEO" if item.get("video_url") else "IMAGE")
        media_url = (
            item.get("image_url")
            or item.get("post_link")
            or item.get("full_pic_src")
            or item.get("pic_src")
            or item.get("picture")
            or item.get("media_url")
            or ""
        )
        permalink = (
            item.get("link")
            or item.get("permalink")
            or item.get("post_url")
            or (f"https://www.instagram.com/p/{media_id}/" if media_id else self.DEFAULT_PERMALINK_FALLBACK)
        )

        timestamp = None
        raw_ts = item.get("date_time_posted") or item.get("date") or item.get("created_time") or item.get("timestamp")
        if raw_ts:
            try:
                timestamp = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
            except Exception:
                timestamp = datetime.now(UTC)

        return NormalizedSocialPost(
            instagram_id=media_id,
            caption=caption,
            media_type=media_type,
            media_url=media_url,
            permalink=permalink,
            timestamp=timestamp,
        )

    async def fetch_from_graph_api(self, token: str, account_id: str = "") -> list[NormalizedSocialPost]:
        """Obtiene publicaciones recientes desde la Instagram Graph API con timeout de 10 s."""
        if account_id:
            url = f"https://graph.facebook.com/v19.0/{account_id}/media"
        else:
            url = "https://graph.instagram.com/me/media"

        params = {
            "fields": "id,caption,media_type,media_url,thumbnail_url,permalink,timestamp",
            "access_token": token,
            "limit": 25,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, params=params, timeout=10.0)
                if response.status_code == 401:
                    logger.error("[Instagram API] Token de acceso no valido o vencido.")
                    return []
                if response.status_code == 429:
                    logger.warning("[Instagram API] Limite de tasa alcanzado (HTTP 429).")
                    return []
                if response.status_code != 200:
                    logger.error("[Instagram API] Codigo de estado inesperado: %s - %s", response.status_code, response.text)
                    return []

                data = response.json()
                raw_items = data.get("data", [])
                posts = []
                for item in raw_items:
                    if item.get("id"):
                        posts.append(self.parse_graph_api_item(item))
                return posts
        except httpx.RequestError as exc:
            logger.error("[Instagram API Error de Red] %s", exc)
            return []
        except Exception as exc:
            logger.error("[Instagram API Error] %s", exc)
            return []

    async def fetch_from_sociablekit(self, embed_id: str) -> list[NormalizedSocialPost]:
        """Obtiene publicaciones desde SociableKIT JSON API con respaldo y timeout de 10 s."""
        urls_to_try = [
            f"https://data.accentapi.com/feed/{embed_id}.json",
            f"https://data.sociablekit.com/embeds/{embed_id}/data",
        ]

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                for url in urls_to_try:
                    try:
                        response = await client.get(url, timeout=10.0)
                        if response.status_code == 200:
                            data = response.json()
                            raw_items = data if isinstance(data, list) else data.get("posts", data.get("data", []))
                            posts = []
                            for item in raw_items:
                                parsed = self.parse_sociablekit_item(item)
                                if parsed.instagram_id:
                                    posts.append(parsed)
                            if posts:
                                return posts
                    except Exception as exc:
                        logger.warning("[SociableKIT] Solicitud a %s fallida: %s", url, exc)
                return []
        except httpx.RequestError as exc:
            logger.error("[SociableKIT Error de Red] %s", exc)
            return []
        except Exception as exc:
            logger.error("[SociableKIT Error] %s", exc)
            return []

    def sync_posts(
        self,
        db: Session,
        posts_data: list[NormalizedSocialPost],
        author_id: int | None = None,
    ) -> dict[str, Any]:
        """
        Guarda o actualiza publicaciones normalizadas de Instagram en la tabla `posts`.
        Respeta las ediciones curadas en el portal (`is_edited == True`).
        """
        if not posts_data:
            return {
                "status": "success",
                "message": "No se recibieron nuevas publicaciones de Instagram.",
                "synced_count": 0,
                "created_count": 0,
                "updated_count": 0,
            }

        created_count = 0
        updated_count = 0
        ai_events_count = 0

        try:
            for item in posts_data:
                if not item.instagram_id:
                    continue

                existing = db.query(Post).filter(Post.instagram_id == item.instagram_id).first()
                teaser = extract_instagram_teaser(item.caption)
                if existing:
                    if not existing.is_edited:
                        existing.caption = teaser
                        existing.content = item.caption
                    existing.media_type = item.media_type
                    existing.media_url = item.media_url
                    existing.permalink = item.permalink
                    if not existing.link_url:
                        existing.link_url = item.permalink
                    if not existing.link_label:
                        existing.link_label = "Ver en Instagram"
                    if existing.published_at is None:
                        existing.published_at = item.timestamp or existing.created_at or datetime.now(UTC)
                    existing.updated_at = datetime.now(UTC)
                    updated_count += 1
                else:
                    pub_ts = item.timestamp or datetime.now(UTC)
                    fallback_title = self.extract_title_from_caption(item.caption)
                    extraction = extract_event_from_instagram_post(
                        caption=item.caption,
                        media_url=item.media_url,
                        media_type=item.media_type,
                        db=db,
                        reference_date=pub_ts,
                    )
                    start_dt = to_utc_datetime(extraction.start_time) if extraction.is_event else None
                    is_valid_ai_event = bool(extraction.is_event and start_dt is not None)

                    if is_valid_ai_event:
                        end_dt = to_utc_datetime(extraction.end_time)
                        ai_title = (extraction.event_title or "").strip()[:255] or fallback_title
                        ai_location = (extraction.location or "").strip()[:255] or None
                        conservative_groups = clean_group_codes(extraction.target_groups)
                        effective_groups = conservative_groups if conservative_groups else ["ALL"]
                        notify_push = bool(extraction.notify_push)
                        push_groups = list(effective_groups) if notify_push else []

                        new_post = Post(
                            title=ai_title,
                            caption=teaser,
                            content=item.caption,
                            post_type="INSTAGRAM",
                            is_news=True,
                            is_event=True,
                            is_pinned=False,
                            is_edited=False,
                            is_ai_generated=True,
                            event_start=start_dt,
                            event_end=end_dt,
                            location=ai_location,
                            has_registration=bool(extraction.allow_registration),
                            target_groups=effective_groups,
                            send_push_notification=notify_push,
                            notify_groups=push_groups,
                            event_notify_groups=push_groups,
                            reminder_minutes_before=30,
                            reminders=[30],
                            instagram_id=item.instagram_id,
                            media_type=item.media_type,
                            media_url=item.media_url,
                            permalink=item.permalink,
                            link_url=item.permalink,
                            link_label="Ver en Instagram",
                            author_id=author_id,
                            created_at=pub_ts,
                            published_at=pub_ts,
                        )
                        ai_events_count += 1
                    else:
                        new_post = Post(
                            title=fallback_title,
                            caption=teaser,
                            content=item.caption,
                            post_type="INSTAGRAM",
                            is_news=True,
                            is_event=False,
                            is_pinned=False,
                            is_edited=False,
                            is_ai_generated=False,
                            target_groups=["ALL"],
                            instagram_id=item.instagram_id,
                            media_type=item.media_type,
                            media_url=item.media_url,
                            permalink=item.permalink,
                            link_url=item.permalink,
                            link_label="Ver en Instagram",
                            author_id=author_id,
                            created_at=pub_ts,
                            published_at=pub_ts,
                        )
                    db.add(new_post)
                    created_count += 1

            db.commit()
            return {
                "status": "success",
                "synced_count": len(posts_data),
                "created_count": created_count,
                "updated_count": updated_count,
                "ai_events_count": ai_events_count,
            }
        except Exception as e:
            db.rollback()
            logger.error("[Instagram DB Sync] Transaccion revertida: %s", e)
            raise e

    async def sync_instagram(self, db: Session, author_id: int | None = None) -> dict[str, Any]:
        """Ejecuta el proceso completo de sincronizacion de Instagram segun las credenciales activas."""
        posts = []
        if settings.INSTAGRAM_ACCESS_TOKEN:
            logger.info("[Instagram Sync] Consultando Instagram Graph API...")
            posts = await self.fetch_from_graph_api(
                token=settings.INSTAGRAM_ACCESS_TOKEN,
                account_id=settings.INSTAGRAM_ACCOUNT_ID,
            )
        elif settings.SOCIABLEKIT_EMBED_ID:
            logger.info("[Instagram Sync] Consultando SociableKIT Feed...")
            posts = await self.fetch_from_sociablekit(embed_id=settings.SOCIABLEKIT_EMBED_ID)
        else:
            logger.info("[Instagram Sync] Sin credenciales externas de Instagram configuradas.")
            return {
                "status": "skipped",
                "message": "No hay INSTAGRAM_ACCESS_TOKEN ni SOCIABLEKIT_EMBED_ID configurados.",
                "synced_count": 0,
                "created_count": 0,
                "updated_count": 0,
            }

        return self.sync_posts(db, posts, author_id=author_id)


instagram_service = InstagramSyncService()
