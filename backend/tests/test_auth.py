import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from src.auth import create_access_token
from src.database import Base, get_db
from src.main import app
from src.models import User

# In-Memory SQLite Engine für isolierte Auth-Tests
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_auth_database():
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    # 1 Normaler Student
    student = User(id=10, email="student@upa.edu.py", full_name="Normaler Student", role="user", groups=["TIE"])
    # 1 Administrator
    admin = User(id=20, email="admin@upa.edu.py", full_name="Admin User", role="admin", groups=["ALL"])
    # Pascal Thommen (darf Mailgruppen einsehen)
    pascal = User(
        id=30, email="pascal.thommen@upa.edu.py", full_name="Pascal Thommen", role="admin", groups=["ALL", "TIE", "TI"]
    )
    db.add(student)
    db.add(admin)
    db.add(pascal)
    db.commit()
    yield
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.pop(get_db, None)


def test_jwt_creation_and_decoding():
    token = create_access_token(data={"sub": "10", "email": "student@upa.edu.py", "role": "user"})
    assert isinstance(token, str)
    assert len(token) > 20


def test_get_me_unauthorized_without_token():
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_get_me_authorized_with_token():
    token = create_access_token(data={"sub": "10", "email": "student@upa.edu.py", "role": "user"})
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/api/auth/me", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "student@upa.edu.py"
    assert data["role"] == "user"
    # Normaler Student darf Gruppen nicht direkt sehen
    assert data["groups"] == []


def test_get_me_shows_mailgroups_exclusively_for_pascal():
    token = create_access_token(data={"sub": "30", "email": "pascal.thommen@upa.edu.py", "role": "admin"})
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/api/auth/me", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "pascal.thommen@upa.edu.py"
    assert data["groups"] == ["ALL", "TIE", "TI"]


def test_create_news_forbidden_for_normal_student():
    token = create_access_token(data={"sub": "10", "email": "student@upa.edu.py", "role": "user"})
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"title": "Versuchter Fake Post", "content": "Sollte blockiert werden", "is_news": True}
    response = client.post("/api/news", json=payload, headers=headers)
    assert response.status_code == 403
    assert "Administrator-Rechte erforderlich" in response.json()["detail"]


def test_create_news_allowed_for_admin():
    token = create_access_token(data={"sub": "20", "email": "admin@upa.edu.py", "role": "admin"})
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "title": "Offizieller Admin Post",
        "content": "Erfolgreich erstellt durch Administrator",
        "is_news": True,
        "is_pinned": True,
    }
    response = client.post("/api/news", json=payload, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Offizieller Admin Post"
    assert data["is_pinned"] is True


def test_get_my_groups_authorized():
    token = create_access_token(data={"sub": "10", "email": "student@upa.edu.py", "role": "user"})
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/api/auth/groups", headers=headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_map_groups_to_logical_tags():
    from src.services.google_groups import map_groups_to_logical_tags

    groups = [
        {"id": "1", "name": "Estudiantes TIE 2025", "email": "estudiantes.tie2025@upa.edu.py", "description": ""},
        {"id": "2", "name": "Profesores Ingenieria", "email": "prof.ingenieria@upa.edu.py", "description": ""},
    ]
    tags = map_groups_to_logical_tags(groups)
    assert "ALL" in tags
    assert "TIE" in tags
    assert "PROF" in tags
    assert "Estudiantes TIE 2025" in tags


def test_login_google_redirect():
    response = client.get("/api/auth/login-google", follow_redirects=False)
    assert response.status_code == 307
    location = response.headers.get("location", "")
    assert "accounts.google.com" in location
    assert "client_id=" in location
    assert "redirect_uri=" in location


def test_google_callback_missing_code_redirects_error():
    response = client.get("/api/auth/google", follow_redirects=False)
    assert response.status_code == 307
    location = response.headers.get("location", "")
    assert "/dashboard/?auth_error=missing_code" in location


def test_google_callback_error_param_redirects():
    response = client.get("/api/auth/google?error=access_denied", follow_redirects=False)
    assert response.status_code == 307
    location = response.headers.get("location", "")
    assert "/dashboard/?auth_error=access_denied" in location


def test_dev_login_admin_pascal_returns_full_jwt_session():
    response = client.post(
        "/api/auth/dev-login",
        json={"email": "pascal.thommen@upa.edu.py"},
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["access_token"], str)
    assert len(data["access_token"]) > 20
    assert data["token_type"] == "bearer"

    user = data["user"]
    assert user["id"] == 30
    assert user["email"] == "pascal.thommen@upa.edu.py"
    assert user["full_name"] == "Pascal Thommen"
    assert user["role"] == "admin"
    assert "ALL" in user["groups"]
    assert "TIE" in user["groups"]
    assert isinstance(user["google_groups"], list)
    assert user["has_classroom_token"] is False

    # Verificar que el token generado funciona inmediatamente en /api/auth/me
    me_resp = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {data['access_token']}"},
    )
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["email"] == "pascal.thommen@upa.edu.py"
    assert me_data["role"] == "admin"
    assert "TIE" in me_data["groups"]


def test_dev_login_creates_new_student_with_strict_privacy():
    response = client.post(
        "/api/auth/dev-login",
        json={"email": "  Maria.Gomez@upa.edu.py  "},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["token_type"] == "bearer"
    user = data["user"]
    assert user["email"] == "maria.gomez@upa.edu.py"
    assert user["full_name"] == "Maria Gomez"
    assert user["role"] == "user"
    # Estudiante regular no visualiza listas de distribucion internas
    assert user["groups"] == []
    assert user["google_groups"] == []
    assert user["has_classroom_token"] is False


def test_dev_login_rejects_invalid_email_formats_400():
    invalid_emails = [
        "",
        "   ",
        "sin_arroba.upa.edu.py",
        "@upa.edu.py",
        "doble@@upa.edu.py",
        "con espacio@upa.edu.py",
        "usuario@dominio_sin_punto",
    ]
    for bad_email in invalid_emails:
        resp = client.post("/api/auth/dev-login", json={"email": bad_email})
        assert resp.status_code == 400, f"Expected 400 for {bad_email!r}, got {resp.status_code}"
        assert "detail" in resp.json()


def test_dev_login_rejects_non_upa_domain_403():
    forbidden_emails = [
        "externo@gmail.com",
        "usuario@outlook.com",
        "falso@upa.edu.py.attacker.com",
        "estudiante@fakeupa.edu.py",
    ]
    for ext_email in forbidden_emails:
        resp = client.post("/api/auth/dev-login", json={"email": ext_email})
        assert resp.status_code == 403, f"Expected 403 for {ext_email!r}, got {resp.status_code}"
        assert "upa.edu.py" in resp.json()["detail"]


def test_google_login_empty_token_returns_400():
    resp = client.post("/api/auth/google", json={"id_token": "   "})
    assert resp.status_code == 400
    assert "detail" in resp.json()


def test_classroom_token_empty_returns_400():
    token = create_access_token(data={"sub": "10", "email": "student@upa.edu.py", "role": "user"})
    resp = client.post(
        "/api/auth/classroom-token",
        json={"classroom_token": "   "},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert "detail" in resp.json()


def test_get_me_invalid_token_returns_401():
    resp = client.get(
        "/api/auth/me",
        headers={"Authorization": "Bearer token.invalido.manipulado"},
    )
    assert resp.status_code == 401
    assert "detail" in resp.json()


def test_get_me_sanitizes_null_google_group_fields():
    db = TestingSessionLocal()
    pascal = db.query(User).filter(User.email == "pascal.thommen@upa.edu.py").first()
    pascal.google_groups = [{"id": None, "name": None, "email": "tie@upa.edu.py", "description": None}]
    db.commit()
    db.close()

    token = create_access_token(data={"sub": "30", "email": "pascal.thommen@upa.edu.py", "role": "admin"})
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["google_groups"]) == 1
    grp = data["google_groups"][0]
    assert grp["id"] == ""
    assert grp["name"] == ""
    assert grp["email"] == "tie@upa.edu.py"
    assert grp["description"] == ""
