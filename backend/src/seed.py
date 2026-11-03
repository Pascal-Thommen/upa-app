import json
import re
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from .database import SessionLocal, engine, run_alembic_migrations
from .models import AdminAuditLog, AudienceGroup, Post, User, UserRole
from .schemas.post import normalize_instagram_url
from .schemas.user import REDUNDANT_GROUP_TAGS, sanitize_user_groups

_SEED_LINE_UPLOAD_RE = re.compile(r"^https?://[^/\s]+/uploads/", re.IGNORECASE)
_SEED_ANY_UPLOAD_RE = re.compile(r"https?://[^/\s\"']+/uploads/", re.IGNORECASE)


def _normalize_stored_upload_urls(db: Session) -> None:
    """Normaliza rutas heredadas con IP/Host antes de /uploads/ y enlaces canonicos de Instagram."""
    for post in db.query(Post).filter(Post._stored_media_url.isnot(None)).all():
        raw_val = post._stored_media_url
        if not raw_val or "/uploads/" not in raw_val:
            continue
        lines = raw_val.split("\n")
        cleaned_lines = [
            _SEED_LINE_UPLOAD_RE.sub("/uploads/", line.strip()) if line.strip() else ""
            for line in lines
        ]
        cleaned_val = "\n".join(cleaned_lines)
        if cleaned_val != raw_val:
            post._stored_media_url = cleaned_val

    for post in db.query(Post).filter(Post.link_url.isnot(None)).all():
        if post.link_url and "/uploads/" in post.link_url:
            cleaned_link = _SEED_LINE_UPLOAD_RE.sub("/uploads/", post.link_url.strip())
            if cleaned_link != post.link_url:
                post.link_url = cleaned_link

    for post in db.query(Post).all():
        is_ig = (post.post_type or "").strip().upper() == "INSTAGRAM"
        raw_perm = (post.permalink or "").strip()
        raw_link = (post.link_url or "").strip()
        if is_ig or "instagram.com" in raw_perm.lower() or "instagram.com" in raw_link.lower():
            norm_perm = normalize_instagram_url(
                raw_perm or (raw_link if is_ig else ""),
                instagram_id=post.instagram_id,
                media_type=post.media_type,
                is_instagram=is_ig,
                fallback_if_generic=True,
            )
            if norm_perm and norm_perm != raw_perm:
                post.permalink = norm_perm
            if is_ig:
                target_link = norm_perm or normalize_instagram_url(
                    raw_link,
                    instagram_id=post.instagram_id,
                    media_type=post.media_type,
                    is_instagram=True,
                    fallback_if_generic=True,
                )
                if target_link and target_link != raw_link:
                    post.link_url = target_link
                if (post.link_url or post.permalink) and not (post.link_label or "").strip():
                    post.link_label = "Ver en Instagram"
            elif raw_link and "instagram.com" in raw_link.lower():
                norm_link = normalize_instagram_url(raw_link, instagram_id=post.instagram_id, media_type=post.media_type)
                if norm_link and norm_link != raw_link:
                    post.link_url = norm_link

        if is_ig and post._stored_media_url and "\n" in post._stored_media_url:
            primary, thumb = [part.strip() for part in post._stored_media_url.split("\n", 1)]
            if primary and thumb and "fbcdn.net" in thumb.lower() and "fbcdn.net" not in primary.lower():
                post._stored_media_url = primary

        if (
            is_ig
            and post.instagram_id == "insta_recepcionista_2026"
            and post._stored_media_url == "https://upa.edu.py/static/images/recepcionista_post.png"
        ):
            post._stored_media_url = (
                "https://data-image.sociablekit.com/sources/instagram-feed/upalemana/DerQoIzjtYf-thumbnail.webp"
            )

    for log_entry in db.query(AdminAuditLog).all():
        if not isinstance(log_entry.details, dict):
            continue
        serialized = json.dumps(log_entry.details, ensure_ascii=False)
        if "/uploads/" in serialized:
            replaced = _SEED_ANY_UPLOAD_RE.sub("/uploads/", serialized)
            if replaced != serialized:
                log_entry.details = json.loads(replaced)


def seed_database():
    """Carga inicial idempotente con datos reales del campus UPA."""
    run_alembic_migrations(engine)

    db: Session = SessionLocal()
    try:
        admin = db.query(User).filter(User.email == "pascal.thommen@upa.edu.py").first()
        if not admin:
            admin = User(
                email="pascal.thommen@upa.edu.py",
                full_name="Pascal Thommen",
                role="admin",
                groups=["Semester_4"],
            )
            db.add(admin)
            db.commit()
            db.refresh(admin)
            print(f"[Seed] Administrador inicial creado: {admin.email}")

        # Limpiar pseudo-grupos redundantes (ALL, TIE aislado) en usuarios existentes
        for existing_user in db.query(User).all():
            cleaned_groups = sanitize_user_groups(existing_user.groups)
            if list(existing_user.groups or []) != cleaned_groups:
                existing_user.groups = cleaned_groups

        # Eliminar posibles grupos de audiencia ficticios ALL o TIE aislado
        for existing_group in db.query(AudienceGroup).all():
            if (
                (existing_group.id or "").strip().upper() in REDUNDANT_GROUP_TAGS
                or (existing_group.name or "").strip().upper() in REDUNDANT_GROUP_TAGS
            ):
                db.delete(existing_group)

        insta_post = db.query(Post).filter(Post.title == "Búsqueda Laboral: Recepcionista").first()
        if not insta_post:
            created_ts = datetime.now(UTC) - timedelta(days=1)
            insta_post = Post(
                title="Búsqueda Laboral: Recepcionista",
                caption="¡Estamos buscando Recepcionista! Si sos una persona proactiva y con vocación de atención, ¡queremos conocerte!\n\nEnviá tu CV a rrhh@upa.edu.py\nReferencia: Recepción\n\n¡Sumate al equipo de la UPA! 🇵🇾🇩🇪",
                content="Principales funciones:\n• Atención a padres, estudiantes, visitantes y público en general.\n• Recepción y gestión de llamadas y correspondencia.\n• Soporte administrativo y a docentes.\n• Gestión de insumos, proveedores y presupuestos.\n• Brindar información sobre la institución y acompañar el proceso de atención a interesados.\n• Elaborar informes mensuales de las actividades realizadas.\n\nRequisitos:\n• Alemán avanzado (excluyente).\n• Inglés avanzado (deseable).\n• Excelente comunicación y trato interpersonal.\n• Manejo de herramientas informáticas.\n\nEdad mínima: 25 años. San Lorenzo | Tiempo completo. Remitir CV a rrhh@upa.edu.py.",
                post_type="INSTAGRAM",
                is_news=True,
                is_event=False,
                is_pinned=False,
                is_edited=False,
                target_groups=["ALL"],
                instagram_id="insta_recepcionista_2026",
                media_type="IMAGE",
                media_url="https://data-image.sociablekit.com/sources/instagram-feed/upalemana/DerQoIzjtYf-thumbnail.webp",
                permalink="https://www.instagram.com/p/DerQoIzjtYf/",
                link_url="https://www.instagram.com/p/DerQoIzjtYf/",
                link_label="Ver en Instagram",
                author_id=admin.id,
                created_at=created_ts,
                published_at=created_ts,
            )
            db.add(insta_post)
            print("[Seed] Publicacion de Instagram registrada: Búsqueda Laboral: Recepcionista")

        event_post = (
            db.query(Post).filter(Post.title == "¿Qué significa seguir siendo humanos en la era de la IA?").first()
        )
        if not event_post:
            tomorrow = datetime.now(UTC) + timedelta(days=1)
            event_start = tomorrow.replace(hour=11, minute=0, second=0, microsecond=0)
            event_end = tomorrow.replace(hour=12, minute=0, second=0, microsecond=0)
            now_ts = datetime.now(UTC)

            event_post = Post(
                title="¿Qué significa seguir siendo humanos en la era de la IA?",
                caption="holaa 👋 mañana tenemos charla de 11 a 12, vayan pues",
                content="Inteligencia artificial, decisiones, libertad y responsabilidad.\n\nDisertante: Daniel Romero (Doctor en Ciencias de la Computación y Máster en Ingeniería de Software, Universidad Politécnica de Valencia).\nMás de 20 años de experiencia profesional en informática aplicada, combinando academia, empresa y proyectos de desarrollo.\n\nFecha y Hora: Miércoles 11:00 HS a 12:00 HS.\nLugar: Auditorio Edificio 1 - Piso 1.",
                post_type="MANUAL",
                is_news=True,
                is_event=True,
                is_pinned=True,
                is_edited=True,
                event_start=event_start,
                event_end=event_end,
                location="Auditorio Edificio 1, Piso 1",
                target_groups=["ALL", "Informatica"],
                event_notify_groups=["Informatica"],
                has_registration=True,
                send_push_notification=True,
                reminders=[30],
                author_id=admin.id,
                created_at=now_ts,
                published_at=now_ts,
            )
            db.add(event_post)
            print("[Seed] Evento hibrido registrado: Charla IA Daniel Romero")
        else:
            if isinstance(event_post.target_groups, list) and "TIE" in event_post.target_groups:
                event_post.target_groups = [g for g in event_post.target_groups if g != "TIE"]
            if isinstance(event_post.event_notify_groups, list):
                event_post.event_notify_groups = sanitize_user_groups(event_post.event_notify_groups)

        default_groups = [
            {
                "id": "estudiantes",
                "name": "Estudiantes",
                "description": "Comunidad estudiantil activa de grado y posgrado.",
                "google_groups": ["estudiantes@upa.edu.py", "tie2025@upa.edu.py"],
                "emails": [],
            },
            {
                "id": "docentes",
                "name": "Docentes",
                "description": "Claustro docente y profesores de cátedra.",
                "google_groups": ["docentes@upa.edu.py"],
                "emails": [],
            },
            {
                "id": "staff",
                "name": "Staff",
                "description": "Personal administrativo, admisiones y soporte operativo.",
                "google_groups": ["staff@upa.edu.py"],
                "emails": ["rectorado@upa.edu.py"],
            },
            {
                "id": "egresados",
                "name": "Egresados",
                "description": "Red de graduados y exalumnos universitarios.",
                "google_groups": ["egresados@upa.edu.py"],
                "emails": [],
            },
        ]
        existing_groups = db.query(AudienceGroup).all()
        if not existing_groups:
            for grp_data in default_groups:
                db.add(AudienceGroup(**grp_data))
                print(f"[Seed] Grupo institucional creado: {grp_data['id']}")
        else:
            default_by_id = {g["id"]: g for g in default_groups}
            for existing_grp in existing_groups:
                grp_defaults = default_by_id.get(existing_grp.id)
                if grp_defaults and not existing_grp.google_groups and grp_defaults.get("google_groups"):
                    existing_grp.google_groups = list(grp_defaults["google_groups"])

        primary_admin_role = db.query(UserRole).filter(UserRole.email == "pascal.thommen@upa.edu.py").first()
        if not primary_admin_role:
            primary_admin_role = UserRole(
                email="pascal.thommen@upa.edu.py",
                name="Pascal Thommen",
                permissions=["publicaciones", "grupos", "roles", "apis", "ia", "historial"],
                is_primary=True,
            )
            db.add(primary_admin_role)
            print("[Seed] Rol inicial creado: pascal.thommen@upa.edu.py")
        elif primary_admin_role.is_primary and primary_admin_role.permissions in (
            ["publicaciones", "grupos", "roles", "apis"],
            ["publicaciones", "grupos", "roles", "apis", "historial"],
        ):
            primary_admin_role.permissions = ["publicaciones", "grupos", "roles", "apis", "ia", "historial"]

        for existing_role in db.query(UserRole).all():
            raw_perms = existing_role.permissions if isinstance(existing_role.permissions, list) else []
            if (
                "ia" not in raw_perms
                and "roles" in raw_perms
                and ("apis" in raw_perms or existing_role.is_primary)
            ):
                updated_perms = list(raw_perms)
                if "historial" in updated_perms:
                    hist_idx = updated_perms.index("historial")
                    updated_perms.insert(hist_idx, "ia")
                else:
                    updated_perms.append("ia")
                existing_role.permissions = updated_perms

        _normalize_stored_upload_urls(db)
        db.commit()
        print("[Seed] Carga inicial finalizada correctamente.")
    finally:
        db.close()


if __name__ == "__main__":
    seed_database()
