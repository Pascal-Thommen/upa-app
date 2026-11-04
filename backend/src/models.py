from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, false, func
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import InstrumentedAttribute, Mapped, mapped_column, relationship

from .database import Base

DEFAULT_VIDEO_POSTER_FALLBACK = "/campus/icons/icon-512.png"


def is_video_stream_url(url: str | None) -> bool:
    """Detecta si una URL apunta directamente a un archivo de video reproducible (mp4, webm, mov)."""
    if not url:
        return False
    clean = str(url).strip().lower().split("?", 1)[0].split("#", 1)[0]
    return clean.endswith((".mp4", ".webm", ".mov"))


def split_stored_media_urls(raw_value: str | None) -> tuple[str | None, str | None]:
    """Separa media_url y thumbnail/image_url codificados sin requerir migracion de esquema."""
    if raw_value is None:
        return None, None
    text_val = str(raw_value)
    if "\n" in text_val:
        primary, thumb = text_val.split("\n", 1)
        clean_primary = primary.strip() or None
        clean_thumb = thumb.strip() or None
        return clean_primary, clean_thumb
    clean = text_val.strip() or None
    return clean, None


def pack_stored_media_urls(primary: str | None, thumb: str | None) -> str | None:
    """Empaqueta media_url e image_url en la columna media_url existente."""
    clean_primary = str(primary).strip() if primary and str(primary).strip() else None
    clean_thumb = str(thumb).strip() if thumb and str(thumb).strip() else None
    if clean_primary and clean_thumb and clean_thumb != clean_primary:
        return f"{clean_primary}\n{clean_thumb}"
    if clean_primary:
        return clean_primary
    if clean_thumb:
        return f"\n{clean_thumb}"
    return None


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="user", nullable=False)  # "user", "editor" o "admin"
    groups: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)  # ej. ["TIE", "Semester_4"]
    google_groups: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)  # Registros de Google Groups
    classroom_token: Mapped[str | None] = mapped_column(Text, nullable=True)  # Token de acceso OAuth para Google Classroom
    classroom_refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)  # Refresh token OAuth para renovacion automatica
    classroom_deadlines_cache: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)  # Cache persistente de entregas Classroom
    classroom_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # Marca de tiempo de ultima sincronizacion
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    # Relaciones
    posts: Mapped[list["Post"]] = relationship("Post", back_populates="author", foreign_keys="[Post.author_id]")
    registrations: Mapped[list["EventRegistration"]] = relationship(
        "EventRegistration", back_populates="user", cascade="all, delete-orphan"
    )
    post_views: Mapped[list["PostView"]] = relationship(
        "PostView", back_populates="user", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list["AdminAuditLog"]] = relationship("AdminAuditLog", back_populates="admin")
    device_tokens: Mapped[list["DeviceToken"]] = relationship(
        "DeviceToken", back_populates="user", cascade="all, delete-orphan"
    )


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    post_type: Mapped[str] = mapped_column(String(50), default="MANUAL", nullable=False)  # "INSTAGRAM", "MANUAL", "EMERGENCY_BANNER"
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)  # Categoria editorial opcional

    # Visibilidad y componentes activos (un registro puede ser noticia, evento o ambos)
    is_news: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_event: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Datos de calendario y evento
    event_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    event_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Grupos destinatarios e inscripcion RSVP
    target_groups: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    has_registration: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Notificaciones y recordatorios
    send_push_notification: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reminders: Mapped[list[int] | None] = mapped_column(JSON, nullable=True)  # Minutos previos al inicio del evento, ej. [30, 1440]
    notify_groups: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)  # Grupos a notificar al publicar o guardar el post
    event_notify_groups: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)  # Grupos que reciben recordatorios del evento

    # Boton de enlace opcional
    link_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    link_label: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Estado editorial: False = pendiente de revision, True = revisado/editado
    is_edited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default=false())
    # True si el evento fue extraido y publicado directamente por IA (Gemini multimodal)
    is_ai_generated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default=false())

    # Campos de sincronizacion con Instagram
    instagram_id: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True, index=True)
    media_type: Mapped[str | None] = mapped_column(String(50), nullable=True)  # IMAGE, VIDEO, CAROUSEL_ALBUM
    _stored_media_url: Mapped[str | None] = mapped_column("media_url", Text, nullable=True)
    permalink: Mapped[str | None] = mapped_column(Text, nullable=True)

    @hybrid_property
    def media_url(self) -> str | None:
        primary, thumb = split_stored_media_urls(self._stored_media_url)
        return primary or thumb

    @media_url.inplace.setter
    def _media_url_setter(self, value: str | None) -> None:
        existing_primary, existing_thumb = split_stored_media_urls(self._stored_media_url)
        clean_val = str(value).strip() if value and str(value).strip() else None
        if clean_val is None:
            if existing_primary is not None:
                self._stored_media_url = None
            else:
                self._stored_media_url = pack_stored_media_urls(None, existing_thumb)
            return
        if existing_thumb and (existing_primary is None or is_video_stream_url(clean_val)):
            self._stored_media_url = pack_stored_media_urls(clean_val, existing_thumb)
        else:
            self._stored_media_url = clean_val

    @media_url.inplace.expression
    @classmethod
    def _media_url_expression(cls) -> InstrumentedAttribute[str | None]:
        return cls._stored_media_url

    @hybrid_property
    def image_url(self) -> str | None:
        primary, thumb = split_stored_media_urls(self._stored_media_url)
        if thumb:
            return thumb
        if primary and not is_video_stream_url(primary):
            return primary
        mtype = str(getattr(self, "media_type", "") or "").strip().upper()
        if mtype == "VIDEO" or is_video_stream_url(primary):
            return DEFAULT_VIDEO_POSTER_FALLBACK
        return None

    @image_url.inplace.setter
    def _image_url_setter(self, value: str | None) -> None:
        existing_primary, _ = split_stored_media_urls(self._stored_media_url)
        clean_thumb = str(value).strip() if value and str(value).strip() else None
        self._stored_media_url = pack_stored_media_urls(existing_primary, clean_thumb)

    @image_url.inplace.expression
    @classmethod
    def _image_url_expression(cls) -> InstrumentedAttribute[str | None]:
        return cls._stored_media_url

    # Metadatos
    author_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    # Relaciones
    author: Mapped[User | None] = relationship("User", back_populates="posts", foreign_keys=[author_id])
    reviewed_by: Mapped[User | None] = relationship("User", foreign_keys=[reviewed_by_id])
    registrations: Mapped[list["EventRegistration"]] = relationship(
        "EventRegistration", back_populates="post", cascade="all, delete-orphan"
    )
    views: Mapped[list["PostView"]] = relationship(
        "PostView", back_populates="post", cascade="all, delete-orphan"
    )

    @property
    def status(self) -> str:
        is_edited = bool(getattr(self, "is_edited", False))
        reviewed_by_id = getattr(self, "reviewed_by_id", None)
        if reviewed_by_id is not None or is_edited:
            return "reviewed"
        if bool(getattr(self, "is_ai_generated", False)):
            return "ai"
        return "unreviewed"


class EventRegistration(Base):
    __tablename__ = "event_registrations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    post_id: Mapped[int] = mapped_column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), default="attending", nullable=False)  # "attending" o "declined"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    __table_args__ = (UniqueConstraint("post_id", "user_id", name="uq_post_user_registration"),)

    post: Mapped[Post] = relationship("Post", back_populates="registrations")
    user: Mapped[User] = relationship("User", back_populates="registrations")


class PostView(Base):
    __tablename__ = "post_views"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    post_id: Mapped[int] = mapped_column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    viewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("post_id", "user_id", name="uq_post_user_view"),)

    post: Mapped[Post] = relationship("Post", back_populates="views")
    user: Mapped[User] = relationship("User", back_populates="post_views")


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    admin_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    target_type: Mapped[str] = mapped_column(String(50), nullable=False)  # "post", "group", "role"
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    admin: Mapped[User] = relationship("User", back_populates="audit_logs")


class DeviceToken(Base):
    __tablename__ = "device_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    device_token: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(50), default="android", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (UniqueConstraint("user_id", "device_token", name="uq_user_device_token"),)

    user: Mapped[User] = relationship("User", back_populates="device_tokens")


class AudienceGroup(Base):
    __tablename__ = "audience_groups"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    google_groups: Mapped[list[str] | None] = mapped_column(JSON, default=list, nullable=True)  # Lista de correos de grupos de Google Workspace
    emails: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)


class UserRole(Base):
    __tablename__ = "user_roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    permissions: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)


class AppSetting(Base):
    """Configuracion global clave/valor persistente (por ejemplo la clave de API de Gemini)."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
