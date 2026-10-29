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
                permissions=["publicaciones", "grupos", "roles", "apis", "historial"],
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
    # Sin autenticación -> 401
    unauth = client.get("/api/groups")
    assert unauth.status_code == 401

    # Estudiante regular -> 403
    student_res = client.get("/api/groups", headers=auth(STUDENT_ID, STUDENT_EMAIL, "user"))
    assert student_res.status_code == 403

    # Redactor solo de publicaciones (sin permiso 'grupos') -> 200 pero con emails vacíos (sin filtración)
    editor_res = client.get("/api/groups", headers=auth(EDITOR_ID, EDITOR_EMAIL, "editor"))
    assert editor_res.status_code == 200
    editor_data = editor_res.json()
    assert len(editor_data) >= 2
    assert all(g["emails"] == [] for g in editor_data)

    # Gestor con permiso 'grupos' -> 200 con lista completa de emails
    res = client.get("/api/groups", headers=auth(GROUPS_MGR_ID, GROUPS_MGR_EMAIL, "editor"))
    assert res.status_code == 200
    data = res.json()
    assert len(data) >= 2
    ids = [g["id"] for g in data]
    assert "estudiantes" in ids
    assert "robotica" in ids
    by_id = {g["id"]: g for g in data}
    assert by_id["estudiantes"]["emails"] == ["estudiantes@upa.edu.py"]
    assert by_id["robotica"]["emails"] == ["robotica@upa.edu.py"]
    # Orden alfabético por nombre ("Club de Robótica" antes que "Estudiantes")
    names = [g["name"] for g in data]
    assert names == sorted(names, key=lambda n: n.lower())


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
    names = [g["name"].lower() for g in body["groups"]]
    assert names == sorted(names)


@pytest.mark.anyio
async def test_google_workspace_directory_cache_and_alphabetical_sorting():
    import time

    from src.services import google_groups

    google_groups.clear_workspace_groups_cache()
    google_groups._workspace_groups_cache["upa.edu.py"] = (
        time.monotonic(),
        [
            {"id": "2", "name": "Zootecnia", "email": "zootecnia@upa.edu.py", "description": ""},
            {"id": "1", "name": "Arquitectura", "email": "arquitectura@upa.edu.py", "description": ""},
        ],
    )

    cached = await google_groups.list_workspace_groups()
    assert [g["name"] for g in cached] == ["Arquitectura", "Zootecnia"]
    google_groups.clear_workspace_groups_cache()


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


def test_delete_seeded_group_allowed_and_recreatable():
    res = client.delete("/api/groups/estudiantes", headers=auth(ADMIN_ID, ADMIN_EMAIL, "admin"))
    assert res.status_code == 200
    assert res.json()["id"] == "estudiantes"

    recreate = client.post(
        "/api/groups",
        json={
            "id": "estudiantes",
            "name": "Estudiantes",
            "description": "Comunidad estudiantil.",
            "google_group": "estudiantes@upa.edu.py",
            "google_groups": ["estudiantes@upa.edu.py"],
            "emails": ["estudiantes@upa.edu.py"],
        },
        headers=auth(ADMIN_ID, ADMIN_EMAIL, "admin"),
    )
    assert recreate.status_code == 201


def test_delete_custom_group_success():
    res = client.delete(
        "/api/groups/robotica",
        headers=auth(GROUPS_MGR_ID, GROUPS_MGR_EMAIL, "editor"),
    )
    assert res.status_code == 200
    assert res.json()["id"] == "robotica"

    res_list = client.get("/api/groups", headers=auth(GROUPS_MGR_ID, GROUPS_MGR_EMAIL, "editor"))
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
        "permissions": ["Publicaciones y Eventos", "Gestión de Roles", "Historial"],
    }
    res = client.post("/api/roles", json=payload, headers=auth(ADMIN_ID, ADMIN_EMAIL, "admin"))
    assert res.status_code == 200
    data = res.json()
    assert data["email"] == "nuevo.admin@upa.edu.py"
    assert data["role"] == "admin"
    assert data["permissions"] == ["publicaciones", "roles", "historial"]

    # Al crear un rol sin especificar permisos, inicia con todas las casillas vacías ([])
    empty_res = client.post(
        "/api/roles",
        json={"email": "sin.permisos@upa.edu.py", "name": "Cuenta Nueva"},
        headers=auth(ADMIN_ID, ADMIN_EMAIL, "admin"),
    )
    assert empty_res.status_code == 200
    assert empty_res.json()["permissions"] == []


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


def test_system_diagnostics_live():
    # Sin autenticación -> 401
    assert client.get("/api/system/diagnostics").status_code == 401

    # Estudiante regular o redactor sin permiso 'apis' -> 403
    assert client.get("/api/system/diagnostics", headers=auth(STUDENT_ID, STUDENT_EMAIL, "user")).status_code == 403
    assert client.get("/api/system/diagnostics", headers=auth(EDITOR_ID, EDITOR_EMAIL, "editor")).status_code == 403

    # Administrador con permiso 'apis' -> 200
    res = client.get("/api/system/diagnostics", headers=auth(ADMIN_ID, ADMIN_EMAIL, "admin"))
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


def test_role_update_logs_exact_permission_diff_in_history():
    headers = auth(ADMIN_ID, ADMIN_EMAIL, "admin")
    client.post(
        "/api/roles",
        json={"email": "diff.test@upa.edu.py", "name": "Diff", "permissions": ["historial"]},
        headers=headers,
    )
    upd = client.put(
        "/api/roles/diff.test@upa.edu.py",
        json={"permissions": ["publicaciones"]},
        headers=headers,
    )
    assert upd.status_code == 200
    res = client.get("/api/history/role/diff.test@upa.edu.py", headers=headers)
    assert res.status_code == 200
    entry = next(e for e in res.json() if e["action"] == "UPDATE_ROLE")
    assert entry["detail"] == "permisos: +publicaciones, -historial"
