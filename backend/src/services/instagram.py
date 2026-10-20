import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Post

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
    Dienst für die Synchronisation von Instagram-Beiträgen (@upalemana).
    Unterstützt Meta Instagram Graph API und SociableKIT JSON API.
    Enthält Resilienz (Timeouts, Fehlerabfang) und atomare ACID-Transaktionen.
    """

    DEFAULT_PERMALINK_FALLBACK = "https://www.instagram.com/upalemana"

    def extract_title_from_caption(self, caption: str) -> str:
        """
        Extrahiert einen prägnanten Titel aus dem Instagram-Caption.
        Nimmt die erste Zeile und kürzt bei Bedarf auf maximal 200 Zeichen.
        """
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
        """Parst ein einzelnes Element aus der Instagram Graph API."""
        media_id = str(item.get("id", ""))
        caption = item.get("caption") or ""
        media_type = item.get("media_type") or "IMAGE"
        media_url = item.get("media_url") or item.get("thumbnail_url") or ""
        permalink = item.get("permalink") or self.DEFAULT_PERMALINK_FALLBACK

        timestamp = None
        raw_ts = item.get("timestamp")
        if raw_ts:
            try:
                # ISO Format parsen: '2026-10-20T12:00:00+0000' oder '2026-10-20T12:00:00Z'
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
        """Parst ein Element aus dem SociableKIT Widget JSON Feed."""
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
        """
        Ruft neue Beiträge über die offizielle Instagram Graph API ab.
        Expliziter Timeout (10s) und Fehlerbehandlung für Statuscodes.
        """
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
                response = await client.get(url, params=params)
                if response.status_code == 401:
                    logger.error("[Instagram API] Ungültiger oder abgelaufener Access Token.")
                    return []
                if response.status_code == 429:
                    logger.warning("[Instagram API] Rate-Limit erreicht (HTTP 429).")
                    return []
                if response.status_code != 200:
                    logger.error(f"[Instagram API] Unerwarteter Statuscode: {response.status_code} - {response.text}")
                    return []

                data = response.json()
                raw_items = data.get("data", [])
                posts = []
                for item in raw_items:
                    if item.get("id"):
                        posts.append(self.parse_graph_api_item(item))
                return posts
        except httpx.RequestError as exc:
            logger.error(f"[Instagram API Netzwerkfehler] {exc}")
            return []
        except Exception as exc:
            logger.error(f"[Instagram API Fehler] {exc}")
            return []

    async def fetch_from_sociablekit(self, embed_id: str) -> list[NormalizedSocialPost]:
        """
        Ruft Beiträge über die SociableKIT Widget JSON API ab.
        Unterstützt primär data.accentapi.com/feed/{embed_id}.json und data.sociablekit.com als Fallback.
        Expliziter Timeout (10s) und Netzwerkresilienz.
        """
        urls_to_try = [
            f"https://data.accentapi.com/feed/{embed_id}.json",
            f"https://data.sociablekit.com/embeds/{embed_id}/data",
        ]

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                for url in urls_to_try:
                    try:
                        response = await client.get(url)
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
                        logger.warning(f"[SociableKIT] Anfrage an {url} fehlgeschlagen: {exc}")
                return []
                return posts
        except httpx.RequestError as exc:
            logger.error(f"[SociableKIT Netzwerkfehler] {exc}")
            return []
        except Exception as exc:
            logger.error(f"[SociableKIT Fehler] {exc}")
            return []

    def sync_posts(
        self,
        db: Session,
        posts_data: list[NormalizedSocialPost],
        author_id: int | None = None,
    ) -> dict[str, Any]:
        """
        Speichert oder aktualisiert die normalisierten Instagram-Posts in der Tabelle `posts`.
        Idempotent (Upsert anhand von `instagram_id`) und atomar (ACID).
        """
        if not posts_data:
            return {
                "status": "success",
                "message": "Keine neuen Instagram-Beiträge empfangen.",
                "synced_count": 0,
                "created_count": 0,
                "updated_count": 0,
            }

        created_count = 0
        updated_count = 0

        try:
            for item in posts_data:
                if not item.instagram_id:
                    continue

                existing = db.query(Post).filter(Post.instagram_id == item.instagram_id).first()
                if existing:
                    existing.caption = item.caption
                    existing.content = item.caption
                    existing.media_type = item.media_type
                    existing.media_url = item.media_url
                    existing.permalink = item.permalink
                    existing.updated_at = datetime.now(UTC)
                    updated_count += 1
                else:
                    title = self.extract_title_from_caption(item.caption)
                    new_post = Post(
                        title=title,
                        caption=item.caption,
                        content=item.caption,
                        post_type="INSTAGRAM",
                        is_news=True,
                        is_event=False,
                        is_pinned=False,
                        target_groups=["ALL"],
                        instagram_id=item.instagram_id,
                        media_type=item.media_type,
                        media_url=item.media_url,
                        permalink=item.permalink,
                        author_id=author_id,
                        created_at=item.timestamp or datetime.now(UTC),
                    )
                    db.add(new_post)
                    created_count += 1

            db.commit()
            return {
                "status": "success",
                "synced_count": len(posts_data),
                "created_count": created_count,
                "updated_count": updated_count,
            }
        except Exception as e:
            db.rollback()
            logger.error(f"[Instagram DB Sync Fehler] Rollback ausgeführt: {e}")
            raise e

    async def sync_instagram(self, db: Session, author_id: int | None = None) -> dict[str, Any]:
        """
        Führt den gesamten Synchronisationsprozess für UPA-Instagram aus.
        Wählt die konfigurierte Strategie (Graph API oder SociableKIT).
        """
        posts = []
        if settings.INSTAGRAM_ACCESS_TOKEN:
            logger.info("[Instagram Sync] Rufe Instagram Graph API ab...")
            posts = await self.fetch_from_graph_api(
                token=settings.INSTAGRAM_ACCESS_TOKEN,
                account_id=settings.INSTAGRAM_ACCOUNT_ID,
            )
        elif settings.SOCIABLEKIT_EMBED_ID:
            logger.info("[Instagram Sync] Rufe SociableKIT Feed ab...")
            posts = await self.fetch_from_sociablekit(embed_id=settings.SOCIABLEKIT_EMBED_ID)
        else:
            logger.info("[Instagram Sync] Keine externen Instagram-Zugangsdaten konfiguriert.")
            return {
                "status": "skipped",
                "message": "Weder INSTAGRAM_ACCESS_TOKEN noch SOCIABLEKIT_EMBED_ID konfiguriert.",
                "synced_count": 0,
                "created_count": 0,
                "updated_count": 0,
            }

        return self.sync_posts(db, posts, author_id=author_id)


instagram_service = InstagramSyncService()
