"""Pruebas para persistencia real de Grupos, Roles y Diagnostico Tecnico."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from src.auth import create_access_token
from src.database import Base, get_db
from src.main import app
from src.models import AudienceGroup, User, UserRole

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


def auth(user_id: int, email: str, role: str) -> dict[str, str]:
    token = create_access_token({"sub": str(user_id), "email": email, "role": role})
    return {"Authorization": f"Bearer {token}"}


ADMIN_ID = 1
ADMIN_EMAIL = "pascal.thommen@upa.edu.py"
EDITOR_ID = 2
EDITOR_EMAIL = "editor.prensa@upa.edu.py"
STUDENT_ID = 3
STUDENT_EMAIL = "estudiante.test@upa.edu.py"


@pytest.fixture(autouse=True)
def setup_database():
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    db.query(AudienceGroup).delete()
    db.query(UserRole).delete()
    db.query(User).delete()

    db.add_all(
        [
            User(id=ADMIN_ID, email=ADMIN_EMAIL, full_name="Pascal Thommen", role="admin"),
            User(id=EDITOR_ID, email=EDITOR_EMAIL, full_name="Editor Prensa", role="editor"),
            User(id=STUDENT_ID, email=STUDENT_EMAIL, full_name="Estudiante Test", role="user"),
            AudienceGroup(
                id="estudiantes",
                name="Estudiantes",
                description="Comunidad estudiantil.",
                badge_class="bg-blue-100 text-blue-800",
                google_group="Estudiantes Activos",
                emails=["estudiantes@upa.edu.py"],
                is_system=True,
            ),
            AudienceGroup(
                id="robotica",
                name="Club de Robótica",
                description="Estudiantes y docentes de robótica.",
                badge_class="bg-cyan-100 text-cyan-800",
                google_group="Club Robotica UPA",
                emails=["robotica@upa.edu.py"],
                is_system=False,
            ),
            UserRole(
                id=1,
                email=ADMIN_EMAIL,
                name="Pascal Thommen",
                role="admin",
                permissions=[
                    "Publicaciones y Eventos",
                    "Grupos y Audiencias",
                    "Gestión de Roles",
                    "Diagnóstico de APIs",
                ],
                is_primary=True,
            ),
            UserRole(
                id=2,
                email=EDITOR_EMAIL,
                name="Editor Prensa",
                role="editor",
                permissions=["Publicaciones y Eventos"],
                is_primary=False,
            ),
        ]
    )
    db.commit()
    db.close()
    yield
    app.dependency_overrides.clear()


def test_list_groups():
    res = client.get("/api/groups")
    assert res.status_code == 200
    data = res.json()
    assert len(data) >= 2
    ids = [g["id"] for g in data]
    assert "estudiantes" in ids
    assert "robotica" in ids


def test_create_group_as_editor():
    payload = {
        "id": "biomedica",
        "name": "Ingeniería Biomédica",
        "description": "Estudiantes de Biomédica",
        "badge_class": "bg-purple-100 text-purple-800",
        "google_group": "Biomedica 2026",
        "emails": ["biomedica@upa.edu.py"],
    }
    res = client.post("/api/groups", json=payload, headers=auth(EDITOR_ID, EDITOR_EMAIL, "editor"))
    assert res.status_code == 201
    created = res.json()
    assert created["id"] == "biomedica"
    assert created["name"] == "Ingeniería Biomédica"
    assert created["is_system"] is False


def test_update_group_success():
    payload = {
        "name": "Club de Robótica Avanzada",
        "description": "Estudiantes, docentes e investigadores de robótica.",
        "google_group": "robotica-avanzada@upa.edu.py",
        "emails": ["robotica@upa.edu.py", "investigacion@upa.edu.py"],
    }
    res = client.put("/api/groups/robotica", json=payload, headers=auth(EDITOR_ID, EDITOR_EMAIL, "editor"))
    assert res.status_code == 200
    updated = res.json()
    assert updated["id"] == "robotica"
    assert updated["name"] == "Club de Robótica Avanzada"
    assert updated["description"] == "Estudiantes, docentes e investigadores de robótica."
    assert "investigacion@upa.edu.py" in updated["emails"]


def test_update_group_not_found():
    payload = {"name": "No existe"}
    res = client.put("/api/groups/inexistente", json=payload, headers=auth(EDITOR_ID, EDITOR_EMAIL, "editor"))
    assert res.status_code == 404


def test_create_group_duplicate_rejected():
    payload = {
        "id": "estudiantes",
        "name": "Estudiantes Duplicado",
    }
    res = client.post("/api/groups", json=payload, headers=auth(ADMIN_ID, ADMIN_EMAIL, "admin"))
    assert res.status_code == 400
    assert "ya existe" in res.json()["detail"]


def test_create_group_student_forbidden():
    payload = {
        "name": "Nuevo Grupo Hack",
    }
    res = client.post("/api/groups", json=payload, headers=auth(STUDENT_ID, STUDENT_EMAIL, "user"))
    assert res.status_code == 403


def test_delete_system_group_prevented():
    res = client.delete("/api/groups/estudiantes", headers=auth(ADMIN_ID, ADMIN_EMAIL, "admin"))
    assert res.status_code == 400
    assert "institucional del sistema" in res.json()["detail"]


def test_delete_custom_group_success():
    res = client.delete("/api/groups/robotica", headers=auth(EDITOR_ID, EDITOR_EMAIL, "editor"))
    assert res.status_code == 200
    assert res.json()["id"] == "robotica"

    # Verificar que ya no exista
    res_list = client.get("/api/groups")
    ids = [g["id"] for g in res_list.json()]
    assert "robotica" not in ids


def test_delete_nonexistent_group_returns_404():
    res = client.delete("/api/groups/grupo_inexistente", headers=auth(ADMIN_ID, ADMIN_EMAIL, "admin"))
    assert res.status_code == 404


def test_list_roles_as_editor():
    res = client.get("/api/roles", headers=auth(EDITOR_ID, EDITOR_EMAIL, "editor"))
    assert res.status_code == 200
    roles = res.json()
    assert len(roles) == 2
    emails = [r["email"] for r in roles]
    assert ADMIN_EMAIL in emails
    assert EDITOR_EMAIL in emails


def test_assign_role_new_admin():
    payload = {
        "email": "nuevo.admin@upa.edu.py",
        "name": "Nuevo Administrador",
        "role": "admin",
        "permissions": ["Publicaciones y Eventos", "Gestión de Roles"],
    }
    res = client.post("/api/roles", json=payload, headers=auth(ADMIN_ID, ADMIN_EMAIL, "admin"))
    assert res.status_code == 200
    data = res.json()
    assert data["email"] == "nuevo.admin@upa.edu.py"
    assert data["role"] == "admin"
    assert data["is_primary"] is False


def test_assign_role_forbidden_domain_rejected():
    payload = {
        "email": "atacante@gmail.com",
        "name": "Atacante Externo",
        "role": "admin",
    }
    res = client.post("/api/roles", json=payload, headers=auth(ADMIN_ID, ADMIN_EMAIL, "admin"))
    assert res.status_code == 400
    assert "@upa.edu.py" in res.json()["detail"]


def test_demote_primary_admin_rejected():
    payload = {
        "email": ADMIN_EMAIL,
        "name": "Pascal Thommen",
        "role": "editor",
    }
    res = client.post("/api/roles", json=payload, headers=auth(ADMIN_ID, ADMIN_EMAIL, "admin"))
    assert res.status_code == 400
    assert "administrador principal no puede ser degradado" in res.json()["detail"]

    # Probar tambien via PUT
    res_put = client.put(f"/api/roles/{ADMIN_EMAIL}", json={"role": "editor"}, headers=auth(ADMIN_ID, ADMIN_EMAIL, "admin"))
    assert res_put.status_code == 400
    assert "administrador principal no puede ser degradado" in res_put.json()["detail"]


def test_update_role_permissions_matrix():
    payload = {
        "permissions": ["Publicaciones y Eventos", "Grupos y Audiencias", "Diagnóstico de APIs"],
    }
    res = client.put(f"/api/roles/{EDITOR_EMAIL}", json=payload, headers=auth(ADMIN_ID, ADMIN_EMAIL, "admin"))
    assert res.status_code == 200
    updated = res.json()
    assert updated["email"] == EDITOR_EMAIL
    assert "Grupos y Audiencias" in updated["permissions"]
    assert "Diagnóstico de APIs" in updated["permissions"]


def test_update_role_invalid_domain_rejected():
    res = client.put("/api/roles/intruso@externo.com", json={"role": "editor"}, headers=auth(ADMIN_ID, ADMIN_EMAIL, "admin"))
    assert res.status_code == 400
    assert "@upa.edu.py" in res.json()["detail"]


def test_update_role_not_found():
    res = client.put("/api/roles/noexiste@upa.edu.py", json={"role": "editor"}, headers=auth(ADMIN_ID, ADMIN_EMAIL, "admin"))
    assert res.status_code == 404


def test_revoke_primary_admin_rejected():
    res = client.delete(f"/api/roles/{ADMIN_EMAIL}", headers=auth(ADMIN_ID, ADMIN_EMAIL, "admin"))
    assert res.status_code == 400
    assert "No se puede revocar el rol del administrador principal" in res.json()["detail"]


def test_revoke_normal_role_success():
    res = client.delete(f"/api/roles/{EDITOR_EMAIL}", headers=auth(ADMIN_ID, ADMIN_EMAIL, "admin"))
    assert res.status_code == 200
    assert EDITOR_EMAIL in res.json()["message"]


def test_system_diagnostics_live():
    res = client.get("/api/system/diagnostics")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ("healthy", "degraded")
    assert "database" in data
    assert "directory_sync" in data
    assert "classroom_api" in data
    assert "application" in data
    assert data["database"]["total_users"] >= 3
    assert data["database"]["total_groups"] >= 2
    assert data["application"]["zero_mock_certified"] is True
