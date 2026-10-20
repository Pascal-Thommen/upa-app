from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import relationship

from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    full_name = Column(String(255), nullable=False)
    role = Column(String(50), default="user", nullable=False)  # "user" oder "admin"
    groups = Column(JSON, default=list, nullable=False)  # z. B. ["TIE", "Semester_4"]
    classroom_token = Column(Text, nullable=True)  # Optionaler Google Access Token für Classroom API
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    # Beziehungen
    posts = relationship("Post", back_populates="author")
    registrations = relationship("EventRegistration", back_populates="user", cascade="all, delete-orphan")
    post_views = relationship("PostView", back_populates="user", cascade="all, delete-orphan")
    audit_logs = relationship("AdminAuditLog", back_populates="admin")


class Post(Base):
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    caption = Column(Text, nullable=True)
    content = Column(Text, nullable=True)
    post_type = Column(String(50), default="MANUAL", nullable=False)  # "INSTAGRAM", "MANUAL", "EMERGENCY_BANNER"
    
    # Sichtbarkeit & Priorität
    is_news = Column(Boolean, default=True, nullable=False)
    is_event = Column(Boolean, default=False, nullable=False)
    is_pinned = Column(Boolean, default=False, nullable=False)  # Oben anheften
    expires_at = Column(DateTime(timezone=True), nullable=True)  # Für Eilmeldungen

    # Kalender & Veranstaltungsdaten
    event_start = Column(DateTime(timezone=True), nullable=True)
    event_end = Column(DateTime(timezone=True), nullable=True)
    location = Column(String(255), nullable=True)

    # Zielgruppen & Anmeldung
    target_groups = Column(JSON, default=list, nullable=False)  # z. B. ["TIE", "ALL"]
    has_registration = Column(Boolean, default=False, nullable=False)  # An-/Abmelde-Button aktiv

    # Benachrichtigungen & Erinnerungen
    send_push_notification = Column(Boolean, default=False, nullable=False)  # Häkchen in Admin
    push_notification_sent_at = Column(DateTime(timezone=True), nullable=True)
    reminder_minutes_before = Column(Integer, default=30, nullable=True)  # Standard 30 Min vor Event

    # Instagram API Felder
    instagram_id = Column(String(100), unique=True, nullable=True, index=True)
    media_type = Column(String(50), nullable=True)  # IMAGE, VIDEO, CAROUSEL_ALBUM
    media_url = Column(Text, nullable=True)
    permalink = Column(Text, nullable=True)

    # Metadaten
    author_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    # Beziehungen
    author = relationship("User", back_populates="posts")
    registrations = relationship("EventRegistration", back_populates="post", cascade="all, delete-orphan")
    views = relationship("PostView", back_populates="post", cascade="all, delete-orphan")


class EventRegistration(Base):
    __tablename__ = "event_registrations"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(50), default="attending", nullable=False)  # "attending" oder "declined"
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    __table_args__ = (
        UniqueConstraint("post_id", "user_id", name="uq_post_user_registration"),
    )

    post = relationship("Post", back_populates="registrations")
    user = relationship("User", back_populates="registrations")


class PostView(Base):
    __tablename__ = "post_views"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    viewed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("post_id", "user_id", name="uq_post_user_view"),
    )

    post = relationship("Post", back_populates="views")
    user = relationship("User", back_populates="post_views")


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    admin_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    action = Column(String(100), nullable=False)  # z. B. "CREATE_POST", "TRIGGER_PUSH", "DELETE_BANNER"
    target_type = Column(String(50), nullable=False)  # "post", "user"
    target_id = Column(Integer, nullable=True)
    details = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    admin = relationship("User", back_populates="audit_logs")
