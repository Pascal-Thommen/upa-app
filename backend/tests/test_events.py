"""Pruebas del ciclo de vida de inscripcion y cancelacion RSVP a eventos con privacidad de conteo."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from src.auth import create_access_token
from src.database import Base, get_db
from src.main import app
from src.models import EventRegistration, Post, User

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_events_database():
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    admin = User(id=1, email="admin@upa.edu.py", full_name="Admin UPA", role="admin", groups=["ALL"])
    student1 = User(id=11, email="ana.gomez@upa.edu.py", full_name="Ana Gomez", role="user", groups=["ALL", "TIE"])
    student2 = User(id=12, email="luis.benitez@upa.edu.py", full_name="Luis Benitez", role="user", groups=["ALL", "TIE"])
    outsider = User(id=13, email="externo@upa.edu.py", full_name="Alumno MECA", role="user", groups=["MECA"])
    db.add_all([admin, student1, student2, outsider])
    db.commit()

    now = datetime.now(UTC)
    event = Post(
        id=101,
        title="Foro de Innovación Empresarial",
        caption="Auditorio principal, inscripción previa.",
        content="Debate abierto para estudiantes de TIE.",
        post_type="MANUAL",
        is_news=True,
        is_event=True,
        is_pinned=True,
        event_start=now + timedelta(days=2),
        event_end=now + timedelta(days=2, hours=2),
        location="Auditorio Edificio 1",
        has_registration=True,
        target_groups=["TIE"],
        author_id=admin.id,
    )
    news_only = Post(
        id=102,
        title="Comunicado General",
        content="No es un evento.",
        post_type="MANUAL",
        is_news=True,
        is_event=False,
        target_groups=["ALL"],
        author_id=admin.id,
    )
    expired_event = Post(
        id=103,
        title="Evento Expirado",
        content="Ya venció su publicación.",
        post_type="MANUAL",
        is_news=True,
        is_event=True,
        event_start=now - timedelta(days=3),
        expires_at=now - timedelta(hours=2),
        has_registration=True,
        target_groups=["ALL"],
        author_id=admin.id,
    )
    db.add_all([event, news_only, expired_event])
    db.commit()
    db.close()

    yield

    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.pop(get_db, None)


def _headers(user_id: int, email: str, role: str = "user") -> dict[str, str]:
    token = create_access_token({"sub": str(user_id), "email": email, "role": role})
    return {"Authorization": f"Bearer {token}"}


def test_event_registration_and_unregistration_lifecycle_and_idempotency():
    h_s1 = _headers(11, "ana.gomez@upa.edu.py")
    h_s2 = _headers(12, "luis.benitez@upa.edu.py")
    h_admin = _headers(1, "admin@upa.edu.py", role="admin")

    # 1. Opt-out directo (No asistiré) sin inscripción previa crea fila declined de forma idempotente
    direct_optout = client.delete("/api/events/101/register", headers=h_s1)
    assert direct_optout.status_code == 200
    assert direct_optout.json()["is_registered"] is False
    assert direct_optout.json()["registration_status"] == "declined"
    assert direct_optout.json()["registered_count"] == 0

    direct_optout_dup = client.delete("/api/events/101/register", headers=h_s1)
    assert direct_optout_dup.status_code == 200
    assert direct_optout_dup.json()["is_registered"] is False
    assert direct_optout_dup.json()["registration_status"] == "declined"

    admin_initial = client.get("/api/publications/101/registrations", headers=h_admin).json()
    assert admin_initial["attending_count"] == 0
    assert admin_initial["declined_count"] == 1

    # 2. Estudiante 1 cambia de opinión y se inscribe (attending)
    reg1 = client.post("/api/events/101/register", headers=h_s1)
    assert reg1.status_code == 200
    body1 = reg1.json()
    assert body1["id"] == 101
    assert body1["is_registered"] is True
    assert body1["registration_status"] == "attending"
    assert body1["registered_count"] == 0

    # 3. Repetir POST /register es idempotente y mantiene una sola fila en BD
    reg1_again = client.post("/api/events/101/register", headers=h_s1)
    assert reg1_again.status_code == 200
    assert reg1_again.json()["is_registered"] is True
    assert reg1_again.json()["registration_status"] == "attending"
    assert reg1_again.json()["registered_count"] == 0

    db = TestingSessionLocal()
    assert db.query(EventRegistration).filter_by(post_id=101, user_id=11).count() == 1
    db.close()

    # 4. Estudiante 2 también se inscribe; ninguno de los estudiantes puede inferir el total de inscritos
    reg2 = client.post("/api/events/101/register", headers=h_s2)
    assert reg2.status_code == 200
    assert reg2.json()["is_registered"] is True
    assert reg2.json()["registration_status"] == "attending"
    assert reg2.json()["registered_count"] == 0

    # 5. En Feed y Agenda para estudiantes, registered_count está neutralizado a 0
    feed_s1 = client.get("/api/v1/feed", headers=h_s1).json()
    ev_in_feed = next(p for p in feed_s1["posts"] if p["id"] == 101)
    assert ev_in_feed["is_registered"] is True
    assert ev_in_feed["registration_status"] == "attending"
    assert ev_in_feed["registered_count"] == 0

    agenda_s1 = client.get("/api/v1/agenda", headers=h_s1).json()
    ev_in_agenda = next(e for e in agenda_s1["events"] if e["id"] == 101)
    item_in_agenda = next(i for i in agenda_s1["items"] if i["id"] == "101")
    assert ev_in_agenda["is_registered"] is True
    assert ev_in_agenda["registration_status"] == "attending"
    assert ev_in_agenda["registered_count"] == 0
    assert item_in_agenda["is_registered"] is True
    assert item_in_agenda["registration_status"] == "attending"
    assert item_in_agenda["registered_count"] == 0

    # 6. El panel administrativo conserva las métricas reales (2 attending, 0 declined)
    admin_regs = client.get("/api/publications/101/registrations", headers=h_admin).json()
    assert admin_regs["attending_count"] == 2
    assert admin_regs["declined_count"] == 0

    # 7. Estudiante 1 cancela su inscripción -> pasa a estado declined
    unreg1 = client.delete("/api/events/101/register", headers=h_s1)
    assert unreg1.status_code == 200
    assert unreg1.json()["is_registered"] is False
    assert unreg1.json()["registration_status"] == "declined"
    assert unreg1.json()["registered_count"] == 0

    # 8. Segundo intento de cancelación cuando ya está declined es idempotente (HTTP 200)
    unreg1_dup = client.delete("/api/events/101/register", headers=h_s1)
    assert unreg1_dup.status_code == 200
    assert unreg1_dup.json()["is_registered"] is False
    assert unreg1_dup.json()["registration_status"] == "declined"

    admin_regs_after = client.get("/api/publications/101/registrations", headers=h_admin).json()
    assert admin_regs_after["attending_count"] == 1
    assert admin_regs_after["declined_count"] == 1

    # 9. Re-inscripción tras cancelación reactiva la misma fila a attending
    rereg1 = client.post("/api/events/101/register", headers=h_s1)
    assert rereg1.status_code == 200
    assert rereg1.json()["is_registered"] is True
    assert rereg1.json()["registration_status"] == "attending"
    assert rereg1.json()["registered_count"] == 0

    db = TestingSessionLocal()
    rows = db.query(EventRegistration).filter_by(post_id=101, user_id=11).all()
    assert len(rows) == 1
    assert rows[0].status == "attending"
    db.close()


def test_event_registration_security_and_error_cases():
    h_s1 = _headers(11, "ana.gomez@upa.edu.py")
    h_outsider = _headers(13, "externo@upa.edu.py")

    # Sin autenticación -> 401
    assert client.post("/api/events/101/register").status_code == 401
    assert client.delete("/api/events/101/register").status_code == 401

    # Usuario fuera del grupo destinatario -> 403
    assert client.post("/api/events/101/register", headers=h_outsider).status_code == 403
    assert client.delete("/api/events/101/register", headers=h_outsider).status_code == 403

    # Publicación que no es evento (is_event=False) -> 404
    assert client.post("/api/events/102/register", headers=h_s1).status_code == 404
    assert client.delete("/api/events/102/register", headers=h_s1).status_code == 404

    # Evento expirado -> 404
    assert client.post("/api/events/103/register", headers=h_s1).status_code == 404
    assert client.delete("/api/events/103/register", headers=h_s1).status_code == 404

    # Evento inexistente -> 404
    assert client.post("/api/events/99999/register", headers=h_s1).status_code == 404
    assert client.delete("/api/events/99999/register", headers=h_s1).status_code == 404
