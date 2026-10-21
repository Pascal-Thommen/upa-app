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
        groups=["ALL", "TIE", "TI"]
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

def test_login_google_avoids_repeated_consent():
    response = client.get("/api/auth/login-google", follow_redirects=False)
    assert response.status_code == 307
    location = response.headers.get("location", "")
    assert "prompt=select_account" in location
    assert "prompt=consent" not in location
    assert "classroom.courses.readonly" in location
    assert "classroom.coursework.me.readonly" in location
    assert "access_type=offline" in location

def test_get_me_semantic_payload_normal_student():
    token = create_access_token(data={"sub": "10", "email": "student@upa.edu.py", "role": "user"})
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/api/auth/me", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 10
    assert data["email"] == "student@upa.edu.py"
    assert data["full_name"] == "Normaler Student"
    assert data["role"] == "user"
    assert data["groups"] == []
    assert data["google_groups"] == []
    assert data["has_classroom_token"] is False

def test_get_me_semantic_payload_pascal_admin():
    token = create_access_token(data={"sub": "30", "email": "pascal.thommen@upa.edu.py", "role": "admin"})
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/api/auth/me", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 30
    assert data["email"] == "pascal.thommen@upa.edu.py"
    assert data["role"] == "admin"
    assert set(data["groups"]) == {"ALL", "TIE", "TI"}
    assert isinstance(data["google_groups"], list)

def test_get_my_groups_semantic_payload_pascal():
    db = TestingSessionLocal()
    pascal = db.query(User).filter(User.email == "pascal.thommen@upa.edu.py").first()
    pascal.google_groups = [
        {"id": "g-101", "name": "Dirección General", "email": "direccion@upa.edu.py", "description": "Grupo directivo"},
        {"id": "g-102", "name": "Docentes TIE", "email": "docentes.tie@upa.edu.py", "description": "Profesores de carrera"}
    ]
    db.commit()
    db.close()

    token = create_access_token(data={"sub": "30", "email": "pascal.thommen@upa.edu.py", "role": "admin"})
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/api/auth/groups", headers=headers)
    assert response.status_code == 200
    groups = response.json()
    assert len(groups) == 2
    assert groups[0]["name"] == "Dirección General"
    assert groups[0]["email"] == "direccion@upa.edu.py"
    assert groups[0]["description"] == "Grupo directivo"
    assert groups[1]["name"] == "Docentes TIE"
    assert groups[1]["email"] == "docentes.tie@upa.edu.py"

def test_get_my_groups_empty_for_normal_student():
    token = create_access_token(data={"sub": "10", "email": "student@upa.edu.py", "role": "user"})
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/api/auth/groups", headers=headers)
    assert response.status_code == 200
    assert response.json() == []

@pytest.mark.asyncio
async def test_recursive_google_groups_resolution(monkeypatch):
    """
    Testet die rekursive Auflösung verschachtelter Google Groups:
    Nutzer ist direkt in Gruppe 'Estudiantes TIE'.
    'Estudiantes TIE' ist Untergruppe von 'Facultad de Ingeniería'.
    'Facultad de Ingeniería' ist Untergruppe von 'Comunidad General UPA'.
    Ergebnis muss alle 3 Gruppen enthalten.
    """
    import httpx
    import jwt
    from src.services import google_groups

    monkeypatch.setattr(
        google_groups,
        "_load_service_account_credentials",
        lambda: {
            "client_email": "test-sa@upa.iam.gserviceaccount.com",
            "private_key": "dummy-key",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    )
    monkeypatch.setattr(jwt, "encode", lambda *args, **kwargs: "mock-signed-jwt")

    class MockTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            url_str = str(request.url)
            if "oauth2.googleapis.com/token" in url_str:
                return httpx.Response(200, json={"access_token": "mock-sa-access-token"})

            if "userKey=student@upa.edu.py" in url_str:
                return httpx.Response(200, json={
                    "groups": [
                        {"id": "1", "name": "Estudiantes TIE", "email": "estudiantes.tie@upa.edu.py", "description": "Nivel 1"}
                    ]
                })
            elif "userKey=estudiantes.tie@upa.edu.py" in url_str:
                return httpx.Response(200, json={
                    "groups": [
                        {"id": "2", "name": "Facultad de Ingeniería", "email": "ingenieria@upa.edu.py", "description": "Nivel 2"}
                    ]
                })
            elif "userKey=ingenieria@upa.edu.py" in url_str:
                return httpx.Response(200, json={
                    "groups": [
                        {"id": "3", "name": "Comunidad UPA General", "email": "comunidad@upa.edu.py", "description": "Nivel 3"}
                    ]
                })
            elif "userKey=comunidad@upa.edu.py" in url_str:
                return httpx.Response(200, json={"groups": []})

            return httpx.Response(404, json={"error": "not found"})

    original_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original_async_client(transport=MockTransport(), **kwargs)
    )

    resolved = await google_groups.get_google_groups_for_user("student@upa.edu.py")
    assert len(resolved) == 3
    emails = {g["email"] for g in resolved}
    assert emails == {"estudiantes.tie@upa.edu.py", "ingenieria@upa.edu.py", "comunidad@upa.edu.py"}
    names = {g["name"] for g in resolved}
    assert names == {"Estudiantes TIE", "Facultad de Ingeniería", "Comunidad UPA General"}

@pytest.mark.asyncio
async def test_recursive_google_groups_cycle_handling(monkeypatch):
    """
    Testet den Schutz gegen Zyklen bei verschachtelten Google Groups:
    Gruppe A verweist auf Gruppe B und Gruppe B verweist auf Gruppe A.
    Die Breitensuche muss ohne Endlosschleife terminieren und beide Gruppen liefern.
    """
    import httpx
    import jwt
    from src.services import google_groups

    monkeypatch.setattr(
        google_groups,
        "_load_service_account_credentials",
        lambda: {
            "client_email": "test-sa@upa.iam.gserviceaccount.com",
            "private_key": "dummy-key",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    )
    monkeypatch.setattr(jwt, "encode", lambda *args, **kwargs: "mock-jwt")

    class MockCycleTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            url_str = str(request.url)
            if "oauth2.googleapis.com/token" in url_str:
                return httpx.Response(200, json={"access_token": "token"})

            if "userKey=user@upa.edu.py" in url_str:
                return httpx.Response(200, json={
                    "groups": [{"id": "A", "name": "Grupo A", "email": "groupa@upa.edu.py"}]
                })
            elif "userKey=groupa@upa.edu.py" in url_str:
                return httpx.Response(200, json={
                    "groups": [{"id": "B", "name": "Grupo B", "email": "groupb@upa.edu.py"}]
                })
            elif "userKey=groupb@upa.edu.py" in url_str:
                return httpx.Response(200, json={
                    "groups": [{"id": "A", "name": "Grupo A", "email": "groupa@upa.edu.py"}]
                })

            return httpx.Response(404, json={"error": "not found"})

    original_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original_async_client(transport=MockCycleTransport(), **kwargs)
    )

    resolved = await google_groups.get_google_groups_for_user("user@upa.edu.py")
    assert len(resolved) == 2
    emails = {g["email"] for g in resolved}
    assert emails == {"groupa@upa.edu.py", "groupb@upa.edu.py"}

@pytest.mark.asyncio
async def test_google_groups_service_handles_missing_sa(monkeypatch):
    from src.services import google_groups
    monkeypatch.setattr(google_groups, "_load_service_account_credentials", lambda: None)
    result = await google_groups.get_google_groups_for_user("user@upa.edu.py")
    assert result == []

