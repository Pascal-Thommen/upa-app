"""Unit tests for SQLAlchemy models in UPA App backend.

Strictly follows Zero Mock Doktrin and software-testing-audit principles.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from src.database import Base
from src.models import AdminAuditLog, EventRegistration, Post, PostView, User


@pytest.fixture
def db_session():
    """Provides an isolated in-memory transactional database session with SQLite foreign keys enabled."""
    engine = create_engine("sqlite:///:memory:", echo=False)

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session: Session = session_factory()

    try:
        yield session
    finally:
        session.rollback()
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_models_metadata_registered():
    """Verify that all tables are properly registered in SQLAlchemy metadata."""
    tables = Base.metadata.tables
    assert "users" in tables
    assert "posts" in tables
    assert "event_registrations" in tables
    assert "post_views" in tables
    assert "admin_audit_logs" in tables


def test_user_creation_and_attributes(db_session: Session):
    """Validates user creation with all campus profile fields."""
    user = User(
        email="p.thommen@upa.edu.py",
        full_name="Pascal Thommen",
        role="admin",
        career="Wirtschaftsinformatik",
        semester=4,
        profile_picture_url="https://upa.edu.py/profiles/pascal.jpg",
        groups=["TIE", "Semester_4"],
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    assert user.id is not None
    assert user.email == "p.thommen@upa.edu.py"
    assert user.full_name == "Pascal Thommen"
    assert user.role == "admin"
    assert user.career == "Wirtschaftsinformatik"
    assert user.semester == 4
    assert user.groups == ["TIE", "Semester_4"]
    assert user.is_active is True
    assert user.created_at is not None
    assert user.updated_at is not None

    user_dict = user.to_dict()
    assert user_dict["email"] == "p.thommen@upa.edu.py"
    assert "TIE" in user_dict["groups"]


def test_user_email_uniqueness_enforced(db_session: Session):
    """Ensures unique constraint on user email prevents duplicates."""
    user1 = User(
        email="duplicate@upa.edu.py",
        full_name="User One",
        role="student",
    )
    db_session.add(user1)
    db_session.commit()

    user2 = User(
        email="duplicate@upa.edu.py",
        full_name="User Two",
        role="student",
    )
    db_session.add(user2)

    with pytest.raises(IntegrityError):
        db_session.commit()

    db_session.rollback()


def test_post_creation_with_event_and_instagram(db_session: Session):
    """Validates post creation with news, event, and Instagram fields."""
    author = User(
        email="marketing@upa.edu.py",
        full_name="Marketing Team",
        role="admin",
    )
    db_session.add(author)
    db_session.commit()
    db_session.refresh(author)

    expires = datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC)
    post = Post(
        title="Torneo Interfacultades UPA",
        caption="Gran apertura este viernes",
        content="Información detallada del evento deportivo con todas las carreras.",
        post_type="INSTAGRAM",
        is_news=True,
        is_event=True,
        is_pinned=True,
        is_urgent=False,
        expires_at=expires,
        location="Canchas Campus Central",
        target_groups=["ALL", "TIE"],
        has_registration=True,
        reminder_minutes_before=60,
        instagram_id="insta_12345",
        media_type="CAROUSEL_ALBUM",
        media_url="https://instagram.com/media/12345.jpg",
        permalink="https://instagram.com/p/12345",
        author_id=author.id,
    )
    db_session.add(post)
    db_session.commit()
    db_session.refresh(post)

    assert post.id is not None
    assert post.title == "Torneo Interfacultades UPA"
    assert post.is_news is True
    assert post.is_event is True
    assert post.is_pinned is True
    assert post.instagram_id == "insta_12345"
    assert post.media_type == "CAROUSEL_ALBUM"
    assert post.author.email == "marketing@upa.edu.py"
    assert len(author.posts) == 1

    post_dict = post.to_dict()
    assert post_dict["id"] == post.id
    assert post_dict["title"] == "Torneo Interfacultades UPA"
    assert post_dict["post_type"] == "INSTAGRAM"


def test_event_registration_and_cascade_delete(db_session: Session):
    """Validates registration status and cascade delete on post removal."""
    user = User(email="attendee@upa.edu.py", full_name="Student Attendee")
    post = Post(title="Workshop Python", is_news=True)
    db_session.add_all([user, post])
    db_session.commit()

    reg = EventRegistration(post_id=post.id, user_id=user.id, status="attending")
    db_session.add(reg)
    db_session.commit()

    assert reg.id is not None
    assert reg.status == "attending"

    # Verify duplicate registration is rejected by unique constraint
    dup_reg = EventRegistration(post_id=post.id, user_id=user.id, status="declined")
    db_session.add(dup_reg)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # Cascade delete post
    db_session.delete(post)
    db_session.commit()

    remaining_reg = db_session.query(EventRegistration).filter_by(user_id=user.id).first()
    assert remaining_reg is None


def test_post_view_and_admin_audit_log(db_session: Session):
    """Validates post view logging and admin audit logging."""
    user = User(email="viewer@upa.edu.py", full_name="Viewer")
    admin = User(email="admin.audit@upa.edu.py", full_name="Auditor", role="admin")
    post = Post(title="Noticia General", is_news=True)
    db_session.add_all([user, admin, post])
    db_session.commit()

    view = PostView(post_id=post.id, user_id=user.id)
    audit = AdminAuditLog(
        admin_id=admin.id,
        action="CREATE_POST",
        target_type="post",
        target_id=post.id,
        details={"title": post.title, "groups": ["ALL"]},
    )
    db_session.add_all([view, audit])
    db_session.commit()

    assert view.id is not None
    assert audit.id is not None
    assert audit.action == "CREATE_POST"
    assert audit.details["title"] == "Noticia General"
