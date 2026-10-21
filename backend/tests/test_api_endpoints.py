from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from src.auth import create_access_token
from src.database import Base, get_db
from src.main import app
from src.models import Post, User

# SQLite In-Memory Engine mit StaticPool für gemeinsamen Speicher aller Connections
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
def setup_database():
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    
    # User anlegen
    user = User(email="test@upa.edu.py", full_name="Test User", role="admin", groups=["TIE"])
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # 1 News Post (Instagram)
    news = Post(
        title="Búsqueda Laboral: Recepcionista",
        caption="¡Estamos buscando Recepcionista!",
        content="Texto completo de funciones...",
        post_type="INSTAGRAM",
        is_news=True,
        is_event=False,
        is_pinned=False,
        target_groups=["ALL"],
        author_id=user.id
    )
    db.add(news)
    
    # 1 Event Post (Charla IA)
    tomorrow = datetime.now(UTC) + timedelta(days=1)
    event = Post(
        title="¿Qué significa seguir siendo humanos en la era de la IA?",
        content="Charla magistral en auditorio...",
        post_type="MANUAL",
        is_news=True,
        is_event=True,
        is_pinned=True,
        event_start=tomorrow,
        location="Auditorio Edificio 1",
        has_registration=True,
        target_groups=["ALL", "TIE"],
        author_id=user.id
    )
    db.add(event)
    db.commit()
    
    yield
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.pop(get_db, None)

def test_get_news_endpoint_requires_auth():
    # Ohne Authentifizierung -> 401
    response = client.get("/api/news")
    assert response.status_code == 401

    # Mit gültigem Token -> 200
    token = create_access_token({"sub": "1", "email": "test@upa.edu.py", "role": "admin"})
    response_auth = client.get("/api/news", headers={"Authorization": f"Bearer {token}"})
    assert response_auth.status_code == 200
    data = response_auth.json()
    assert len(data) == 2  # Beide sind is_news = True
    assert data[0]["is_pinned"] is True
    assert data[0]["title"] == "¿Qué significa seguir siendo humanos en la era de la IA?"
    assert data[1]["title"] == "Búsqueda Laboral: Recepcionista"

def test_get_events_endpoint_requires_auth():
    # Ohne Authentifizierung -> 401
    response = client.get("/api/events")
    assert response.status_code == 401

    # Mit gültigem Token -> 200
    token = create_access_token({"sub": "1", "email": "test@upa.edu.py", "role": "admin"})
    response_auth = client.get("/api/events", headers={"Authorization": f"Bearer {token}"})
    assert response_auth.status_code == 200
    data = response_auth.json()
    assert len(data) == 1  # Nur der Event
    assert data[0]["title"] == "¿Qué significa seguir siendo humanos en la era de la IA?"
    assert data[0]["location"] == "Auditorio Edificio 1"
    assert data[0]["has_registration"] is True

def test_filter_by_group():
    token = create_access_token({"sub": "1", "email": "test@upa.edu.py", "role": "admin"})
    response = client.get("/api/news?group=TIE", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2


def _assert_no_null_values(obj, path="root"):
    """Verifica recursivamente que ningun campo de un payload JSON sea None."""
    assert obj is not None, f"Null value found at {path}"
    if isinstance(obj, dict):
        for k, v in obj.items():
            _assert_no_null_values(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            _assert_no_null_values(item, f"{path}[{idx}]")


def test_anti_conflict_audit_no_null_values_across_endpoints():
    """
    Inserta registros con columnas opcionales en None y verifica que
    /api/v1/app-state, /api/auth/me, /api/news y /api/events entreguen
    objetos JSON completos sin ningun valor null.
    """
    db = TestingSessionLocal()
    sparse_post = Post(
        title="Aviso Minimo Sin Opcionales",
        caption=None,
        content=None,
        post_type="MANUAL",
        is_news=True,
        is_event=True,
        is_pinned=False,
        event_start=datetime.now(UTC) + timedelta(days=2),
        event_end=None,
        location=None,
        target_groups=[],
        has_registration=False,
        instagram_id=None,
        media_type=None,
        media_url=None,
        permalink=None,
    )
    db.add(sparse_post)
    db.commit()
    db.close()

    login_resp = client.post(
        "/api/auth/dev-login",
        json={"email": "pascal.thommen@upa.edu.py"},
    )
    assert login_resp.status_code == 200
    login_data = login_resp.json()
    _assert_no_null_values(login_data, "dev_login")

    headers = {"Authorization": f"Bearer {login_data['access_token']}"}

    for endpoint in ["/api/auth/me", "/api/news", "/api/events", "/api/v1/app-state"]:
        resp = client.get(endpoint, headers=headers)
        assert resp.status_code == 200, f"{endpoint} failed with {resp.status_code}"
        payload = resp.json()
        _assert_no_null_values(payload, endpoint)


def test_rbac_group_isolation_on_news_events_and_app_state():
    """
    Verifica que un estudiante regular (grupos=['TIE']) no pueda ver ni acceder
    a noticias o eventos exclusivos de docentes ('PROF') o administracion ('ADMIN').
    """
    db = TestingSessionLocal()
    student = User(
        id=50,
        email="alumno.tie@upa.edu.py",
        full_name="Alumno TIE",
        role="user",
        groups=["TIE"],
    )
    prof_post = Post(
        id=500,
        title="Reunion Exclusiva de Claustro Docente",
        content="Solo para profesores",
        post_type="MANUAL",
        is_news=True,
        is_event=True,
        event_start=datetime.now(UTC) + timedelta(days=3),
        target_groups=["PROF"],
    )
    db.add_all([student, prof_post])
    db.commit()
    db.close()

    student_token = create_access_token(
        {"sub": "50", "email": "alumno.tie@upa.edu.py", "role": "user"}
    )
    student_headers = {"Authorization": f"Bearer {student_token}"}

    # 1. El estudiante no recibe el post exclusivo de PROF en /api/news ni forzando ?group=PROF
    news_resp = client.get("/api/news", headers=student_headers)
    assert news_resp.status_code == 200
    news_titles = [n["title"] for n in news_resp.json()]
    assert "Reunion Exclusiva de Claustro Docente" not in news_titles

    news_forced = client.get("/api/news?group=PROF", headers=student_headers)
    assert news_forced.status_code == 200
    assert "Reunion Exclusiva de Claustro Docente" not in [n["title"] for n in news_forced.json()]

    # 2. Acceso directo por ID a noticia o evento restringido retorna 403 Forbidden
    news_detail_forbidden = client.get("/api/news/500", headers=student_headers)
    assert news_detail_forbidden.status_code == 403

    event_detail_forbidden = client.get("/api/events/500", headers=student_headers)
    assert event_detail_forbidden.status_code == 403

    # 3. En cambio, un administrador tiene acceso completo (200 OK)
    admin_token = create_access_token(
        {"sub": "1", "email": "test@upa.edu.py", "role": "admin"}
    )
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    admin_detail = client.get("/api/news/500", headers=admin_headers)
    assert admin_detail.status_code == 200
    assert admin_detail.json()["title"] == "Reunion Exclusiva de Claustro Docente"

    # 4. Un cliente no autenticado en /api/v1/app-state solo recibe posts de INSTAGRAM publicos
    unauth_state = client.get("/api/v1/app-state")
    assert unauth_state.status_code == 200
    unauth_data = unauth_state.json()
    assert unauth_data["authenticated"] is False
    assert unauth_data["user"] is None
    assert all(item["post_type"] == "INSTAGRAM" for item in unauth_data["feed"])


def test_not_found_404_and_bad_request_400_errors():
    admin_token = create_access_token(
        {"sub": "1", "email": "test@upa.edu.py", "role": "admin"}
    )
    headers = {"Authorization": f"Bearer {admin_token}"}

    # 404 en noticia y evento inexistentes
    assert client.get("/api/news/999999", headers=headers).status_code == 404
    assert client.get("/api/events/999999", headers=headers).status_code == 404

    # 400 en creacion de noticia con titulo vacio
    bad_title = client.post(
        "/api/news",
        json={"title": "   ", "content": "Contenido"},
        headers=headers,
    )
    assert bad_title.status_code == 400

    # 400 en creacion de noticia con post_type invalido
    bad_type = client.post(
        "/api/news",
        json={"title": "Titulo valido", "post_type": "TIPO_INEXISTENTE"},
        headers=headers,
    )
    assert bad_type.status_code == 400

    # 400 cuando event_end es anterior a event_start
    now = datetime.now(UTC)
    bad_dates = client.post(
        "/api/news",
        json={
            "title": "Evento con fechas invertidas",
            "is_event": True,
            "event_start": (now + timedelta(days=2)).isoformat(),
            "event_end": (now + timedelta(days=1)).isoformat(),
        },
        headers=headers,
    )
    assert bad_dates.status_code == 400


def test_openapi_docs_and_integration_guide_completeness():
    from pathlib import Path

    docs_resp = client.get("/docs")
    assert docs_resp.status_code == 200
    assert "Swagger UI" in docs_resp.text or "openapi.json" in docs_resp.text

    openapi_resp = client.get("/openapi.json")
    assert openapi_resp.status_code == 200
    schema = openapi_resp.json()
    paths = schema.get("paths", {})
    for required_path in [
        "/api/auth/dev-login",
        "/api/auth/me",
        "/api/v1/app-state",
        "/api/news",
        "/api/events",
        "/api/classroom/deadlines",
    ]:
        assert required_path in paths, f"Missing {required_path} in OpenAPI spec"

    components = schema.get("components", {}).get("schemas", {})
    for required_model in [
        "DevLoginRequest",
        "AuthResponse",
        "UserResponse",
        "NewsResponse",
        "EventResponse",
        "ClassroomDeadlineResponse",
        "AppStateResponse",
    ]:
        assert required_model in components, f"Missing {required_model} in OpenAPI schemas"

    guide_path = Path(__file__).resolve().parent.parent.parent / "docs" / "FRONTEND_INTEGRATION_GUIDE.md"
    assert guide_path.exists()
    guide_text = guide_path.read_text(encoding="utf-8")
    assert "POST /api/auth/dev-login" in guide_text
    assert "Authorization: Bearer" in guide_text
    assert "/api/v1/app-state" in guide_text
    assert "/api/classroom/deadlines" in guide_text

