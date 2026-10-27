from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, false, func
from sqlalchemy.orm import relationship

from .database import Base


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
    device_token = Column(String(512), nullable=True)  # Token de dispositivo FCM legado
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
    push_notification_sent_at = Column(DateTime(timezone=True), nullable=True)
    reminder_minutes_before = Column(Integer, default=30, nullable=True)
    reminders = Column(JSON, nullable=True)  # Minutos previos al inicio del evento, ej. [30, 1440]
    notify_groups = Column(JSON, nullable=True)  # Grupos a notificar al publicar o guardar el post
    event_notify_groups = Column(JSON, nullable=True)  # Grupos que reciben recordatorios del evento

    # Contenido adicional exclusivo de la vista de detalle en la aplicacion
    detail_text = Column(Text, nullable=True)
    link_url = Column(Text, nullable=True)
    link_label = Column(String(100), nullable=True)

    # Estado editorial: False = pendiente de revision, True = revisado/editado
    is_edited = Column(Boolean, default=False, nullable=False, server_default=false())

    # Campos de sincronizacion con Instagram
    instagram_id = Column(String(100), unique=True, nullable=True, index=True)
    media_type = Column(String(50), nullable=True)  # IMAGE, VIDEO, CAROUSEL_ALBUM
    media_url = Column(Text, nullable=True)
    permalink = Column(Text, nullable=True)

    # Metadatos
    author_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    # Relaciones
    author = relationship("User", back_populates="posts")
    registrations = relationship("EventRegistration", back_populates="post", cascade="all, delete-orphan")
    views = relationship("PostView", back_populates="post", cascade="all, delete-orphan")


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
    badge_class = Column(String(100), nullable=False, default="bg-slate-100 text-slate-800 border-slate-200")
    google_group = Column(String(255), nullable=True)
    google_groups = Column(JSON, nullable=True)  # Lista de correos de grupos de Google Workspace
    emails = Column(JSON, default=list, nullable=False)
    is_system = Column(Boolean, default=False, nullable=False)
    parent_id = Column(
        String(50),
        ForeignKey("audience_groups.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )  # Grupo contenedor para la jerarquia (hasta 3 niveles)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)


class UserRole(Base):
    __tablename__ = "user_roles"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    role = Column(String(50), default="editor", nullable=False)  # "admin" o "editor"
    permissions = Column(JSON, default=list, nullable=False)
    is_primary = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
