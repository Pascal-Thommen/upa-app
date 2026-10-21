from datetime import UTC, datetime, timedelta

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from .database import Base, SessionLocal, engine
from .models import Post, User


def ensure_schema_columns(bind_engine=engine) -> None:
    """Garantiza que las columnas nuevas existan en tablas preexistentes."""
    try:
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
    """Idempotentes Seeding mit echten Campus-Daten aus Instagram und internen Vorlesungen."""
    # Tabellen sicherstellen
    Base.metadata.create_all(bind=engine)
    ensure_schema_columns(engine)
    
    db: Session = SessionLocal()
    try:
        # 1. Admin-Nutzer anlegen
        admin = db.query(User).filter(User.email == "pascal.thommen@upa.edu.py").first()
        if not admin:
            admin = User(
                email="pascal.thommen@upa.edu.py",
                full_name="Pascal Thommen",
                role="admin",
                groups=["TIE", "Semester_4", "ALL"]
            )
            db.add(admin)
            db.commit()
            db.refresh(admin)
            print(f"[Seed] Admin-Nutzer angelegt: {admin.email}")

        # 2. Instagram News Post einpflegen
        insta_post = db.query(Post).filter(Post.title == "Búsqueda Laboral: Recepcionista").first()
        if not insta_post:
            insta_post = Post(
                title="Búsqueda Laboral: Recepcionista",
                caption="¡Estamos buscando Recepcionista! Si sos una persona proactiva y con vocación de atención, ¡queremos conocerte!\n\nEnviá tu CV a rrhh@upa.edu.py\nReferencia: Recepción\n\n¡Sumate al equipo de la UPA! 🇵🇾🇩🇪",
                content="Principales funciones:\n• Atención a padres, estudiantes, visitantes y público en general.\n• Recepción y gestión de llamadas y correspondencia.\n• Soporte administrativo y a docentes.\n• Gestión de insumos, proveedores y presupuestos.\n• Brindar información sobre la institución y acompañar el proceso de atención a interesados.\n• Elaborar informes mensuales de las actividades realizadas.\n\nRequisitos:\n• Alemán avanzado (excluyente).\n• Inglés avanzado (deseable).\n• Excelente comunicación y trato interpersonal.\n• Manejo de herramientas informáticas.\n\nEdad mínima: 25 años. San Lorenzo | Tiempo completo. Remitir CV a rrhh@upa.edu.py.",
                post_type="INSTAGRAM",
                is_news=True,
                is_event=False,
                is_pinned=False,
                target_groups=["ALL"],
                instagram_id="insta_recepcionista_2026",
                media_type="IMAGE",
                media_url="https://upa.edu.py/static/images/recepcionista_post.png",
                permalink="https://www.instagram.com/p/DerQoIzjtYf/",
                author_id=admin.id,
                created_at=datetime.now(UTC) - timedelta(days=1)
            )
            db.add(insta_post)
            print("[Seed] Instagram Post eingepflegt: Búsqueda Laboral: Recepcionista")

        # 3. Interner Event (Charla IA) einpflegen
        event_post = db.query(Post).filter(Post.title == "¿Qué significa seguir siendo humanos en la era de la IA?").first()
        if not event_post:
            # Termin morgen um 11:00 Uhr
            tomorrow = datetime.now(UTC) + timedelta(days=1)
            event_start = tomorrow.replace(hour=11, minute=0, second=0, microsecond=0)
            event_end = tomorrow.replace(hour=12, minute=0, second=0, microsecond=0)
            
            event_post = Post(
                title="¿Qué significa seguir siendo humanos en la era de la IA?",
                caption="holaa 👋 mañana tenemos charla de 11 a 12, vayan pues",
                content="Inteligencia artificial, decisiones, libertad y responsabilidad.\n\nDisertante: Daniel Romero (Doctor en Ciencias de la Computación y Máster en Ingeniería de Software, Universidad Politécnica de Valencia).\nMás de 20 años de experiencia profesional en informática aplicada, combinando academia, empresa y proyectos de desarrollo.\n\nFecha y Hora: Miércoles 11:00 HS a 12:00 HS.\nLugar: Auditorio Edificio 1 - Piso 1.",
                post_type="MANUAL",
                is_news=True,
                is_event=True,
                is_pinned=True,  # Oben angepinnt
                event_start=event_start,
                event_end=event_end,
                location="Auditorio Edificio 1, Piso 1",
                target_groups=["ALL", "TIE", "Informatica"],
                has_registration=True,
                send_push_notification=True,
                reminder_minutes_before=30,
                author_id=admin.id,
                created_at=datetime.now(UTC)
            )
            db.add(event_post)
            print("[Seed] Event eingepflegt: Charla IA Daniel Romero")

        db.commit()
        print("[Seed] Seeding erfolgreich beendet.")
    finally:
        db.close()

if __name__ == "__main__":
    seed_database()
