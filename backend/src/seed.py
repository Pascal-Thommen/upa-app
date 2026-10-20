"""Database Seeding Script for UPA Campus Platform.

Seeds authentic UPA campus data idempotently into PostgreSQL (or configured database):
1. Instagram Post (@upalemana): Job opening for Receptionist.
2. Internal Event (Charla IA): Keynote on AI and humanity by Dr. Daniel Romero.

Adheres strictly to the UPA App contract and Zero Mock Doktrin.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

# Ensure backend directory is in path when executed directly
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from src.database import Base, SessionLocal, engine  # noqa: E402
from src.models import Post, User  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed")

# -----------------------------------------------------------------------------
# Canonical Real-World Campus Datasets
# -----------------------------------------------------------------------------

SEED_AUTHOR_DATA = {
    "email": "rrhh@upa.edu.py",
    "full_name": "UPA Talento Humano y Comunicación",
    "role": "admin",
    "career": "Administración Campus",
    "semester": None,
    "groups": ["STAFF", "ADMIN"],
    "is_active": True,
}

SEED_INSTAGRAM_POST: dict[str, Any] = {
    "title": "Búsqueda Laboral: Recepcionista",
    "caption": (
        "¡Estamos buscando Recepcionista! Si sos una persona proactiva y con vocación de atención, "
        "¡queremos conocerte! Enviá tu CV a rrhh@upa.edu.py. Referencia: Recepción. ¡Sumate al equipo de la UPA!"
    ),
    "content": (
        "¡Estamos buscando Recepcionista!\n\n"
        "Si sos una persona proactiva y con vocación de atención, ¡queremos conocerte!\n\n"
        "Enviá tu CV a rrhh@upa.edu.py\n"
        "Referencia: Recepción\n\n"
        "¡Sumate al equipo de la UPA!"
    ),
    "post_type": "INSTAGRAM",
    "is_news": True,
    "is_event": False,
    "is_pinned": False,
    "is_urgent": False,
    "has_registration": False,
    "instagram_id": "upa_insta_recepcionista_2026",
    "media_type": "IMAGE",
    "media_url": "https://multica.eu1.netbird.services/api/attachments/01a15981-3d09-7ca3-b0bc-8fe8411f4418/download",
    "permalink": "https://www.instagram.com/p/upa-recepcionista-busqueda/",
    "target_groups": ["ALL"],
}

SEED_INTERNAL_EVENT: dict[str, Any] = {
    "title": "¿Qué significa seguir siendo humanos en la era de la IA?",
    "caption": (
        "Inteligencia artificial, decisiones, libertad y responsabilidad. "
        "Disertante: Daniel Romero (Doctor en Ciencias de la Computación, Univ. Politécnica de Valencia)."
    ),
    "content": (
        "¿Qué significa seguir siendo humanos en la era de la IA?\n\n"
        "• Tema: Inteligencia artificial, decisiones, libertad y responsabilidad\n"
        "• Referente / Disertante: Daniel Romero (Doctor en Ciencias de la Computación, Univ. Politécnica de Valencia)\n"
        "• Termin / Fecha: Miércoles 14, 11:00 HS\n"
        "• Ort / Lugar: Auditorio Edificio 1, Piso 1\n"
        "• Modalidad: Presencial con registro previo requerido."
    ),
    "post_type": "MANUAL",
    "is_news": True,
    "is_event": True,
    "is_pinned": True,
    "is_urgent": False,
    "has_registration": True,
    "event_start": datetime(2026, 10, 14, 11, 0, 0, tzinfo=UTC),
    "event_end": datetime(2026, 10, 14, 12, 30, 0, tzinfo=UTC),
    "location": "Auditorio Edificio 1, Piso 1",
    "media_type": "IMAGE",
    "media_url": "https://multica.eu1.netbird.services/api/attachments/01a15981-8ac8-7b1b-80a7-3ce474ccc846/download",
    "target_groups": ["ALL"],
}


def ensure_author_user(db: Session) -> User:
    """Retrieves or creates the canonical author user for campus announcements."""
    author = db.query(User).filter(User.email == SEED_AUTHOR_DATA["email"]).first()
    if not author:
        author = User(**SEED_AUTHOR_DATA)
        db.add(author)
        db.flush()
        logger.info("Created campus author user: %s (id=%s)", author.email, author.id)
    else:
        logger.info("Existing campus author user found: %s (id=%s)", author.email, author.id)
    return author


def seed_database(db: Session | None = None) -> list[Post]:
    """Seeds the database idempotently with authentic campus data.

    Returns the list of seeded Post records [instagram_post, internal_event].
    """
    owns_session = False
    if db is None:
        owns_session = True
        Base.metadata.create_all(bind=engine)
        db = SessionLocal()

    seeded_posts: list[Post] = []
    try:
        author = ensure_author_user(db)

        # 1. Instagram Post: Búsqueda Laboral Recepcionista
        insta_query = db.query(Post).filter(
            or_(
                Post.instagram_id == SEED_INSTAGRAM_POST["instagram_id"],
                Post.title == SEED_INSTAGRAM_POST["title"],
            )
        )
        existing_insta = insta_query.first()

        if existing_insta:
            for key, val in SEED_INSTAGRAM_POST.items():
                setattr(existing_insta, key, val)
            existing_insta.author_id = author.id
            insta_post = existing_insta
            logger.info("Updated existing Instagram post (id=%s, title='%s')", insta_post.id, insta_post.title)
        else:
            insta_post = Post(**SEED_INSTAGRAM_POST, author_id=author.id)
            db.add(insta_post)
            db.flush()
            logger.info("Inserted new Instagram post (id=%s, title='%s')", insta_post.id, insta_post.title)
        seeded_posts.append(insta_post)

        # 2. Internal Event: Charla IA Daniel Romero
        event_query = db.query(Post).filter(
            Post.title == SEED_INTERNAL_EVENT["title"]
        )
        existing_event = event_query.first()

        if existing_event:
            for key, val in SEED_INTERNAL_EVENT.items():
                setattr(existing_event, key, val)
            existing_event.author_id = author.id
            event_post = existing_event
            logger.info("Updated existing Event post (id=%s, title='%s')", event_post.id, event_post.title)
        else:
            event_post = Post(**SEED_INTERNAL_EVENT, author_id=author.id)
            db.add(event_post)
            db.flush()
            logger.info("Inserted new Event post (id=%s, title='%s')", event_post.id, event_post.title)
        seeded_posts.append(event_post)

        db.commit()
        for post in seeded_posts:
            db.refresh(post)
        logger.info("Database seeding successfully completed. %d records committed.", len(seeded_posts))
        return seeded_posts

    except Exception as exc:
        db.rollback()
        logger.error("Database seeding failed: %s", exc)
        raise exc
    finally:
        if owns_session:
            db.close()


def main() -> int:
    """CLI entry point for seeding execution."""
    logger.info("Starting UPA Campus Platform Database Seeding...")
    try:
        posts = seed_database()
        logger.info("Successfully seeded %d posts into database:", len(posts))
        for p in posts:
            logger.info(" - [%s] (id=%d) %s (is_news=%s, is_event=%s)", p.post_type, p.id, p.title, p.is_news, p.is_event)
        return 0
    except Exception as exc:
        logger.error("Seeding aborted with error: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
