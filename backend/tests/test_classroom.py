import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from src.api.classroom import clear_classroom_cache
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
    clear_classroom_cache()
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


def test_root_redirects_to_dashboard():
    response = client.get("/", follow_redirects=False)
    assert response.status_code in (307, 200)
    if response.status_code == 307:
        assert response.headers["location"] == "/dashboard/"


def test_classroom_parallel_deadlines_and_in_memory_cache(monkeypatch):
    import src.api.classroom as classroom_mod

    call_counter = {"courses": 0, "coursework": 0}
    real_async_client = httpx.AsyncClient

    def classroom_handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/v1/courses?" in url:
            call_counter["courses"] += 1
            return httpx.Response(
                200,
                json={
                    "courses": [
                        {
                            "id": "c_100",
                            "name": "Ingenieria de Software II",
                            "section": "Semestre 6",
                            "alternateLink": "https://classroom.google.com/c/c_100",
                            "room": "Lab 3",
                        },
                        {
                            "id": "c_200",
                            "name": "Investigacion de Operaciones",
                            "section": "Semestre 6",
                            "alternateLink": "https://classroom.google.com/c/c_200",
                            "room": "Aula 12",
                        },
                    ]
                },
            )
        if "/courses/c_100/courseWork" in url:
            call_counter["coursework"] += 1
            return httpx.Response(
                200,
                json={
                    "courseWork": [
                        {
                            "id": "w_late",
                            "title": "Entrega Final Arquitectura",
                            "description": "Documento y prototipo funcional",
                            "dueDate": {"year": 2026, "month": 11, "day": 15},
                            "dueTime": {"hours": 23, "minutes": 59},
                            "alternateLink": "https://classroom.google.com/c/c_100/a/w_late",
                            "maxPoints": 100,
                        }
                    ]
                },
            )
        if "/courses/c_200/courseWork" in url:
            call_counter["coursework"] += 1
            return httpx.Response(
                200,
                json={
                    "courseWork": [
                        {
                            "id": "w_early",
                            "title": "Modelo Simplex",
                            "description": "Resolver ejercicios 1 al 5",
                            "dueDate": {"year": 2026, "month": 10, "day": 28},
                            "dueTime": {"hours": 18, "minutes": 30},
                            "alternateLink": "https://classroom.google.com/c/c_200/a/w_early",
                            "maxPoints": 50,
                        }
                    ]
                },
            )
        return httpx.Response(404)

    monkeypatch.setattr(
        classroom_mod.httpx,
        "AsyncClient",
        lambda **kwargs: real_async_client(transport=httpx.MockTransport(classroom_handler), timeout=10.0),
    )

    jwt_token = create_access_token(data={"sub": "102", "email": "estudiante2@upa.edu.py", "role": "user"})
    headers = {"Authorization": f"Bearer {jwt_token}"}

    # 1. First call fetches from API in parallel and populates cache
    resp1 = client.get("/api/classroom/deadlines", headers=headers)
    assert resp1.status_code == 200
    assert resp1.headers.get("X-Classroom-Status") == "active"
    deadlines = resp1.json()
    assert len(deadlines) == 2
    # Must be sorted chronologically (w_early before w_late)
    assert deadlines[0]["id"] == "w_early"
    assert deadlines[0]["course"] == "Investigacion de Operaciones"
    assert deadlines[0]["due_date_formatted"] == "2026-10-28 18:30"
    assert deadlines[0]["max_points"] == 50
    assert deadlines[1]["id"] == "w_late"
    assert deadlines[1]["course"] == "Ingenieria de Software II"
    assert deadlines[1]["due_date_formatted"] == "2026-11-15 23:59"
    assert call_counter["courses"] == 1
    assert call_counter["coursework"] == 2

    # 2. Second call must be served from in-memory cache without network calls
    resp2 = client.get("/api/classroom/deadlines", headers=headers)
    assert resp2.status_code == 200
    assert resp2.headers.get("X-Classroom-Status") == "cached"
    assert len(resp2.json()) == 2
    assert call_counter["courses"] == 1
    assert call_counter["coursework"] == 2

    # 3. Courses endpoint also populates and serves from cache
    c_resp1 = client.get("/api/classroom/courses", headers=headers)
    assert c_resp1.status_code == 200
    assert c_resp1.headers.get("X-Classroom-Status") == "active"
    courses = c_resp1.json()
    assert len(courses) == 2
    assert courses[0]["name"] == "Ingenieria de Software II"
    assert courses[0]["room"] == "Lab 3"

    c_resp2 = client.get("/api/classroom/courses", headers=headers)
    assert c_resp2.status_code == 200
    assert c_resp2.headers.get("X-Classroom-Status") == "cached"


def test_classroom_timeout_and_empty_courses_handling(monkeypatch):
    import src.api.classroom as classroom_mod

    real_async_client = httpx.AsyncClient

    def empty_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"courses": []})

    monkeypatch.setattr(
        classroom_mod.httpx,
        "AsyncClient",
        lambda **kwargs: real_async_client(transport=httpx.MockTransport(empty_handler), timeout=10.0),
    )

    jwt_token = create_access_token(data={"sub": "102", "email": "estudiante2@upa.edu.py", "role": "user"})
    headers = {"Authorization": f"Bearer {jwt_token}"}

    resp_empty = client.get("/api/classroom/deadlines", headers=headers)
    assert resp_empty.status_code == 200
    assert resp_empty.headers.get("X-Classroom-Status") == "no_courses"
    assert resp_empty.json() == []

    # Simulate timeout on Google Classroom API
    clear_classroom_cache()

    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Classroom API timed out", request=request)

    monkeypatch.setattr(
        classroom_mod.httpx,
        "AsyncClient",
        lambda **kwargs: real_async_client(transport=httpx.MockTransport(timeout_handler), timeout=10.0),
    )

    resp_timeout = client.get("/api/classroom/deadlines", headers=headers)
    assert resp_timeout.status_code == 200
    assert resp_timeout.headers.get("X-Classroom-Status") == "network_error"
    assert resp_timeout.json() == []
