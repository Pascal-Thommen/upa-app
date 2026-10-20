from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..database import get_db
from ..models import Post, User
from ..auth import require_admin
from ..services.sociablekit import SociableKitService
from ..config import settings

router = APIRouter(prefix="/api/social", tags=["Social Media"])


@router.post("/sync", status_code=status.HTTP_200_OK)
def trigger_social_sync(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    """
    Startet die manuelle oder automatisierte Synchronisation mit SociableKIT.
    Geschützt: Nur Administratoren dürfen Synchronisationsläufe anstoßen.
    """
    service = SociableKitService()
    synced_count = service.sync_posts(db)
    
    total_instagram_posts = db.query(func.count(Post.id)).filter(Post.post_type == "INSTAGRAM").scalar() or 0
    return {
        "status": "success",
        "synced_in_this_run": synced_count,
        "total_instagram_posts": total_instagram_posts
    }


@router.get("/status")
def get_social_integration_status(db: Session = Depends(get_db)):
    """
    Liefert den aktuellen Status der Social-Media-Integration.
    Öffentlich zugänglich für Systemprüfungen und Admin-Dashboard.
    """
    total_instagram_posts = db.query(func.count(Post.id)).filter(Post.post_type == "INSTAGRAM").scalar() or 0
    return {
        "sociablekit_configured": bool(settings.SOCIABLEKIT_EMBED_ID),
        "total_instagram_posts": total_instagram_posts,
        "channel": "@upalemana"
    }
