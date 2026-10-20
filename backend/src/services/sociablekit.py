import logging
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Post

logger = logging.getLogger(__name__)


class SociableKitService:
    def __init__(self, embed_id: str | None = None, api_url: str | None = None):
        self.embed_id = embed_id or settings.SOCIABLEKIT_EMBED_ID
        self.api_url = api_url or settings.SOCIABLEKIT_API_URL

    def fetch_posts_from_api(self) -> list[dict[str, Any]]:
        """
        Ruft Posts von der SociableKIT JSON-API ab.
        Resilienz: 10s Timeout, Fehlerabfang bei Netzwerk- oder Dienstausfällen.
        """
        if not self.embed_id:
            logger.warning("[SociableKit] Keine embed_id konfiguriert.")
            return []

        url = f"{self.api_url}?embed_id={self.embed_id}"
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(url)
                if response.status_code != 200:
                    logger.error(f"[SociableKit] API HTTP {response.status_code}: {response.text[:200]}")
                    return []
                data = response.json()
                if isinstance(data, dict):
                    return data.get("data", [])
                elif isinstance(data, list):
                    return data
                return []
        except Exception as e:
            logger.error(f"[SociableKit] Verbindungsfehler: {e}")
            return []

    def sync_posts(self, db: Session, raw_posts: list[dict[str, Any]] | None = None) -> int:
        """
        Synchronisiert Posts mit der relationalen PostgreSQL-Datenbank.
        - Deduplizierung anhand der instagram_id.
        - Aktualisierung bei bestehenden Beiträgen.
        - Neuanlage bei neuen Beiträgen.
        """
        posts_data = raw_posts if raw_posts is not None else self.fetch_posts_from_api()
        if not posts_data:
            return 0

        synced_count = 0
        for item in posts_data:
            post_id = str(item.get("id") or item.get("post_id") or "")
            if not post_id:
                continue

            caption = item.get("caption") or item.get("content") or ""
            media_url = item.get("media_url") or item.get("image_url") or item.get("thumbnail_url") or ""
            permalink = item.get("permalink") or item.get("link") or f"https://www.instagram.com/p/{post_id}"
            media_type = item.get("media_type") or "IMAGE"

            # Titel aus erster Zeile der Caption generieren
            title = ""
            if caption:
                lines = [line.strip() for line in caption.split("\n") if line.strip()]
                if lines:
                    title = lines[0][:100]
            if not title:
                title = "Instagram Post"

            existing = db.query(Post).filter(Post.instagram_id == post_id).first()
            if existing:
                existing.caption = caption
                existing.content = caption
                existing.media_url = media_url
                existing.permalink = permalink
                existing.media_type = media_type
                existing.updated_at = datetime.now(UTC)
            else:
                new_post = Post(
                    title=title,
                    caption=caption,
                    content=caption,
                    post_type="INSTAGRAM",
                    is_news=True,
                    is_event=False,
                    is_pinned=False,
                    target_groups=["ALL"],
                    instagram_id=post_id,
                    media_type=media_type,
                    media_url=media_url,
                    permalink=permalink
                )
                db.add(new_post)
            synced_count += 1

        db.commit()
        return synced_count
