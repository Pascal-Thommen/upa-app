from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, false, func
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import relationship

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

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    full_name = Column(String(255), nullable=False)
    role = Column(String(50), default="user", nullable=False)  # "user", "editor" o "admin"
    groups = Column(JSON, default=list, nullable=False)  # ej. ["TIE", "Semester_4"]
    google_groups = Column(JSON, default=list, nullable=False)  # Registros de Google Groups
    classroom_token = Column(Text, nullable=True)  # Token de acceso OAuth para Google Classroom
    classroom_refresh_token = Column(Text, nullable=True)  # Refresh token OAuth para renovacion automatica
    classroom_deadlines_cache = Column(JSON, default=list, nullable=False)  # Cache persistente de entregas Classroom
    classroom_synced_at = Column(DateTime(timezone=True), nullable=True)  # Marca de tiempo de ultima sincronizacion
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    # Relaciones
    posts = relationship("Post", back_populates="author")
    registrations = relationship("EventRegistration", back_populates="user", cascade="all, delete-orphan")
    post_views = relationship("PostView", back_populates="user", cascade="all, delete-orphan")
    audit_logs = relationship("AdminAuditLog", back_populates="admin")
    device_tokens = relationship("DeviceToken", back_populates="user", cascade="all, delete-orphan")


class Post(Base):
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    caption = Column(Text, nullable=True)
    content = Column(Text, nullable=True)
    post_type = Column(String(50), default="MANUAL", nullable=False)  # "INSTAGRAM", "MANUAL", "EMERGENCY_BANNER"
    category = Column(String(50), nullable=True)  # Categoria editorial opcional

    # Visibilidad y componentes activos (un registro puede ser noticia, evento o ambos)
    is_news = Column(Boolean, default=True, nullable=False)
    is_event = Column(Boolean, default=False, nullable=False)
    is_pinned = Column(Boolean, default=False, nullable=False)
    published_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # Datos de calendario y evento
    event_start = Column(DateTime(timezone=True), nullable=True)
    event_end = Column(DateTime(timezone=True), nullable=True)
    location = Column(String(255), nullable=True)

    # Grupos destinatarios e inscripcion RSVP
    target_groups = Column(JSON, default=list, nullable=False)
    has_registration = Column(Boolean, default=False, nullable=False)

    # Notificaciones y recordatorios
    send_push_notification = Column(Boolean, default=False, nullable=False)
    reminders = Column(JSON, nullable=True)  # Minutos previos al inicio del evento, ej. [30, 1440]
    notify_groups = Column(JSON, nullable=True)  # Grupos a notificar al publicar o guardar el post
    event_notify_groups = Column(JSON, nullable=True)  # Grupos que reciben recordatorios del evento

    # Boton de enlace opcional
    link_url = Column(Text, nullable=True)
    link_label = Column(String(100), nullable=True)

    # Estado editorial: False = pendiente de revision, True = revisado/editado
    is_edited = Column(Boolean, default=False, nullable=False, server_default=false())
    # True si el evento fue extraido y publicado directamente por IA (Gemini multimodal)
    is_ai_generated = Column(Boolean, default=False, nullable=False, server_default=false())

    # Campos de sincronizacion con Instagram
    instagram_id = Column(String(100), unique=True, nullable=True, index=True)
    media_type = Column(String(50), nullable=True)  # IMAGE, VIDEO, CAROUSEL_ALBUM
    _stored_media_url = Column("media_url", Text, nullable=True)
    permalink = Column(Text, nullable=True)

    @hybrid_property
    def media_url(self) -> str | None:
        primary, thumb = split_stored_media_urls(self._stored_media_url)
        return primary or thumb

    @media_url.setter
    def media_url(self, value: str | None) -> None:
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

    @media_url.expression
    def media_url(cls):
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

    @image_url.setter
    def image_url(self, value: str | None) -> None:
        existing_primary, _ = split_stored_media_urls(self._stored_media_url)
        clean_thumb = str(value).strip() if value and str(value).strip() else None
        self._stored_media_url = pack_stored_media_urls(existing_primary, clean_thumb)

    @image_url.expression
    def image_url(cls):
        return cls._stored_media_url

    # Metadatos
    author_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    # Relaciones
    author = relationship("User", back_populates="posts")
    registrations = relationship("EventRegistration", back_populates="post", cascade="all, delete-orphan")
    views = relationship("PostView", back_populates="post", cascade="all, delete-orphan")

    @property
    def status(self) -> str:
        if bool(getattr(self, "is_ai_generated", False)) and not bool(getattr(self, "is_edited", False)):
            return "ai"
        if bool(getattr(self, "is_edited", False)) or (getattr(self, "post_type", "MANUAL") != "INSTAGRAM"):
            return "edited"
        return "pending"


class EventRegistration(Base):
    __tablename__ = "event_registrations"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(50), default="attending", nullable=False)  # "attending" o "declined"
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    __table_args__ = (UniqueConstraint("post_id", "user_id", name="uq_post_user_registration"),)

    post = relationship("Post", back_populates="registrations")
    user = relationship("User", back_populates="registrations")


class PostView(Base):
    __tablename__ = "post_views"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    viewed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("post_id", "user_id", name="uq_post_user_view"),)

    post = relationship("Post", back_populates="views")
    user = relationship("User", back_populates="post_views")


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    admin_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    action = Column(String(100), nullable=False)
    target_type = Column(String(50), nullable=False)  # "post", "group", "role"
    target_id = Column(Integer, nullable=True)
    target_key = Column(String(255), nullable=True, index=True)
    details = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    admin = relationship("User", back_populates="audit_logs")


class DeviceToken(Base):
    __tablename__ = "device_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    device_token = Column(String(512), nullable=False, index=True)
    platform = Column(String(50), default="android", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "device_token", name="uq_user_device_token"),)

    user = relationship("User", back_populates="device_tokens")


class AudienceGroup(Base):
    __tablename__ = "audience_groups"

    id = Column(String(50), primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    google_groups = Column(JSON, default=list, nullable=True)  # Lista de correos de grupos de Google Workspace
    emails = Column(JSON, default=list, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)


class UserRole(Base):
    __tablename__ = "user_roles"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    permissions = Column(JSON, default=list, nullable=False)
    is_primary = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)


class AppSetting(Base):
    """Configuracion global clave/valor persistente (por ejemplo la clave de API de Gemini)."""

    __tablename__ = "app_settings"

    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=False, default="")
    updated_by = Column(String(255), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
