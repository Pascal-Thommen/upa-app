from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class User(Base):
    """User model representing university students, faculty, and administrative staff.
    
    Adheres to UPA identity specification: authenticates via Google OAuth domain @upa.edu.py,
    stores campus role, academic career, and semester.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="student", server_default="student")
    career: Mapped[str | None] = mapped_column(String(100), nullable=True)
    semester: Mapped[int | None] = mapped_column(Integer, nullable=True)
    profile_picture_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationship to authored news / posts
    news: Mapped[list["News"]] = relationship(
        "News",
        back_populates="author",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def to_dict(self) -> dict[str, Any]:
        """Serializes user record to dictionary representation."""
        return {
            "id": self.id,
            "email": self.email,
            "full_name": self.full_name,
            "role": self.role,
            "career": self.career,
            "semester": self.semester,
            "profile_picture_url": self.profile_picture_url,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email='{self.email}', role='{self.role}')>"


class News(Base):
    """News and campus posts model (Single Source of Truth for announcements, events, and feeds).
    
    Supports emergency banners with expiration dates, full web push payloads,
    and target audience segmentation.
    """

    __tablename__ = "news"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False, default="news", server_default="news")
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_urgent: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    visible_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    target_audience: Mapped[str | None] = mapped_column(String(255), nullable=True)
    author_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    is_published: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Bidirectional relationship to author
    author: Mapped["User"] = relationship("User", back_populates="news")

    def to_dict(self) -> dict[str, Any]:
        """Serializes news record to dictionary representation."""
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "summary": self.summary,
            "category": self.category,
            "image_url": self.image_url,
            "is_urgent": self.is_urgent,
            "visible_until": self.visible_until.isoformat() if self.visible_until else None,
            "target_audience": self.target_audience,
            "author_id": self.author_id,
            "is_published": self.is_published,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return f"<News(id={self.id}, title='{self.title[:30]}', author_id={self.author_id})>"
