import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy.orm import Session

from ..api.media import get_upload_dir
from ..config import settings
from ..models import DEFAULT_VIDEO_POSTER_FALLBACK, Post, is_video_stream_url
from ..schemas.post import ASUNCION_TZ, DEFAULT_INSTAGRAM_PROFILE_URL, normalize_instagram_url
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
    image_url: str = ""
    _mirror_attempted: bool = False

    def __post_init__(self) -> None:
        self.permalink = normalize_instagram_url(
            self.permalink,
            instagram_id=self.instagram_id,
            media_type=self.media_type,
            is_instagram=True,
            fallback_if_generic=True,
        )
        if not self.image_url:
            if self.media_url and not is_video_stream_url(self.media_url):
                self.image_url = self.media_url
            elif str(self.media_type or "").strip().upper() == "VIDEO" or is_video_stream_url(self.media_url):
                self.image_url = DEFAULT_VIDEO_POSTER_FALLBACK


class InstagramSyncService:
    """
    Servicio de sincronizacion de publicaciones de Instagram (@upalemana).
    Soporta Meta Instagram Graph API y SociableKIT JSON API con timeouts explicitos
    y transacciones atomicas sobre PostgreSQL.
    """

    DEFAULT_PERMALINK_FALLBACK = DEFAULT_INSTAGRAM_PROFILE_URL
    DEFAULT_VIDEO_THUMBNAIL_FALLBACK = DEFAULT_VIDEO_POSTER_FALLBACK
    GRAPH_API_VERSION = "v21.0"
    GRAPH_API_BASE_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

    async def discover_instagram_account_id(
        self,
        token: str,
        client: httpx.AsyncClient | None = None,
    ) -> str:
        """Resuelve dinamicamente el ID de la cuenta de Instagram Business via GET /me/accounts."""
        clean_token = (token or "").strip()
        if not clean_token:
            return ""

        url = f"{self.GRAPH_API_BASE_URL}/me/accounts"
        params = {
            "fields": "instagram_business_account",
            "access_token": clean_token,
        }

        async def _request(http_client: httpx.AsyncClient) -> str:
            response = await http_client.get(url, params=params, timeout=10.0)
            if response.status_code == 401:
                logger.error("[Instagram API Auto-Discovery] Token de acceso no valido o vencido (HTTP 401).")
                return ""
            if response.status_code != 200:
                logger.warning(
                    "[Instagram API Auto-Discovery] Respuesta inesperada %s: %s",
                    response.status_code,
                    response.text,
                )
                return ""
            data = response.json()
            for page in data.get("data", []):
                ig_acc = page.get("instagram_business_account")
                if isinstance(ig_acc, dict) and ig_acc.get("id"):
                    discovered_id = str(ig_acc["id"]).strip()
                    if discovered_id:
                        logger.info(
                            "[Instagram API Auto-Discovery] Instagram Business Account ID resuelto: %s",
                            discovered_id,
                        )
                        return discovered_id
            return ""

        try:
            if client is not None:
                return await _request(client)
            async with httpx.AsyncClient(timeout=10.0) as owned_client:
                return await _request(owned_client)
        except httpx.RequestError as exc:
            logger.error("[Instagram API Auto-Discovery Error de Red] %s", exc)
            return ""
        except Exception as exc:
            logger.error("[Instagram API Auto-Discovery Error] %s", exc)
            return ""

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
        raw_media_url = (item.get("media_url") or "").strip()
        raw_thumb_url = (item.get("thumbnail_url") or item.get("image_url") or "").strip()
        media_url = raw_media_url or raw_thumb_url
        if str(media_type).strip().upper() == "VIDEO" or is_video_stream_url(media_url):
            image_url = (
                raw_thumb_url
                or (raw_media_url if raw_media_url and not is_video_stream_url(raw_media_url) else "")
                or self.DEFAULT_VIDEO_THUMBNAIL_FALLBACK
            )
        else:
            image_url = raw_thumb_url or media_url
        permalink = normalize_instagram_url(
            item.get("permalink") or "",
            instagram_id=media_id,
            media_type=media_type,
            is_instagram=True,
            fallback_if_generic=True,
        )

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
            image_url=image_url,
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
        primary_pic = (
            item.get("image_url")
            or item.get("full_pic_src")
            or item.get("pic_src")
            or item.get("picture")
            or item.get("post_link")
            or ""
        )
        thumb_url = (
            item.get("thumbnail_url")
            or item.get("image_url")
            or item.get("thumbnail")
            or primary_pic
            or ""
        )
        media_url = (
            primary_pic
            or item.get("media_url")
            or thumb_url
            or item.get("video_url")
            or ""
        )
        if str(media_type).strip().upper() == "VIDEO" or is_video_stream_url(media_url):
            image_url = (
                thumb_url
                or (media_url if media_url and not is_video_stream_url(media_url) else "")
                or self.DEFAULT_VIDEO_THUMBNAIL_FALLBACK
            )
        else:
            image_url = thumb_url or media_url
        raw_permalink = (
            item.get("link")
            or item.get("permalink")
            or item.get("post_url")
            or ""
        )
        permalink = normalize_instagram_url(
            raw_permalink,
            instagram_id=media_id,
            media_type=media_type,
            is_instagram=True,
            fallback_if_generic=True,
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
            image_url=image_url,
            permalink=permalink,
            timestamp=timestamp,
        )

    def _sanitize_instagram_id(self, instagram_id: str | None) -> str:
        """Normaliza el ID de Instagram a un identificador de archivo seguro."""
        return re.sub(r"[^A-Za-z0-9_-]", "_", str(instagram_id or "").strip())

    def _detect_image_extension(self, content: bytes, content_type: str = "", url: str = "") -> str | None:
        """Determina la extension local (.jpg, .webp, .png) y descarta respuestas JSON/HTML invalidas."""
        if not content:
            return None
        if content.startswith(b"\xff\xd8\xff"):
            return ".jpg"
        if content.startswith(b"\x89PNG\r\n\x1a\n"):
            return ".png"
        if len(content) >= 12 and content[0:4] == b"RIFF" and content[8:12] == b"WEBP":
            return ".webp"

        content_type_clean = (content_type or "").split(";")[0].strip().lower()
        if content_type_clean == "image/webp":
            return ".webp"
        if content_type_clean == "image/png":
            return ".png"
        if content_type_clean in ("image/jpeg", "image/jpg"):
            return ".jpg"

        if content_type_clean in ("application/json", "text/html", "text/plain", "application/xml"):
            return None
        stripped = content.lstrip()
        if stripped.startswith((b"{", b"[", b"<!DOCTYPE", b"<html", b"<?xml")):
            return None

        lower_path = str(url or "").lower().split("?", 1)[0].split("#", 1)[0]
        if lower_path.endswith(".webp"):
            return ".webp"
        if lower_path.endswith(".png"):
            return ".png"
        return ".jpg"

    def _store_image_bytes(
        self,
        instagram_id: str,
        content: bytes,
        content_type: str = "",
        source_url: str = "",
    ) -> str | None:
        """Persiste los bytes de la imagen en uploads/instagram/<instagram_id>.<ext> y retorna la ruta relativa."""
        safe_id = self._sanitize_instagram_id(instagram_id)
        if not safe_id or not content:
            return None
        ext = self._detect_image_extension(content, content_type=content_type, url=source_url)
        if not ext:
            return None
        try:
            instagram_dir = get_upload_dir() / "instagram"
            instagram_dir.mkdir(parents=True, exist_ok=True)
            filename = f"{safe_id}{ext}"
            target_path = instagram_dir / filename
            target_path.write_bytes(content)
            return f"/uploads/instagram/{filename}"
        except Exception as exc:
            logger.warning("[Instagram Image Sync] Error guardando imagen local para %s: %s", safe_id, exc)
            return None

    def _candidate_image_url(self, media_url: str | None, image_url: str | None) -> str:
        """Determina la URL remota de imagen o miniatura que debe descargarse localmente."""
        for raw in (image_url, media_url):
            candidate = str(raw or "").strip()
            if not candidate or candidate == self.DEFAULT_VIDEO_THUMBNAIL_FALLBACK:
                continue
            if candidate.startswith("/uploads/"):
                continue
            if not candidate.startswith(("http://", "https://")):
                continue
            if is_video_stream_url(candidate):
                continue
            if candidate.lower().startswith(("https://upa.edu.py/static/", "http://upa.edu.py/static/")):
                continue
            return candidate
        return ""

    def _apply_local_image_url(self, item: NormalizedSocialPost, local_url: str) -> None:
        """Actualiza image_url (y media_url en publicaciones que no son streams de video) con la ruta local."""
        item.image_url = local_url
        if not is_video_stream_url(item.media_url):
            item.media_url = local_url

    async def download_instagram_image_async(
        self,
        instagram_id: str,
        image_url: str,
        client: httpx.AsyncClient | None = None,
    ) -> str | None:
        """Descarga asincronamente una imagen de Instagram con timeout de 10 s y la guarda en /uploads/instagram/."""
        clean_url = (image_url or "").strip()
        safe_id = self._sanitize_instagram_id(instagram_id)
        if not safe_id or not clean_url:
            return None
        if clean_url.startswith("/uploads/"):
            return clean_url
        if not clean_url.startswith(("http://", "https://")) or is_video_stream_url(clean_url):
            return None

        async def _fetch(http_client: httpx.AsyncClient) -> str | None:
            response = await http_client.get(clean_url, timeout=10.0)
            if response.status_code != 200 or not response.content:
                logger.warning(
                    "[Instagram Image Sync] HTTP %s al descargar imagen para %s (%s)",
                    response.status_code,
                    safe_id,
                    clean_url,
                )
                return None
            return self._store_image_bytes(
                safe_id,
                response.content,
                content_type=response.headers.get("content-type", ""),
                source_url=clean_url,
            )

        try:
            if client is not None:
                return await _fetch(client)
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as owned_client:
                return await _fetch(owned_client)
        except httpx.TimeoutException as exc:
            logger.warning("[Instagram Image Sync] Timeout descargando imagen para %s (%s): %s", safe_id, clean_url, exc)
            return None
        except httpx.RequestError as exc:
            logger.warning("[Instagram Image Sync] Error de red descargando imagen para %s (%s): %s", safe_id, clean_url, exc)
            return None
        except Exception as exc:
            logger.warning("[Instagram Image Sync] Error inesperado descargando imagen para %s: %s", safe_id, exc)
            return None

    def download_instagram_image(self, instagram_id: str, image_url: str) -> str | None:
        """Descarga sincronamente una imagen de Instagram con timeout de 10 s y la guarda en /uploads/instagram/."""
        clean_url = (image_url or "").strip()
        safe_id = self._sanitize_instagram_id(instagram_id)
        if not safe_id or not clean_url:
            return None
        if clean_url.startswith("/uploads/"):
            return clean_url
        if not clean_url.startswith(("http://", "https://")) or is_video_stream_url(clean_url):
            return None

        try:
            response = httpx.get(clean_url, timeout=10.0, follow_redirects=True)
            if response.status_code != 200 or not response.content:
                logger.warning(
                    "[Instagram Image Sync] HTTP %s al descargar imagen para %s (%s)",
                    response.status_code,
                    safe_id,
                    clean_url,
                )
                return None
            return self._store_image_bytes(
                safe_id,
                response.content,
                content_type=response.headers.get("content-type", ""),
                source_url=clean_url,
            )
        except httpx.TimeoutException as exc:
            logger.warning("[Instagram Image Sync] Timeout descargando imagen para %s (%s): %s", safe_id, clean_url, exc)
            return None
        except httpx.RequestError as exc:
            logger.warning("[Instagram Image Sync] Error de red descargando imagen para %s (%s): %s", safe_id, clean_url, exc)
            return None
        except Exception as exc:
            logger.warning("[Instagram Image Sync] Error inesperado descargando imagen para %s: %s", safe_id, exc)
            return None

    async def fetch_from_graph_api(self, token: str, account_id: str = "") -> list[NormalizedSocialPost]:
        """Obtiene publicaciones recientes desde la Instagram Graph API v21.0 con timeout de 10 s."""
        clean_token = (token or "").strip()
        if not clean_token:
            return []

        params = {
            "fields": "id,caption,media_type,media_url,permalink,timestamp,thumbnail_url",
            "access_token": clean_token,
            "limit": 25,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resolved_account_id = (account_id or "").strip()
                if not resolved_account_id:
                    resolved_account_id = await self.discover_instagram_account_id(clean_token, client=client)

                if resolved_account_id:
                    url = f"{self.GRAPH_API_BASE_URL}/{resolved_account_id}/media"
                else:
                    url = "https://graph.instagram.com/me/media"

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
                        parsed = self.parse_graph_api_item(item)
                        candidate_url = self._candidate_image_url(parsed.media_url, parsed.image_url)
                        if candidate_url:
                            parsed._mirror_attempted = True
                            local_url = await self.download_instagram_image_async(
                                parsed.instagram_id,
                                candidate_url,
                                client=client,
                            )
                            if local_url:
                                self._apply_local_image_url(parsed, local_url)
                        posts.append(parsed)
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
                                    candidate_url = self._candidate_image_url(parsed.media_url, parsed.image_url)
                                    if candidate_url:
                                        parsed._mirror_attempted = True
                                        local_url = await self.download_instagram_image_async(
                                            parsed.instagram_id,
                                            candidate_url,
                                            client=client,
                                        )
                                        if local_url:
                                            self._apply_local_image_url(parsed, local_url)
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
        processed_post_ids: set[int] = set()

        try:
            for item in posts_data:
                if not item.instagram_id:
                    continue

                if item.image_url.startswith("/uploads/") and not is_video_stream_url(item.media_url):
                    item.media_url = item.image_url
                else:
                    candidate_url = self._candidate_image_url(item.media_url, item.image_url)
                    if candidate_url and not item._mirror_attempted:
                        item._mirror_attempted = True
                        local_url = self.download_instagram_image(item.instagram_id, candidate_url)
                        if local_url:
                            self._apply_local_image_url(item, local_url)

                existing_by_id = db.query(Post).filter(Post.instagram_id == item.instagram_id).first()
                existing_by_perm = None
                if (
                    item.permalink
                    and item.permalink != self.DEFAULT_PERMALINK_FALLBACK
                    and "instagram.com/" in item.permalink.lower()
                ):
                    existing_by_perm = (
                        db.query(Post)
                        .filter(Post.post_type == "INSTAGRAM", Post.permalink == item.permalink)
                        .order_by(Post.is_edited.desc(), Post.id.asc())
                        .first()
                    )

                existing = existing_by_id or existing_by_perm
                if (
                    existing_by_id is not None
                    and existing_by_perm is not None
                    and existing_by_id.id != existing_by_perm.id
                ):
                    # Fusionar duplicados creados previamente (ej. shortcode SociableKIT vs ID numerico Graph API)
                    if existing_by_perm.is_edited and not existing_by_id.is_edited:
                        existing = existing_by_perm
                        duplicate = existing_by_id
                    elif not existing_by_perm.is_edited and existing_by_id.is_edited:
                        existing = existing_by_id
                        duplicate = existing_by_perm
                    elif existing_by_perm.id < existing_by_id.id:
                        existing = existing_by_perm
                        duplicate = existing_by_id
                    else:
                        existing = existing_by_id
                        duplicate = existing_by_perm
                    db.delete(duplicate)
                    db.flush()

                teaser = extract_instagram_teaser(item.caption)
                if existing:
                    if not item.image_url.startswith("/uploads/"):
                        existing_img = existing.image_url or ""
                        existing_med = existing.media_url or ""
                        if existing_img.startswith("/uploads/"):
                            self._apply_local_image_url(item, existing_img)
                        elif existing_med.startswith("/uploads/") and not is_video_stream_url(
                            existing_med
                        ):
                            self._apply_local_image_url(item, existing_med)

                    existing.instagram_id = item.instagram_id
                    if not existing.is_edited:
                        existing.caption = teaser
                        existing.content = item.caption
                    existing.media_type = item.media_type
                    existing.media_url = item.media_url
                    existing.image_url = item.image_url
                    existing.permalink = item.permalink
                    if (
                        not existing.is_edited
                        or not existing.link_url
                        or "instagram.com" in (existing.link_url or "").lower()
                    ):
                        existing.link_url = item.permalink
                    if not existing.link_label:
                        existing.link_label = "Ver en Instagram"
                    if existing.published_at is None:
                        existing.published_at = item.timestamp or existing.created_at or datetime.now(UTC)
                    existing.updated_at = datetime.now(UTC)
                    if existing.id is not None:
                        processed_post_ids.add(existing.id)
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

                    if is_valid_ai_event and start_dt is not None:
                        end_dt = to_utc_datetime(extraction.end_time)
                        ai_title = (extraction.event_title or "").strip()[:255] or fallback_title
                        ai_location = (extraction.location or "").strip()[:255] or None
                        conservative_groups = clean_group_codes(extraction.target_groups)
                        effective_groups = conservative_groups if conservative_groups else ["ALL"]
                        notify_push = bool(extraction.notify_push)
                        push_groups = list(effective_groups) if notify_push else []
                        default_reminders = (
                            [1440, 30] if start_dt.astimezone(ASUNCION_TZ).weekday() in (5, 6) else [30]
                        )

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
                            reminders=default_reminders,
                            instagram_id=item.instagram_id,
                            media_type=item.media_type,
                            media_url=item.media_url,
                            image_url=item.image_url,
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
                            image_url=item.image_url,
                            permalink=item.permalink,
                            link_url=item.permalink,
                            link_label="Ver en Instagram",
                            author_id=author_id,
                            created_at=pub_ts,
                            published_at=pub_ts,
                        )
                    db.add(new_post)
                    created_count += 1

            # Actualizar tambien publicaciones existentes en la base de datos con URLs efimeras de Meta CDN
            existing_ig_posts = db.query(Post).filter(Post.post_type == "INSTAGRAM").all()
            for stale_post in existing_ig_posts:
                if stale_post.id in processed_post_ids:
                    continue
                stored_raw = (stale_post._stored_media_url or "").lower()
                if "cdninstagram.com" not in stored_raw and "fbcdn.net" not in stored_raw:
                    continue
                stale_candidate = self._candidate_image_url(stale_post.media_url, stale_post.image_url)
                if not stale_candidate:
                    continue
                stale_ig_id = stale_post.instagram_id or f"post_{stale_post.id}"
                local_stale_url = self.download_instagram_image(stale_ig_id, stale_candidate)
                if local_stale_url:
                    if not is_video_stream_url(stale_post.media_url):
                        stale_post.media_url = local_stale_url
                    stale_post.image_url = local_stale_url
                    stale_post.updated_at = datetime.now(UTC)
                    updated_count += 1

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
