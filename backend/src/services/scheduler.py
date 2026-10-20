import asyncio
import logging

from ..config import settings
from ..database import SessionLocal
from .instagram import instagram_service

logger = logging.getLogger(__name__)

_scheduler_task: asyncio.Task | None = None


async def _feed_sync_loop():
    """Hintergrund-Worker, der periodisch neue Instagram-Beiträge abruft."""
    logger.info("[Feed Scheduler] Worker gestartet.")
    while True:
        try:
            if settings.FEED_SYNC_ENABLED:
                logger.info("[Feed Scheduler] Starte periodische Instagram-Synchronisation...")
                db = SessionLocal()
                try:
                    result = await instagram_service.sync_instagram(db)
                    logger.info(f"[Feed Scheduler] Sync-Ergebnis: {result}")
                finally:
                    db.close()
        except asyncio.CancelledError:
            logger.info("[Feed Scheduler] Worker beendet (Cancelled).")
            break
        except Exception as e:
            logger.error(f"[Feed Scheduler Fehler] {e}")

        # Intervall aus Konfiguration (Standard: 60 Minuten)
        interval_seconds = max(settings.FEED_SYNC_INTERVAL_MINUTES * 60, 60)
        try:
            await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            logger.info("[Feed Scheduler] Sleep abgebrochen bei Shutdown.")
            break


def start_feed_sync_scheduler() -> asyncio.Task | None:
    """Startet den periodischen Feed-Synchronisations-Task."""
    global _scheduler_task
    if settings.FEED_SYNC_ENABLED and _scheduler_task is None:
        _scheduler_task = asyncio.create_task(_feed_sync_loop())
        return _scheduler_task
    return None


def stop_feed_sync_scheduler() -> None:
    """Beendet den periodischen Feed-Synchronisations-Task ordnungsgemäß."""
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        _scheduler_task.cancel()
        _scheduler_task = None
