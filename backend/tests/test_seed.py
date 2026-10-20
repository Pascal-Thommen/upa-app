"""Automated tests for UPA Campus Platform Database Seeding.

Verifies:
1. Exact field mapping for Instagram post (@upalemana) and Internal Event (Charla IA).
2. Idempotency: Repeated executions never create duplicate rows.
3. Foreign key integrity and author linking.
4. CLI execution success.

Adheres strictly to the Zero Mock Doktrin (no mocks, real database operations).
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.database import Base
from src.models import Post, User
from src.seed import (
    SEED_AUTHOR_DATA,
    SEED_INSTAGRAM_POST,
    SEED_INTERNAL_EVENT,
    main,
    seed_database,
)

TEST_DB_URL = "sqlite:///:memory:"


def setup_test_db():
    engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return testing_session()


def test_seed_database_creates_both_records():
    """Verify that seed_database populates both canonical records with accurate fields."""
    db = setup_test_db()
    try:
        posts = seed_database(db)
        assert len(posts) == 2

        # 1. Instagram Post Verification
        insta = db.query(Post).filter(Post.title == SEED_INSTAGRAM_POST["title"]).first()
        assert insta is not None
        assert insta.post_type == "INSTAGRAM"
        assert insta.is_news is True
        assert insta.is_event is False
        assert insta.has_registration is False
        assert insta.instagram_id == "upa_insta_recepcionista_2026"
        assert insta.media_type == "IMAGE"
        assert "rrhh@upa.edu.py" in insta.caption
        assert "Recepcionista" in insta.title
        assert "01a15981-3d09-7ca3-b0bc-8fe8411f4418" in insta.media_url
        assert insta.target_groups == ["ALL"]

        # 2. Internal Event Verification
        event = db.query(Post).filter(Post.title == SEED_INTERNAL_EVENT["title"]).first()
        assert event is not None
        assert event.post_type == "MANUAL"
        assert event.is_news is True
        assert event.is_event is True
        assert event.has_registration is True
        assert event.is_pinned is True
        assert event.location == "Auditorio Edificio 1, Piso 1"
        assert "Daniel Romero" in event.caption
        assert "01a15981-8ac8-7b1b-80a7-3ce474ccc846" in event.media_url
        assert event.event_start is not None

        # Author Verification
        author = db.query(User).filter(User.email == SEED_AUTHOR_DATA["email"]).first()
        assert author is not None
        assert insta.author_id == author.id
        assert event.author_id == author.id
    finally:
        db.close()


def test_seed_database_idempotency_no_duplicates():
    """Verify that multiple consecutive seeding runs produce zero duplicate rows."""
    db = setup_test_db()
    try:
        # First execution
        first_run_posts = seed_database(db)
        assert len(first_run_posts) == 2
        initial_post_count = db.query(Post).count()
        initial_user_count = db.query(User).count()
        assert initial_post_count == 2
        assert initial_user_count == 1

        # Second execution
        second_run_posts = seed_database(db)
        assert len(second_run_posts) == 2
        assert db.query(Post).count() == 2
        assert db.query(User).count() == 1

        # Third execution
        third_run_posts = seed_database(db)
        assert len(third_run_posts) == 2
        assert db.query(Post).count() == 2
        assert db.query(User).count() == 1

        # IDs remain stable across runs
        assert first_run_posts[0].id == second_run_posts[0].id == third_run_posts[0].id
        assert first_run_posts[1].id == second_run_posts[1].id == third_run_posts[1].id
    finally:
        db.close()


def test_seed_database_updates_mutated_data_idempotently():
    """Verify that if existing records were modified, re-seeding restores canonical state."""
    db = setup_test_db()
    try:
        seed_database(db)

        # Mutate caption of the Instagram post
        insta = db.query(Post).filter(Post.instagram_id == "upa_insta_recepcionista_2026").first()
        insta.caption = "Contenido desactualizado modificado manualmente"
        db.commit()

        # Verify mutation took effect
        mutated = db.query(Post).filter(Post.instagram_id == "upa_insta_recepcionista_2026").first()
        assert mutated.caption == "Contenido desactualizado modificado manualmente"

        # Re-run seeding
        seed_database(db)

        # Verify restoration of canonical content
        restored = db.query(Post).filter(Post.instagram_id == "upa_insta_recepcionista_2026").first()
        assert "¡Estamos buscando Recepcionista!" in restored.caption
        assert db.query(Post).count() == 2
    finally:
        db.close()


def test_seed_cli_main_success():
    """Verify that the CLI entry point main() returns exit code 0."""
    result = main()
    assert result == 0
