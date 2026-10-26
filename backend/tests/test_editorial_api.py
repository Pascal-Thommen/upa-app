"""Pruebas del backend para el Cockpit de Redaccion: POST /api/events, participantes, categoria y rol editor."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from src.auth import create_access_token
from src.database import Base, ensure_schema_upgrades, get_db
from src.main import app
from src.models import AdminAuditLog, EventRegistration, Post, User

engine = create_engine(
    "sqlite:///:memory:",
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


def auth(user_id: int, role: str) -> dict[str, str]:
    token = create_access_token({"sub": str(user_id), "email": f"u{user_id}@upa.edu.py", "role": role})
    return {"Authorization": f"Bearer {token}"}


ADMIN = 1
EDITOR = 2
STUDENT = 3
STUDENT_B = 4


@pytest.fixture(autouse=True)
def setup_database():
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    db.add_all(
        [
            User(id=ADMIN, email="u1@upa.edu.py", full_name="Admin UPA", role="admin", groups=["ALL"]),
            User(id=EDITOR, email="u2@upa.edu.py", full_name="Redaccion UPA", role="editor", groups=["ALL"]),
            User(id=STUDENT, email="u3@upa.edu.py", full_name="Ana Gomez", role="user", groups=["ALL", "TIE"]),
            User(id=STUDENT_B, email="u4@upa.edu.py", full_name="Luis Benitez", role="user", groups=["ALL", "PI"]),
        ]
    )
    db.commit()
    db.close()
    yield
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.pop(get_db, None)


def _event_payload(**overrides):
    start = datetime.now(UTC) + timedelta(days=3)
    payload = {
        "title": "Charla de Robotica",
        "description": "Demostracion en vivo",
        "location": "Laboratorio 2",
        "event_start": start.isoformat(),
        "event_end": (start + timedelta(hours=2)).isoformat(),
        "has_registration": True,
        "target_groups": ["TIE"],
        "image_url": "https://api.upa.edu.py/uploads/aaa.png",
    }
    payload.update(overrides)
    return payload


def test_create_event_persists_real_row_and_audit_log():
    payload = _event_payload()
    response = client.post("/api/events", json=payload, headers=auth(ADMIN, "admin"))
    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Charla de Robotica"
    assert body["description"] == "Demostracion en vivo"
    assert body["location"] == "Laboratorio 2"
    assert body["has_registration"] is True
    assert body["target_groups"] == ["TIE"]
    assert body["image_url"] == "https://api.upa.edu.py/uploads/aaa.png"
    assert body["registered_count"] == 0
    assert body["is_registered"] is False

    db = TestingSessionLocal()
    post = db.query(Post).filter(Post.id == body["id"]).one()
    assert post.is_event is True
    assert post.is_news is False, "un evento no aparece como noticia por defecto"
    assert post.category == "VERANSTALTUNG"
    assert post.author_id == ADMIN
    assert post.media_url == "https://api.upa.edu.py/uploads/aaa.png"
    audit = db.query(AdminAuditLog).filter(AdminAuditLog.action == "CREATE_EVENT").one()
    assert audit.target_id == post.id
    assert audit.details == {"title": "Charla de Robotica"}
    db.close()

    # Visible en la agenda del grupo destinatario y oculto para otros grupos
    assert any(e["id"] == body["id"] for e in client.get("/api/events", headers=auth(STUDENT, "user")).json())
    assert not any(e["id"] == body["id"] for e in client.get("/api/events", headers=auth(STUDENT_B, "user")).json())


def test_create_event_validation_and_permissions():
    start = datetime.now(UTC) + timedelta(days=1)
    earlier = start - timedelta(hours=1)

    bad_range = client.post(
        "/api/events",
        json=_event_payload(event_start=start.isoformat(), event_end=earlier.isoformat()),
        headers=auth(ADMIN, "admin"),
    )
    assert bad_range.status_code == 400
    assert "finalizacion" in bad_range.json()["detail"]

    blank_title = client.post("/api/events", json=_event_payload(title="   "), headers=auth(ADMIN, "admin"))
    assert blank_title.status_code == 400

    missing_start = client.post("/api/events", json={"title": "Sin fecha"}, headers=auth(ADMIN, "admin"))
    assert missing_start.status_code == 422

    assert client.post("/api/events", json=_event_payload(), headers=auth(STUDENT, "user")).status_code == 403
    assert client.post("/api/events", json=_event_payload()).status_code in (401, 403)

    db = TestingSessionLocal()
    assert db.query(Post).filter(Post.is_event.is_(True)).count() == 0, "los rechazos no persisten nada"
    db.close()


def test_event_registrations_lists_real_participants():
    event = client.post("/api/events", json=_event_payload(target_groups=["ALL"]), headers=auth(ADMIN, "admin")).json()
    eid = event["id"]
    assert client.post(f"/api/events/{eid}/register", headers=auth(STUDENT, "user")).status_code == 200
    assert client.post(f"/api/events/{eid}/register", headers=auth(STUDENT_B, "user")).status_code == 200

    db = TestingSessionLocal()
    declined = db.query(EventRegistration).filter(EventRegistration.user_id == STUDENT_B).one()
    declined.status = "declined"
    db.commit()
    db.close()

    response = client.get(f"/api/events/{eid}/registrations", headers=auth(EDITOR, "editor"))
    assert response.status_code == 200
    data = response.json()
    assert data["event_id"] == eid
    assert data["title"] == "Charla de Robotica"
    assert data["has_registration"] is True
    assert data["attending_count"] == 1, "solo cuentan los inscritos con estado attending"
    assert [(r["user_id"], r["full_name"], r["email"], r["status"]) for r in data["registrations"]] == [
        (STUDENT, "Ana Gomez", "u3@upa.edu.py", "attending"),
        (STUDENT_B, "Luis Benitez", "u4@upa.edu.py", "declined"),
    ]
    for entry in data["registrations"]:
        assert datetime.fromisoformat(entry["registered_at"].replace("Z", "+00:00")).tzinfo is not None


def test_event_registrations_errors():
    event = client.post("/api/events", json=_event_payload(), headers=auth(ADMIN, "admin")).json()
    assert client.get(f"/api/events/{event['id']}/registrations", headers=auth(STUDENT, "user")).status_code == 403
    assert client.get(f"/api/events/{event['id']}/registrations").status_code in (401, 403)
    assert client.get("/api/events/9999/registrations", headers=auth(ADMIN, "admin")).status_code == 404

    news = client.post(
        "/api/news", json={"title": "Solo noticia", "target_groups": ["ALL"]}, headers=auth(ADMIN, "admin")
    ).json()
    not_event = client.get(f"/api/events/{news['id']}/registrations", headers=auth(ADMIN, "admin"))
    assert not_event.status_code == 404, "una noticia que no es evento no expone inscripciones"


def test_event_without_registrations_returns_empty_list():
    event = client.post("/api/events", json=_event_payload(), headers=auth(ADMIN, "admin")).json()
    data = client.get(f"/api/events/{event['id']}/registrations", headers=auth(ADMIN, "admin")).json()
    assert data["attending_count"] == 0
    assert data["registrations"] == []


def test_news_category_is_normalized_validated_and_clearable():
    created = client.post(
        "/api/news",
        json={"title": "Becas", "category": " ankuendigung ", "target_groups": ["ALL"]},
        headers=auth(ADMIN, "admin"),
    )
    assert created.status_code == 201
    assert created.json()["category"] == "ANKUENDIGUNG"

    db = TestingSessionLocal()
    assert db.query(Post).filter(Post.id == created.json()["id"]).one().category == "ANKUENDIGUNG"
    db.close()

    invalid = client.post("/api/news", json={"title": "X", "category": "OTRA"}, headers=auth(ADMIN, "admin"))
    assert invalid.status_code == 400
    assert "Categoria invalida" in invalid.json()["detail"]

    nid = created.json()["id"]
    changed = client.put(f"/api/news/{nid}", json={"category": "MELDUNG"}, headers=auth(ADMIN, "admin"))
    assert changed.status_code == 200 and changed.json()["category"] == "MELDUNG"
    cleared = client.put(f"/api/news/{nid}", json={"category": ""}, headers=auth(ADMIN, "admin"))
    assert cleared.status_code == 200 and cleared.json()["category"] == ""
    assert client.put(f"/api/news/{nid}", json={"category": "OTRA"}, headers=auth(ADMIN, "admin")).status_code == 400

    untouched = client.get(f"/api/news/{nid}", headers=auth(STUDENT, "user")).json()
    assert untouched["title"] == "Becas"
    assert untouched["category"] == ""


def test_news_without_category_returns_empty_string_not_null():
    created = client.post(
        "/api/news", json={"title": "Sin categoria", "target_groups": ["ALL"]}, headers=auth(ADMIN, "admin")
    )
    assert created.status_code == 201
    assert created.json()["category"] == ""


def test_editor_role_manages_content_but_user_role_cannot():
    news = client.post(
        "/api/news",
        json={"title": "Nota", "target_groups": ["PI"], "category": "MELDUNG"},
        headers=auth(EDITOR, "editor"),
    )
    assert news.status_code == 201
    nid = news.json()["id"]

    # El redactor ve contenido de cualquier grupo (igual que el administrador)
    assert client.get(f"/api/news/{nid}", headers=auth(EDITOR, "editor")).status_code == 200
    assert client.get(f"/api/news/{nid}", headers=auth(STUDENT, "user")).status_code == 403

    assert (
        client.put(f"/api/news/{nid}", json={"title": "Nota 2"}, headers=auth(EDITOR, "editor")).json()["title"]
        == "Nota 2"
    )
    assert client.put(f"/api/news/{nid}", json={"title": "Hack"}, headers=auth(STUDENT, "user")).status_code == 403

    event = client.post("/api/events", json=_event_payload(), headers=auth(EDITOR, "editor"))
    assert event.status_code == 201
    eid = event.json()["id"]
    assert (
        client.put(f"/api/events/{eid}", json={"location": "Aula 5"}, headers=auth(EDITOR, "editor")).json()["location"]
        == "Aula 5"
    )
    assert client.delete(f"/api/events/{eid}", headers=auth(STUDENT, "user")).status_code == 403
    assert client.delete(f"/api/events/{eid}", headers=auth(EDITOR, "editor")).json()["status"] == "deleted"
    assert client.delete(f"/api/news/{nid}", headers=auth(EDITOR, "editor")).json()["status"] == "deleted"

    db = TestingSessionLocal()
    actions = {a.action for a in db.query(AdminAuditLog).filter(AdminAuditLog.admin_id == EDITOR).all()}
    assert {"CREATE_EVENT", "UPDATE_EVENT", "DELETE_EVENT", "DELETE_NEWS", "UPDATE_NEWS"} <= actions
    db.close()


def test_ensure_schema_upgrades_adds_category_to_legacy_posts_table_idempotently():
    legacy = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    with legacy.begin() as conn:
        conn.execute(text("CREATE TABLE posts (id INTEGER PRIMARY KEY, title VARCHAR(255) NOT NULL)"))
        conn.execute(text("INSERT INTO posts (id, title) VALUES (1, 'Existente')"))

    assert "category" not in {c["name"] for c in inspect(legacy).get_columns("posts")}
    ensure_schema_upgrades(legacy)
    ensure_schema_upgrades(legacy)  # idempotente
    assert "category" in {c["name"] for c in inspect(legacy).get_columns("posts")}
    with legacy.connect() as conn:
        row = conn.execute(text("SELECT title, category FROM posts WHERE id = 1")).one()
    assert tuple(row) == ("Existente", None), "los datos existentes se conservan"

    empty = create_engine("sqlite:///:memory:", poolclass=StaticPool)
    ensure_schema_upgrades(empty)  # sin tabla posts: no falla
    assert inspect(empty).get_table_names() == []
