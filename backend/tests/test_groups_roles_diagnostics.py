"""Pruebas de persistencia real de Grupos, Matriz de Roles y Diagnóstico de APIs."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from src.auth import create_access_token
from src.database import Base, get_db
from src.main import app
from src.models import AdminAuditLog, AudienceGroup, User, UserRole

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
GROUPS_MGR_ID = 4
GROUPS_MGR_EMAIL = "coordinacion.grupos@upa.edu.py"
STUDENT_ID = 3
STUDENT_EMAIL = "estudiante.test@upa.edu.py"


@pytest.fixture(autouse=True)
def setup_database():
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    db.query(AdminAuditLog).delete()
    db.query(AudienceGroup).delete()
    db.query(UserRole).delete()
    db.query(User).delete()

    db.add_all(
        [
            User(id=ADMIN_ID, email=ADMIN_EMAIL, full_name="Pascal Thommen", role="admin"),
            User(id=EDITOR_ID, email=EDITOR_EMAIL, full_name="Editor Prensa", role="editor"),
            User(id=GROUPS_MGR_ID, email=GROUPS_MGR_EMAIL, full_name="Coordinación Grupos", role="editor"),
            User(
                id=STUDENT_ID,
                email=STUDENT_EMAIL,
                full_name="Estudiante Test",
                role="user",
                groups=["ALL", "TIE"],
                google_groups=[{"id": "g-tie", "name": "Estudiantes TIE", "email": "estudiantes-tie@upa.edu.py"}],
            ),
            AudienceGroup(
                id="estudiantes",
                name="Estudiantes",
                description="Comunidad estudiantil.",
                badge_class="bg-blue-100 text-blue-800",
                google_group="estudiantes@upa.edu.py",
                google_groups=["estudiantes@upa.edu.py"],
                emails=["estudiantes@upa.edu.py"],
                is_system=True,
            ),
            AudienceGroup(
                id="robotica",
                name="Club de Robótica",
                description="Estudiantes y docentes de robótica.",
                badge_class="bg-cyan-100 text-cyan-800",
                google_group="robotica@upa.edu.py",
                google_groups=["robotica@upa.edu.py"],
                emails=["robotica@upa.edu.py"],
                is_system=False,
            ),
            UserRole(
                id=1,
                email=ADMIN_EMAIL,
                name="Pascal Thommen",
                role="admin",
                permissions=["publicaciones", "grupos", "roles", "apis"],
                is_primary=True,
            ),
            UserRole(
                id=2,
                email=EDITOR_EMAIL,
                name="Editor Prensa",
                role="editor",
                permissions=["publicaciones"],
                is_primary=False,
            ),
            UserRole(
                id=3,
                email=GROUPS_MGR_EMAIL,
                name="Coordinación Grupos",
                role="editor",
                permissions=["publicaciones", "grupos"],
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


def test_editor_without_groups_permission_cannot_modify_groups():
    payload = {"name": "Intento sin permiso"}
    res = client.post("/api/groups", json=payload, headers=auth(EDITOR_ID, EDITOR_EMAIL, "editor"))
    assert res.status_code == 403


def test_create_and_update_group_with_groups_permission():
    payload = {
        "id": "biomedica",
        "name": "Ingeniería Biomédica",
        "description": "Estudiantes de Biomédica",
        "google_groups": ["biomedica@upa.edu.py", "laboratorio.bio@upa.edu.py"],
        "emails": ["ana.bio@upa.edu.py"],
    }
    headers = auth(GROUPS_MGR_ID, GROUPS_MGR_EMAIL, "editor")
    res = client.post("/api/groups", json=payload, headers=headers)
    assert res.status_code == 201
    created = res.json()
    assert created["id"] == "biomedica"
    assert created["name"] == "Ingeniería Biomédica"
    assert created["google_groups"] == ["biomedica@upa.edu.py", "laboratorio.bio@upa.edu.py"]
    assert created["emails"] == ["ana.bio@upa.edu.py"]
    assert created["is_system"] is False

    upd = client.put(
        "/api/groups/biomedica",
        json={
            "name": "Biomédica UPA",
            "description": "",
            "google_groups": ["biomedica@upa.edu.py"],
            "emails": ["ana.bio@upa.edu.py", "carlos.bio@upa.edu.py"],
        },
        headers=headers,
    )
    assert upd.status_code == 200
    updated = upd.json()
    assert updated["name"] == "Biomédica UPA"
    assert updated["google_groups"] == ["biomedica@upa.edu.py"]
    assert updated["emails"] == ["ana.bio@upa.edu.py", "carlos.bio@upa.edu.py"]


def test_google_workspace_groups_discovery_and_permissions():
    forbidden = client.get(
        "/api/groups/google-workspace",
        headers=auth(STUDENT_ID, STUDENT_EMAIL, "user"),
    )
    assert forbidden.status_code == 403

    res = client.get(
        "/api/groups/google-workspace",
        headers=auth(GROUPS_MGR_ID, GROUPS_MGR_EMAIL, "editor"),
    )
    assert res.status_code == 200
    body = res.json()
    assert body["source"] in ("directory", "known_users")
    emails = [g["email"] for g in body["groups"]]
    assert "estudiantes-tie@upa.edu.py" in emails


def test_create_group_duplicate_rejected():
    payload = {
        "id": "estudiantes",
        "name": "Estudiantes Duplicado",
    }
    res = client.post("/api/groups", json=payload, headers=auth(ADMIN_ID, ADMIN_EMAIL, "admin"))
    assert res.status_code == 400
    assert "ya existe" in res.json()["detail"]


def test_create_group_student_forbidden():
    payload = {"name": "Nuevo Grupo Hack"}
    res = client.post("/api/groups", json=payload, headers=auth(STUDENT_ID, STUDENT_EMAIL, "user"))
    assert res.status_code == 403


def test_delete_system_group_prevented():
    res = client.delete("/api/groups/estudiantes", headers=auth(ADMIN_ID, ADMIN_EMAIL, "admin"))
    assert res.status_code == 400
    assert "institucional del sistema" in res.json()["detail"]


def test_delete_custom_group_success():
    res = client.delete(
        "/api/groups/robotica",
        headers=auth(GROUPS_MGR_ID, GROUPS_MGR_EMAIL, "editor"),
    )
    assert res.status_code == 200
    assert res.json()["id"] == "robotica"

    res_list = client.get("/api/groups")
    ids = [g["id"] for g in res_list.json()]
    assert "robotica" not in ids


def test_delete_nonexistent_group_returns_404():
    res = client.delete("/api/groups/grupo_inexistente", headers=auth(ADMIN_ID, ADMIN_EMAIL, "admin"))
    assert res.status_code == 404


def test_roles_requires_roles_module_permission():
    forbidden = client.get("/api/roles", headers=auth(EDITOR_ID, EDITOR_EMAIL, "editor"))
    assert forbidden.status_code == 403

    ok = client.get("/api/roles", headers=auth(ADMIN_ID, ADMIN_EMAIL, "admin"))
    assert ok.status_code == 200
    emails = [r["email"] for r in ok.json()]
    assert ADMIN_EMAIL in emails
    assert EDITOR_EMAIL in emails


def test_assign_role_new_account_normalizes_permissions():
    payload = {
        "email": "nuevo.admin@upa.edu.py",
        "name": "Nuevo Administrador",
        "permissions": ["Publicaciones y Eventos", "Gestión de Roles"],
    }
    res = client.post("/api/roles", json=payload, headers=auth(ADMIN_ID, ADMIN_EMAIL, "admin"))
    assert res.status_code == 200
    data = res.json()
    assert data["email"] == "nuevo.admin@upa.edu.py"
    assert data["role"] == "admin"
    assert data["permissions"] == ["publicaciones", "roles"]


def test_assign_role_forbidden_domain_rejected():
    payload = {
        "email": "atacante@gmail.com",
        "name": "Atacante Externo",
        "permissions": ["publicaciones"],
    }
    res = client.post("/api/roles", json=payload, headers=auth(ADMIN_ID, ADMIN_EMAIL, "admin"))
    assert res.status_code == 400
    assert "@upa.edu.py" in res.json()["detail"]


def test_primary_admin_can_toggle_own_non_roles_permissions_and_sync_me():
    headers = auth(ADMIN_ID, ADMIN_EMAIL, "admin")
    upd = client.put(
        f"/api/roles/{ADMIN_EMAIL}",
        json={"permissions": ["publicaciones", "roles"]},
        headers=headers,
    )
    assert upd.status_code == 200
    assert upd.json()["permissions"] == ["publicaciones", "roles"]

    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["permissions"] == ["publicaciones", "roles"]


def test_cannot_leave_zero_accounts_with_roles_permission():
    headers = auth(ADMIN_ID, ADMIN_EMAIL, "admin")
    # Intentar quitar "roles" siendo el único gestor de Roles falla con 400
    upd = client.put(
        f"/api/roles/{ADMIN_EMAIL}",
        json={"permissions": ["publicaciones", "grupos"]},
        headers=headers,
    )
    assert upd.status_code == 400
    assert "al menos una cuenta con permiso en Roles" in upd.json()["detail"]

    rev = client.delete(f"/api/roles/{ADMIN_EMAIL}", headers=headers)
    assert rev.status_code == 400
    assert "al menos una cuenta con permiso en Roles" in rev.json()["detail"]

    # Al autorizar un segundo gestor de Roles sí se permite quitar "roles" del primero
    second = client.post(
        "/api/roles",
        json={"email": "respaldo.roles@upa.edu.py", "permissions": ["roles", "publicaciones"]},
        headers=headers,
    )
    assert second.status_code == 200

    upd_ok = client.put(
        f"/api/roles/{ADMIN_EMAIL}",
        json={"permissions": ["publicaciones"]},
        headers=headers,
    )
    assert upd_ok.status_code == 200
    assert upd_ok.json()["permissions"] == ["publicaciones"]
    assert upd_ok.json()["role"] == "editor"


def test_revoke_normal_role_success():
    res = client.delete(f"/api/roles/{EDITOR_EMAIL}", headers=auth(ADMIN_ID, ADMIN_EMAIL, "admin"))
    assert res.status_code == 200
    assert EDITOR_EMAIL in res.json()["message"]


def test_assign_role_new_account_defaults_to_no_permissions():
    res = client.post(
        "/api/roles",
        json={"email": "nuevo.sinpermisos@upa.edu.py", "name": "Nuevo Sin Permisos"},
        headers=auth(ADMIN_ID, ADMIN_EMAIL, "admin"),
    )
    assert res.status_code == 200
    data = res.json()
    assert data["permissions"] == []
    assert data["role"] == "editor"


def test_group_hierarchy_create_children_up_to_three_levels():
    headers = auth(GROUPS_MGR_ID, GROUPS_MGR_EMAIL, "editor")

    child = client.post(
        "/api/groups",
        json={"id": "tie", "name": "Ingeniería Empresarial", "parent_id": "estudiantes"},
        headers=headers,
    )
    assert child.status_code == 201
    assert child.json()["parent_id"] == "estudiantes"

    grandchild = client.post(
        "/api/groups",
        json={"id": "tie2026", "name": "TIE Cohorte 2026", "parent_id": "tie"},
        headers=headers,
    )
    assert grandchild.status_code == 201
    assert grandchild.json()["parent_id"] == "tie"

    too_deep = client.post(
        "/api/groups",
        json={"id": "tie2026a", "name": "TIE Cohorte 2026 A", "parent_id": "tie2026"},
        headers=headers,
    )
    assert too_deep.status_code == 400
    assert "3 niveles" in too_deep.json()["detail"]


def test_group_hierarchy_rejects_self_reference_and_missing_parent():
    headers = auth(GROUPS_MGR_ID, GROUPS_MGR_EMAIL, "editor")

    self_ref = client.post(
        "/api/groups",
        json={"id": "loop", "name": "Grupo Ciclico", "parent_id": "loop"},
        headers=headers,
    )
    # El id "loop" no existe todavia como contenedor, por lo que se rechaza.
    assert self_ref.status_code == 400

    missing = client.post(
        "/api/groups",
        json={"id": "huerfano", "name": "Grupo Huerfano", "parent_id": "no_existe"},
        headers=headers,
    )
    assert missing.status_code == 400
    assert "no existe" in missing.json()["detail"]


def test_group_hierarchy_list_returns_parent_id():
    headers = auth(GROUPS_MGR_ID, GROUPS_MGR_EMAIL, "editor")
    client.post(
        "/api/groups",
        json={"id": "sub_grupo", "name": "Subgrupo de Prueba", "parent_id": "estudiantes"},
        headers=headers,
    )
    res = client.get("/api/groups")
    assert res.status_code == 200
    by_id = {g["id"]: g for g in res.json()}
    assert by_id["sub_grupo"]["parent_id"] == "estudiantes"
    assert by_id["estudiantes"]["parent_id"] is None


def test_system_diagnostics_live():
    res = client.get("/api/system/diagnostics")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ("healthy", "degraded")
    assert "database" in data
    assert "directory_sync" in data
    assert "classroom_api" in data
    assert "application" in data
    assert "instagram_configured" in data["application"]
    assert "fcm_configured" in data["application"]
    assert data["database"]["total_users"] >= 4
    assert data["database"]["total_groups"] >= 2
    assert data["application"]["zero_mock_certified"] is True
