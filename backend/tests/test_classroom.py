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


def test_root_redirects_to_dashboard():
    response = client.get("/", follow_redirects=False)
    assert response.status_code in (307, 200)
    if response.status_code == 307:
        assert response.headers["location"] == "/dashboard/"


def test_classroom_parse_due_date_and_null_hardening():
    from src.api.classroom import _parse_due_date_and_time
    from src.schemas.classroom import ClassroomDeadlineResponse

    # Caso 1: due_date y due_time en None
    due_date_obj, due_time_obj, formatted = _parse_due_date_and_time(None, None)
    assert due_date_obj.year == 0
    assert due_time_obj.hours == 23
    assert formatted == ""

    # Caso 2: due_date diccionario con valores validos y due_time valido
    d2, t2, fmt2 = _parse_due_date_and_time(
        {"year": 2026, "month": 11, "day": 5},
        {"hours": 18, "minutes": 30},
    )
    assert d2.year == 2026
    assert d2.month == 11
    assert d2.day == 5
    assert t2.hours == 18
    assert t2.minutes == 30
    assert fmt2 == "2026-11-05 18:30"

    # Caso 3: Verificacion de esquema sin nulos
    item = ClassroomDeadlineResponse(
        id="100",
        assignment_id="100",
        course_id="200",
        course="Ingenieria de Software",
        course_name="Ingenieria de Software",
        title="Proyecto Final",
        description="",
        due_date=d2,
        due_time=t2,
        due_date_formatted=fmt2,
        alternate_link="https://classroom.google.com/c/200",
        max_points=100.0,
    )
    dumped = item.model_dump()
    assert all(v is not None for v in dumped.values())

