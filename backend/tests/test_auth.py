from datetime import timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from src.auth import SESSION_COOKIE_NAME, create_access_token
from src.database import Base, get_db
from src.main import app
from src.models import User

# In-Memory SQLite Engine für isolierte Auth-Tests
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
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
def setup_auth_database():
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    
    # 1 Normaler Student
    student = User(
        id=10,
        email="student@upa.edu.py",
        full_name="Normaler Student",
        role="user",
        groups=["TIE"]
    )
    # 1 Administrator
    admin = User(
        id=20,
        email="admin@upa.edu.py",
        full_name="Admin User",
        role="admin",
        groups=["ALL"]
    )
    # Pascal Thommen (darf Mailgruppen einsehen)
    pascal = User(
        id=30,
        email="pascal.thommen@upa.edu.py",
        full_name="Pascal Thommen",
        role="admin",
        groups=["ALL", "TIE", "TI"],
        google_groups=[
            {
                "id": "grp_1",
                "name": "Ingenieria Empresarial TIE",
                "email": "tie@upa.edu.py",
                "description": "Grupo oficial de Ingenieria Empresarial",
            },
            {
                "id": "grp_2",
                "name": "Claustro Docente UPA",
                "email": "docentes@upa.edu.py",
                "description": "Grupo superior de docentes",
            },
        ],
    )
    db.add(student)
    db.add(admin)
    db.add(pascal)
    db.commit()
    yield
    client.cookies.clear()
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
    payload = {
        "title": "Versuchter Fake Post",
        "content": "Sollte blockiert werden",
        "is_news": True
    }
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
        "is_pinned": True
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
        {"id": "2", "name": "Profesores Ingenieria", "email": "prof.ingenieria@upa.edu.py", "description": ""}
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
    assert "accounts.google.com/o/oauth2/v2/auth" in location
    assert "client_id=" in location
    assert "redirect_uri=" in location
    assert "prompt=select_account" in location
    assert "prompt=consent" not in location
    assert "hd=upa.edu.py" in location
    assert "classroom.courses.readonly" in location
    assert "classroom.coursework.me.readonly" in location


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


def test_google_callback_full_flow_and_cookie_session(monkeypatch):
    import src.api.auth as auth_api

    real_async_client = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        if "oauth2.googleapis.com/token" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "access_token": "ya29.real_classroom_token_123",
                    "id_token": "valid_google_id_token_xyz",
                    "expires_in": 3600,
                    "token_type": "Bearer",
                },
            )
        return httpx.Response(404)

    monkeypatch.setattr(
        auth_api.httpx,
        "AsyncClient",
        lambda **kwargs: real_async_client(transport=httpx.MockTransport(handler), timeout=10.0),
    )

    async def fake_verify_token(id_token: str):
        assert id_token == "valid_google_id_token_xyz"
        return {
            "email": "pascal.thommen@upa.edu.py",
            "name": "Pascal Thommen",
            "aud": "50361321197-om1eptt5qisjn8jeunkjs47o56il7s33.apps.googleusercontent.com",
        }

    async def fake_get_groups(email: str):
        return [
            {
                "id": "g_direct",
                "name": "Ingenieria TIE",
                "email": "tie@upa.edu.py",
                "description": "Direct group",
            },
            {
                "id": "g_nested",
                "name": "Comunidad Docente UPA",
                "email": "docentes@upa.edu.py",
                "description": "Nested parent group",
            },
        ]

    monkeypatch.setattr(auth_api, "verify_google_id_token", fake_verify_token)
    monkeypatch.setattr(auth_api, "get_google_groups_for_user", fake_get_groups)

    response = client.get("/api/auth/google?code=valid_oauth_code_123", follow_redirects=False)
    assert response.status_code == 307
    location = response.headers.get("location", "")
    assert location.startswith("/dashboard/?token=")
    assert SESSION_COOKIE_NAME in response.cookies

    # Verify session works via cookie alone and returns full semantic profile + official google_groups
    client.cookies.set(SESSION_COOKIE_NAME, response.cookies[SESSION_COOKIE_NAME])
    me_resp = client.get("/api/auth/me")
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["email"] == "pascal.thommen@upa.edu.py"
    assert me_data["full_name"] == "Pascal Thommen"
    assert me_data["role"] == "admin"
    assert me_data["has_classroom_token"] is True
    assert len(me_data["google_groups"]) == 2
    assert me_data["google_groups"][0]["name"] == "Ingenieria TIE"
    assert me_data["google_groups"][0]["email"] == "tie@upa.edu.py"
    assert me_data["google_groups"][1]["name"] == "Comunidad Docente UPA"
    assert me_data["google_groups"][1]["email"] == "docentes@upa.edu.py"

    # Verify logout clears cookie
    logout_resp = client.post("/api/auth/logout")
    assert logout_resp.status_code == 200
    assert logout_resp.json()["status"] == "logged_out"


def test_google_callback_network_timeout_redirects_gracefully(monkeypatch):
    import src.api.auth as auth_api

    real_async_client = httpx.AsyncClient

    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Timeout during token exchange", request=request)

    monkeypatch.setattr(
        auth_api.httpx,
        "AsyncClient",
        lambda **kwargs: real_async_client(transport=httpx.MockTransport(timeout_handler), timeout=10.0),
    )

    response = client.get("/api/auth/google?code=timeout_code", follow_redirects=False)
    assert response.status_code == 307
    assert "/dashboard/?auth_error=token_exchange_failed" in response.headers.get("location", "")


def test_expired_and_invalid_jwt_rejected():
    expired_token = create_access_token(
        data={"sub": "10", "email": "student@upa.edu.py", "role": "user"},
        expires_delta=timedelta(minutes=-10),
    )
    resp_expired = client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert resp_expired.status_code == 401
    assert "Ungültiger oder abgelaufener Session Token" in resp_expired.json()["detail"]

    resp_malformed = client.get("/api/auth/me", headers={"Authorization": "Bearer invalid.jwt.token"})
    assert resp_malformed.status_code == 401


@pytest.mark.anyio
async def test_recursive_google_groups_resolution_and_cycle_safety(monkeypatch):
    import src.services.google_groups as gg_mod

    monkeypatch.setattr(
        gg_mod,
        "_load_service_account_credentials",
        lambda: {
            "client_email": "sa@upa-project.iam.gserviceaccount.com",
            "private_key": "fake-key",
            "token_uri": "https://oauth2.googleapis.com/token",
        },
    )
    monkeypatch.setattr(gg_mod.jwt, "encode", lambda payload, key, algorithm: "signed_jwt_assertion")

    real_async_client = httpx.AsyncClient

    def directory_handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "oauth2.googleapis.com/token" in url:
            return httpx.Response(200, json={"access_token": "dir_admin_token_123"})
        if "userKey=pascal.thommen@upa.edu.py" in url or "userKey=pascal.thommen%40upa.edu.py" in url:
            return httpx.Response(
                200,
                json={
                    "groups": [
                        {
                            "id": "g1",
                            "name": "Docentes TI",
                            "email": "docentes.ti@upa.edu.py",
                            "description": "Direct membership",
                        }
                    ]
                },
            )
        if "userKey=docentes.ti@upa.edu.py" in url or "userKey=docentes.ti%40upa.edu.py" in url:
            return httpx.Response(
                200,
                json={
                    "groups": [
                        {
                            "id": "g2",
                            "name": "Claustro General",
                            "email": "claustro@upa.edu.py",
                            "description": "Indirect parent membership",
                        }
                    ]
                },
            )
        if "userKey=claustro@upa.edu.py" in url or "userKey=claustro%40upa.edu.py" in url:
            # Includes circular reference back to g1 to test cycle termination
            return httpx.Response(
                200,
                json={
                    "groups": [
                        {
                            "id": "g1",
                            "name": "Docentes TI",
                            "email": "docentes.ti@upa.edu.py",
                            "description": "Cycle back",
                        },
                        {
                            "id": "g3",
                            "name": "Comunidad UPA",
                            "email": "comunidad@upa.edu.py",
                            "description": "Top level group",
                        },
                    ]
                },
            )
        return httpx.Response(200, json={"groups": []})

    monkeypatch.setattr(
        gg_mod.httpx,
        "AsyncClient",
        lambda **kwargs: real_async_client(transport=httpx.MockTransport(directory_handler), timeout=10.0),
    )

    groups = await gg_mod.get_google_groups_for_user("pascal.thommen@upa.edu.py")
    assert len(groups) == 3
    emails = [g["email"] for g in groups]
    names = [g["name"] for g in groups]
    assert emails == ["docentes.ti@upa.edu.py", "claustro@upa.edu.py", "comunidad@upa.edu.py"]
    assert names == ["Docentes TI", "Claustro General", "Comunidad UPA"]


def test_exclusive_google_groups_visibility_in_groups_and_app_state():
    # Pascal Thommen sees official google_groups
    pascal_token = create_access_token(data={"sub": "30", "email": "pascal.thommen@upa.edu.py", "role": "admin"})
    pascal_headers = {"Authorization": f"Bearer {pascal_token}"}

    groups_resp = client.get("/api/auth/groups", headers=pascal_headers)
    assert groups_resp.status_code == 200
    groups_data = groups_resp.json()
    assert len(groups_data) == 2
    assert groups_data[0]["name"] == "Ingenieria Empresarial TIE"
    assert groups_data[0]["email"] == "tie@upa.edu.py"

    state_resp = client.get("/api/v1/app-state", headers=pascal_headers)
    assert state_resp.status_code == 200
    state_user = state_resp.json()["user"]
    assert len(state_user["google_groups"]) == 2
    assert state_user["google_groups"][0]["email"] == "tie@upa.edu.py"

    # Normal student and other admin receive empty google_groups list
    student_token = create_access_token(data={"sub": "10", "email": "student@upa.edu.py", "role": "user"})
    student_groups = client.get("/api/auth/groups", headers={"Authorization": f"Bearer {student_token}"}).json()
    assert student_groups == []
