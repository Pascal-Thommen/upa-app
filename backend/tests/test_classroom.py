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
    assert "Portal Campus Institucional" in response.text or "Portal Institucional" in response.text
    assert "Google Classroom" in response.text


def test_dashboard_spa_subroutes_served():
    subroutes = [
        "/dashboard/publicaciones",
        "/dashboard/grupos",
        "/dashboard/roles",
        "/dashboard/diagnostico",
        "/dashboard/estudiantes",
        "/dashboard/ruta-desconocida",
    ]
    for route in subroutes:
        response = client.get(route)
        assert response.status_code == 200, f"Error al servir subruta SPA {route}"
        assert "UPA" in response.text
        assert "Portal Campus Institucional" in response.text or "Portal Institucional" in response.text

    # Archivo con extension inexistente debe dar 404
    missing_asset = client.get("/dashboard/no-existe.png")
    assert missing_asset.status_code == 404


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


def test_classroom_auto_refresh_on_http_401_for_deadlines_and_courses(monkeypatch):
    import httpx
    from src.api.classroom import clear_classroom_cache

    clear_classroom_cache()
    db = TestingSessionLocal()
    student = db.query(User).filter(User.id == 102).first()
    student.classroom_token = "ya29.expired_60min_token"
    student.classroom_refresh_token = "1//0g_valid_refresh_token_upa"
    db.commit()
    db.close()

    real_async_client = httpx.AsyncClient
    call_log: list[tuple[str, str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        auth_header = request.headers.get("Authorization", "")
        call_log.append((request.method, url, auth_header))

        if "oauth2.googleapis.com/token" in url:
            body_text = request.content.decode("utf-8")
            assert "grant_type=refresh_token" in body_text
            assert "1%2F%2F0g_valid_refresh_token_upa" in body_text or "1//0g_valid_refresh_token_upa" in body_text
            return httpx.Response(
                200,
                json={
                    "access_token": "ya29.refreshed_live_token_2026",
                    "expires_in": 3600,
                    "token_type": "Bearer",
                },
            )

        if "classroom.googleapis.com/v1/courses?" in url:
            if auth_header == "Bearer ya29.expired_60min_token":
                return httpx.Response(401, json={"error": {"code": 401, "message": "Unauthenticated"}})
            if auth_header == "Bearer ya29.refreshed_live_token_2026":
                return httpx.Response(
                    200,
                    json={
                        "courses": [
                            {
                                "id": "course_tie_4",
                                "name": "Ingenieria de Software II",
                                "section": "Semestre 4",
                                "alternateLink": "https://classroom.google.com/c/course_tie_4",
                                "room": "Aula 204",
                            }
                        ]
                    },
                )

        if "courseWork" in url:
            if auth_header == "Bearer ya29.refreshed_live_token_2026":
                return httpx.Response(
                    200,
                    json={
                        "courseWork": [
                            {
                                "id": "work_900",
                                "title": "Proyecto Integrador Final",
                                "description": "Entrega de API REST y App Movil",
                                "dueDate": {"year": 2026, "month": 11, "day": 15},
                                "dueTime": {"hours": 23, "minutes": 59},
                                "alternateLink": "https://classroom.google.com/c/course_tie_4/a/work_900",
                                "maxPoints": 100,
                            }
                        ]
                    },
                )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *args, **kwargs: real_async_client(transport=transport, timeout=kwargs.get("timeout", 10.0)),
    )

    jwt_token = create_access_token(data={"sub": "102", "email": "estudiante2@upa.edu.py", "role": "user"})
    headers = {"Authorization": f"Bearer {jwt_token}"}

    # 1. Consultar deadlines: debe detectar 401, refrescar token contra Google OAuth y retornar la tarea
    resp = client.get("/api/classroom/deadlines", headers=headers)
    assert resp.status_code == 200
    assert resp.headers.get("X-Classroom-Status") == "active"
    assert resp.headers.get("X-Classroom-Token-Refreshed") == "true"
    deadlines = resp.json()
    assert len(deadlines) == 1
    assert deadlines[0]["id"] == "work_900"
    assert deadlines[0]["title"] == "Proyecto Integrador Final"
    assert deadlines[0]["course_name"] == "Ingenieria de Software II"
    assert deadlines[0]["due_date_formatted"] == "2026-11-15 23:59"

    # 2. Verificar que el nuevo access_token quedo persistido en la base de datos
    db_verify = TestingSessionLocal()
    updated_student = db_verify.query(User).filter(User.id == 102).first()
    assert updated_student.classroom_token == "ya29.refreshed_live_token_2026"
    db_verify.close()

    # 3. Forzar expiracion nuevamente y probar auto-refresh en /api/classroom/courses
    clear_classroom_cache()
    db_exp = TestingSessionLocal()
    s2 = db_exp.query(User).filter(User.id == 102).first()
    s2.classroom_token = "ya29.expired_60min_token"
    db_exp.commit()
    db_exp.close()

    courses_resp = client.get("/api/classroom/courses", headers=headers)
    assert courses_resp.status_code == 200
    assert courses_resp.headers.get("X-Classroom-Status") == "active"
    assert courses_resp.headers.get("X-Classroom-Token-Refreshed") == "true"
    courses = courses_resp.json()
    assert len(courses) == 1
    assert courses[0]["id"] == "course_tie_4"
    assert courses[0]["name"] == "Ingenieria de Software II"


def test_classroom_auto_refresh_handles_revoked_refresh_token_gracefully(monkeypatch):
    import httpx
    from src.api.classroom import clear_classroom_cache

    clear_classroom_cache()
    db = TestingSessionLocal()
    student = db.query(User).filter(User.id == 102).first()
    student.classroom_token = "ya29.expired_token"
    student.classroom_refresh_token = "1//0g_revoked_refresh_token"
    db.commit()
    db.close()

    real_async_client = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "oauth2.googleapis.com/token" in url:
            return httpx.Response(400, json={"error": "invalid_grant"})
        return httpx.Response(401, json={"error": {"code": 401, "message": "Unauthenticated"}})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *args, **kwargs: real_async_client(transport=transport, timeout=kwargs.get("timeout", 10.0)),
    )

    jwt_token = create_access_token(data={"sub": "102", "email": "estudiante2@upa.edu.py", "role": "user"})
    headers = {"Authorization": f"Bearer {jwt_token}"}

    resp = client.get("/api/classroom/deadlines", headers=headers)
    assert resp.status_code == 200
    assert resp.headers.get("X-Classroom-Status") == "permission_denied"
    assert resp.json() == []
