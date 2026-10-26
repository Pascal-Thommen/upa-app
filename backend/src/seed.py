from datetime import UTC, datetime, timedelta

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from .database import Base, SessionLocal, engine, ensure_schema_upgrades
from .models import AudienceGroup, Post, User, UserRole


def ensure_schema_columns(bind_engine=engine) -> None:
    """Garantiza que las columnas nuevas existan en tablas preexistentes."""
    try:
        ensure_schema_upgrades(bind_engine)
        inspector = inspect(bind_engine)
        if "users" in inspector.get_table_names():
            existing_cols = {col["name"] for col in inspector.get_columns("users")}
            with bind_engine.begin() as conn:
                if "classroom_refresh_token" not in existing_cols:
                    conn.execute(text("ALTER TABLE users ADD COLUMN classroom_refresh_token TEXT"))
                if "device_token" not in existing_cols:
                    conn.execute(text("ALTER TABLE users ADD COLUMN device_token VARCHAR(512)"))
    except Exception as exc:
        print(f"[Schema Sync Notice] {exc}")


def seed_database():
    """Carga inicial idempotente con datos reales del campus UPA."""
    Base.metadata.create_all(bind=engine)
    ensure_schema_columns(engine)

    db: Session = SessionLocal()
    try:
        admin = db.query(User).filter(User.email == "pascal.thommen@upa.edu.py").first()
        if not admin:
            admin = User(
                email="pascal.thommen@upa.edu.py",
                full_name="Pascal Thommen",
                role="admin",
                groups=["TIE", "Semester_4", "ALL"],
            )
            db.add(admin)
            db.commit()
            db.refresh(admin)
            print(f"[Seed] Administrador inicial creado: {admin.email}")

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
                target_groups=["ALL", "TIE", "Informatica"],
                event_notify_groups=["ALL", "TIE", "Informatica"],
                has_registration=True,
                send_push_notification=True,
                reminder_minutes_before=30,
                reminders=[30],
                author_id=admin.id,
                created_at=now_ts,
                published_at=now_ts,
            )
            db.add(event_post)
            print("[Seed] Evento hibrido registrado: Charla IA Daniel Romero")

        default_groups = [
            {
                "id": "estudiantes",
                "name": "Estudiantes",
                "description": "Comunidad estudiantil activa de grado y posgrado.",
                "badge_class": "bg-blue-100 text-blue-800 border-blue-200",
                "google_group": "estudiantes@upa.edu.py",
                "google_groups": ["estudiantes@upa.edu.py", "tie2025@upa.edu.py"],
                "emails": [],
                "is_system": True,
            },
            {
                "id": "docentes",
                "name": "Docentes",
                "description": "Claustro docente y profesores de cátedra.",
                "badge_class": "bg-emerald-100 text-emerald-800 border-emerald-200",
                "google_group": "docentes@upa.edu.py",
                "google_groups": ["docentes@upa.edu.py"],
                "emails": [],
                "is_system": True,
            },
            {
                "id": "staff",
                "name": "Staff",
                "description": "Personal administrativo, admisiones y soporte operativo.",
                "badge_class": "bg-amber-100 text-amber-800 border-amber-200",
                "google_group": "staff@upa.edu.py",
                "google_groups": ["staff@upa.edu.py"],
                "emails": ["rectorado@upa.edu.py"],
                "is_system": True,
            },
            {
                "id": "egresados",
                "name": "Egresados",
                "description": "Red de graduados y exalumnos universitarios.",
                "badge_class": "bg-purple-100 text-purple-800 border-purple-200",
                "google_group": "egresados@upa.edu.py",
                "google_groups": ["egresados@upa.edu.py"],
                "emails": [],
                "is_system": True,
            },
        ]
        for grp_data in default_groups:
            existing_grp = db.query(AudienceGroup).filter(AudienceGroup.id == grp_data["id"]).first()
            if not existing_grp:
                db.add(AudienceGroup(**grp_data))
                print(f"[Seed] Grupo institucional creado: {grp_data['id']}")
            elif not existing_grp.google_groups and grp_data.get("google_groups"):
                existing_grp.google_groups = list(grp_data["google_groups"])

        primary_admin_role = db.query(UserRole).filter(UserRole.email == "pascal.thommen@upa.edu.py").first()
        if not primary_admin_role:
            primary_admin_role = UserRole(
                email="pascal.thommen@upa.edu.py",
                name="Pascal Thommen",
                role="admin",
                permissions=["publicaciones", "grupos", "roles", "apis"],
                is_primary=True,
            )
            db.add(primary_admin_role)
            print("[Seed] Rol inicial creado: pascal.thommen@upa.edu.py")

        db.commit()
        print("[Seed] Carga inicial finalizada correctamente.")
    finally:
        db.close()


if __name__ == "__main__":
    seed_database()
