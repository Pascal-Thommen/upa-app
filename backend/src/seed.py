from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from .database import SessionLocal, engine, run_alembic_migrations
from .models import AudienceGroup, Post, User, UserRole
from .schemas.user import REDUNDANT_GROUP_TAGS, sanitize_user_groups


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
                media_url="https://upa.edu.py/static/images/recepcionista_post.png",
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
                permissions=["publicaciones", "grupos", "roles", "apis", "historial"],
                is_primary=True,
            )
            db.add(primary_admin_role)
            print("[Seed] Rol inicial creado: pascal.thommen@upa.edu.py")
        elif primary_admin_role.is_primary and primary_admin_role.permissions == [
            "publicaciones",
            "grupos",
            "roles",
            "apis",
        ]:
            primary_admin_role.permissions = ["publicaciones", "grupos", "roles", "apis", "historial"]

        db.commit()
        print("[Seed] Carga inicial finalizada correctamente.")
    finally:
        db.close()


if __name__ == "__main__":
    seed_database()
