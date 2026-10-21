import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from src.auth import create_access_token
from src.database import Base, get_db
from src.main import app
from src.models import User

# In-Memory SQLite Engine für isolierte Classroom-Tests
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
def setup_classroom_database():
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    # Student ohne Classroom-Token
    student_without_token = User(
        id=101,
        email="estudiante1@upa.edu.py",
        full_name="Estudiante Sin Classroom",
        role="user",
        groups=["TIE", "ALL"],
        classroom_token=None,
    )
    # Student mit Classroom-Token
    student_with_token = User(
        id=102,
        email="estudiante2@upa.edu.py",
        full_name="Estudiante Con Classroom",
        role="user",
        groups=["TI", "ALL"],
        classroom_token="ya29.mock_or_test_token_sample",
    )
    db.add(student_without_token)
    db.add(student_with_token)
    db.commit()

    yield

    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.pop(get_db, None)


def test_classroom_deadlines_unauthorized_without_token():
    response = client.get("/api/classroom/deadlines")
    assert response.status_code == 401


def test_classroom_courses_unauthorized_without_token():
    response = client.get("/api/classroom/courses")
    assert response.status_code == 401


def test_classroom_deadlines_without_classroom_token():
    jwt_token = create_access_token(data={"sub": "101", "email": "estudiante1@upa.edu.py", "role": "user"})
    headers = {"Authorization": f"Bearer {jwt_token}"}
    response = client.get("/api/classroom/deadlines", headers=headers)
    assert response.status_code == 200
    assert response.headers.get("X-Classroom-Status") == "missing_token"
    assert response.json() == []


def test_classroom_courses_without_classroom_token():
    jwt_token = create_access_token(data={"sub": "101", "email": "estudiante1@upa.edu.py", "role": "user"})
    headers = {"Authorization": f"Bearer {jwt_token}"}
    response = client.get("/api/classroom/courses", headers=headers)
    assert response.status_code == 200
    assert response.headers.get("X-Classroom-Status") == "missing_token"
    assert response.json() == []


def test_update_classroom_token_endpoint():
    jwt_token = create_access_token(data={"sub": "101", "email": "estudiante1@upa.edu.py", "role": "user"})
    headers = {"Authorization": f"Bearer {jwt_token}"}

    # Zunächst has_classroom_token False
    me_resp = client.get("/api/auth/me", headers=headers)
    assert me_resp.status_code == 200
    assert me_resp.json()["has_classroom_token"] is False

    # Token aktualisieren
    payload = {"classroom_token": "ya29.new_sample_token"}
    update_resp = client.post("/api/auth/classroom-token", json=payload, headers=headers)
    assert update_resp.status_code == 200
    data = update_resp.json()
    assert data["has_classroom_token"] is True

    # Erneuter Abruf /me
    me_resp2 = client.get("/api/auth/me", headers=headers)
    assert me_resp2.status_code == 200
    assert me_resp2.json()["has_classroom_token"] is True


def test_classroom_deadlines_error_handling_when_token_invalid():
    jwt_token = create_access_token(data={"sub": "102", "email": "estudiante2@upa.edu.py", "role": "user"})
    headers = {"Authorization": f"Bearer {jwt_token}"}

    # Da Google API das Test-Token ablehnt oder Timeout/Error meldet, greift Fehlerbehandlung
    response = client.get("/api/classroom/deadlines", headers=headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert response.headers.get("X-Classroom-Status") in ("permission_denied", "api_error", "network_error")


def test_classroom_courses_error_handling_when_token_invalid():
    jwt_token = create_access_token(data={"sub": "102", "email": "estudiante2@upa.edu.py", "role": "user"})
    headers = {"Authorization": f"Bearer {jwt_token}"}

    response = client.get("/api/classroom/courses", headers=headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert response.headers.get("X-Classroom-Status") in ("permission_denied", "api_error", "network_error")


def test_dashboard_static_files_served():
    response = client.get("/dashboard/")
    assert response.status_code == 200
    assert "UPA" in response.text
    assert "Portal Institucional Campus" in response.text
    assert "Google Classroom" in response.text

def test_dashboard_anti_flicker_assets_served():
    response = client.get("/dashboard/")
    assert response.status_code == 200
    # Verifiziert die Anti-Flicker CSS- und Script-Injektion
    assert "html.has-auth #view-login" in response.text
    assert "html.has-auth #view-dashboard" in response.text
    assert "upa_access_token" in response.text

def test_root_redirects_to_dashboard():
    response = client.get("/", follow_redirects=False)
    assert response.status_code in (307, 200)
    if response.status_code == 307:
        assert response.headers["location"] == "/dashboard/"

def test_classroom_deadlines_semantic_payload_and_caching(monkeypatch):
    import httpx
    from src.api import classroom

    # Cache leeren für deterministischen Test
    classroom._DEADLINES_CACHE.clear()

    jwt_token = create_access_token(data={"sub": "102", "email": "estudiante2@upa.edu.py", "role": "user"})
    headers = {"Authorization": f"Bearer {jwt_token}"}

    class MockClassroomTransport(httpx.AsyncBaseTransport):
        call_count = 0

        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            MockClassroomTransport.call_count += 1
            url_str = str(request.url)

            if "courses?studentId=me" in url_str:
                return httpx.Response(200, json={
                    "courses": [
                        {"id": "c-100", "name": "Ingeniería de Software", "section": "TIE-8"}
                    ]
                })
            elif "courses/c-100/courseWork" in url_str:
                return httpx.Response(200, json={
                    "courseWork": [
                        {
                            "id": "w-501",
                            "title": "Entrega Final: Sprint 3",
                            "description": "Subir repositorio y video demo",
                            "dueDate": {"year": 2026, "month": 11, "day": 10},
                            "dueTime": {"hours": 18, "minutes": 30},
                            "alternateLink": "https://classroom.google.com/c/c-100/a/w-501",
                            "maxPoints": 100
                        },
                        {
                            "id": "w-500",
                            "title": "Avance 1: Arquitectura",
                            "description": "Documento técnico",
                            "dueDate": {"year": 2026, "month": 10, "day": 25},
                            "dueTime": {"hours": 23, "minutes": 59},
                            "alternateLink": "https://classroom.google.com/c/c-100/a/w-500",
                            "maxPoints": 50
                        }
                    ]
                })
            return httpx.Response(404, json={})

    original_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original_async_client(transport=MockClassroomTransport(), **kwargs)
    )

    # Erster Aufruf: Fragt API ab, formatiert Payloads semantisch und befüllt Cache
    resp1 = client.get("/api/classroom/deadlines", headers=headers)
    assert resp1.status_code == 200
    assert resp1.headers.get("X-Classroom-Status") == "active"
    deadlines = resp1.json()
    assert len(deadlines) == 2

    # Prüfung der semantischen Pflichtfelder und Datumsformatierung
    first = deadlines[0]
    assert first["id"] == "w-500"
    assert first["course_id"] == "c-100"
    assert first["course"] == "Ingeniería de Software"
    assert first["title"] == "Avance 1: Arquitectura"
    assert first["due_date_formatted"] == "2026-10-25 23:59"
    assert first["max_points"] == 50

    second = deadlines[1]
    assert second["id"] == "w-501"
    assert second["due_date_formatted"] == "2026-11-10 18:30"

    # Zweiter Aufruf: Muss zwingend aus dem In-Memory Cache kommen (Performance & Timeout-Schutz)
    initial_calls = MockClassroomTransport.call_count
    resp2 = client.get("/api/classroom/deadlines", headers=headers)
    assert resp2.status_code == 200
    assert resp2.headers.get("X-Classroom-Status") == "cached"
    assert len(resp2.json()) == 2
    assert MockClassroomTransport.call_count == initial_calls

def test_classroom_courses_semantic_payload_and_caching(monkeypatch):
    import httpx
    from src.api import classroom

    classroom._COURSES_CACHE.clear()

    jwt_token = create_access_token(data={"sub": "102", "email": "estudiante2@upa.edu.py", "role": "user"})
    headers = {"Authorization": f"Bearer {jwt_token}"}

    class MockCoursesTransport(httpx.AsyncBaseTransport):
        call_count = 0

        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            MockCoursesTransport.call_count += 1
            return httpx.Response(200, json={
                "courses": [
                    {
                        "id": "c-201",
                        "name": "Gestión Financiera",
                        "section": "PI-5",
                        "alternateLink": "https://classroom.google.com/c/c-201",
                        "room": "Aula B102"
                    }
                ]
            })

    original_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original_async_client(transport=MockCoursesTransport(), **kwargs)
    )

    # 1. Aufruf
    resp1 = client.get("/api/classroom/courses", headers=headers)
    assert resp1.status_code == 200
    assert resp1.headers.get("X-Classroom-Status") == "active"
    courses = resp1.json()
    assert len(courses) == 1
    assert courses[0]["id"] == "c-201"
    assert courses[0]["name"] == "Gestión Financiera"
    assert courses[0]["section"] == "PI-5"
    assert courses[0]["room"] == "Aula B102"

    # 2. Aufruf: Muss gecached sein
    calls = MockCoursesTransport.call_count
    resp2 = client.get("/api/classroom/courses", headers=headers)
    assert resp2.status_code == 200
    assert resp2.headers.get("X-Classroom-Status") == "cached"
    assert len(resp2.json()) == 1
    assert MockCoursesTransport.call_count == calls

def test_classroom_api_500_error_handling(monkeypatch):
    import httpx
    from src.api import classroom
    classroom._DEADLINES_CACHE.clear()

    jwt_token = create_access_token(data={"sub": "102", "email": "estudiante2@upa.edu.py", "role": "user"})
    headers = {"Authorization": f"Bearer {jwt_token}"}

    class Error500Transport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"error": "Google Internal Server Error"})

    original_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original_async_client(transport=Error500Transport(), **kwargs)
    )

    response = client.get("/api/classroom/deadlines", headers=headers)
    assert response.status_code == 200
    assert response.headers.get("X-Classroom-Status") == "api_error"
    assert response.json() == []

def test_classroom_timeout_network_error_handling(monkeypatch):
    import httpx
    from src.api import classroom
    classroom._DEADLINES_CACHE.clear()

    jwt_token = create_access_token(data={"sub": "102", "email": "estudiante2@upa.edu.py", "role": "user"})
    headers = {"Authorization": f"Bearer {jwt_token}"}

    class TimeoutTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("Connection timed out after 6.0s")

    original_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original_async_client(transport=TimeoutTransport(), **kwargs)
    )

    response = client.get("/api/classroom/deadlines", headers=headers)
    assert response.status_code == 200
    assert response.headers.get("X-Classroom-Status") == "network_error"
    assert response.json() == []

def test_classroom_no_courses_boundary(monkeypatch):
    import httpx
    from src.api import classroom
    classroom._DEADLINES_CACHE.clear()

    jwt_token = create_access_token(data={"sub": "102", "email": "estudiante2@upa.edu.py", "role": "user"})
    headers = {"Authorization": f"Bearer {jwt_token}"}

    class NoCoursesTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"courses": []})

    original_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original_async_client(transport=NoCoursesTransport(), **kwargs)
    )

    response = client.get("/api/classroom/deadlines", headers=headers)
    assert response.status_code == 200
    assert response.headers.get("X-Classroom-Status") == "no_courses"
    assert response.json() == []
