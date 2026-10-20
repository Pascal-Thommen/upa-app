"""Database models for UPA App Campus Platform.

Single Source of Truth: Posts unify news, campus announcements, calendar events,
and official Instagram media in a single relational model.
"""

from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship

from .database import Base


class User(Base):
    """User model representing students, faculty, and administrative staff."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    full_name = Column(String(255), nullable=False)
    role = Column(String(50), default="student", server_default="student", nullable=False)
    career = Column(String(100), nullable=True)
    semester = Column(Integer, nullable=True)
    profile_picture_url = Column(String(500), nullable=True)
    groups = Column(JSON, default=list, nullable=False)
    is_active = Column(Boolean, default=True, server_default="true", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    posts = relationship("Post", back_populates="author", cascade="all, delete-orphan", passive_deletes=True)
    registrations = relationship("EventRegistration", back_populates="user", cascade="all, delete-orphan")
    post_views = relationship("PostView", back_populates="user", cascade="all, delete-orphan")
    audit_logs = relationship("AdminAuditLog", back_populates="admin")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "email": self.email,
            "full_name": self.full_name,
            "role": self.role,
            "career": self.career,
            "semester": self.semester,
            "profile_picture_url": self.profile_picture_url,
            "groups": self.groups,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email='{self.email}', role='{self.role}')>"


class Post(Base):
    """Post model: Single Source of Truth for news, announcements, events, and Instagram posts."""

    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    caption = Column(Text, nullable=True)
    content = Column(Text, nullable=True)
    post_type = Column(String(50), default="MANUAL", server_default="MANUAL", nullable=False)

    # Visibility & Priority
    is_news = Column(Boolean, default=True, server_default="true", nullable=False)
    is_event = Column(Boolean, default=False, server_default="false", nullable=False)
    is_pinned = Column(Boolean, default=False, server_default="false", nullable=False)
    is_urgent = Column(Boolean, default=False, server_default="false", nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # Calendar & Event details
    event_start = Column(DateTime(timezone=True), nullable=True)
    event_end = Column(DateTime(timezone=True), nullable=True)
    location = Column(String(255), nullable=True)

    # Target audiences & registration
    target_groups = Column(JSON, default=list, nullable=False)
    has_registration = Column(Boolean, default=False, server_default="false", nullable=False)

    # Notifications & Reminders
    send_push_notification = Column(Boolean, default=False, server_default="false", nullable=False)
    push_notification_sent_at = Column(DateTime(timezone=True), nullable=True)
    reminder_minutes_before = Column(Integer, default=30, nullable=True)

    # Instagram API metadata
    instagram_id = Column(String(100), unique=True, nullable=True, index=True)
    media_type = Column(String(50), nullable=True)
    media_url = Column(Text, nullable=True)
    permalink = Column(Text, nullable=True)

    # Author and Timestamps
    author_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    author = relationship("User", back_populates="posts")
    registrations = relationship("EventRegistration", back_populates="post", cascade="all, delete-orphan")
    views = relationship("PostView", back_populates="post", cascade="all, delete-orphan")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "caption": self.caption,
            "content": self.content,
            "post_type": self.post_type,
            "is_news": self.is_news,
            "is_event": self.is_event,
            "is_pinned": self.is_pinned,
            "is_urgent": self.is_urgent,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "target_groups": self.target_groups,
            "instagram_id": self.instagram_id,
            "media_type": self.media_type,
            "media_url": self.media_url,
            "permalink": self.permalink,
            "author_id": self.author_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return f"<Post(id={self.id}, title='{self.title[:30]}', is_news={self.is_news})>"


# Alias for compatibility
News = Post


class EventRegistration(Base):
    __tablename__ = "event_registrations"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    post_id = Column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(50), default="attending", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    __table_args__ = (
        UniqueConstraint("post_id", "user_id", name="uq_post_user_registration"),
    )

    post = relationship("Post", back_populates="registrations")
    user = relationship("User", back_populates="registrations")


class PostView(Base):
    __tablename__ = "post_views"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
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

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    admin_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    action = Column(String(100), nullable=False)
    target_type = Column(String(50), nullable=False)
    target_id = Column(Integer, nullable=True)
    details = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    admin = relationship("User", back_populates="audit_logs")
