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


def test_event_rsvp_register_unregister_idempotency_and_errors():
    db = TestingSessionLocal()
    student1 = User(
        id=61,
        email="alumno1.tie@upa.edu.py",
        full_name="Alumno Uno",
        role="user",
        groups=["TIE"],
    )
    student2 = User(
        id=62,
        email="alumno2.tie@upa.edu.py",
        full_name="Alumno Dos",
        role="user",
        groups=["TIE"],
    )
    outsider = User(
        id=63,
        email="externo.admin@upa.edu.py",
        full_name="Alumno Otra Carrera",
        role="user",
        groups=["MECA"],
    )
    prof_event = Post(
        id=700,
        title="Seminario Exclusivo TIE",
        content="Solo para estudiantes de TIE",
        post_type="MANUAL",
        is_news=False,
        is_event=True,
        event_start=datetime.now(UTC) + timedelta(days=2),
        has_registration=True,
        target_groups=["TIE"],
    )
    db.add_all([student1, student2, outsider, prof_event])
    db.commit()
    db.close()

    h1 = {"Authorization": f"Bearer {create_access_token({'sub': '61', 'email': 'alumno1.tie@upa.edu.py', 'role': 'user'})}"}
    h2 = {"Authorization": f"Bearer {create_access_token({'sub': '62', 'email': 'alumno2.tie@upa.edu.py', 'role': 'user'})}"}
    h_out = {"Authorization": f"Bearer {create_access_token({'sub': '63', 'email': 'externo.admin@upa.edu.py', 'role': 'user'})}"}

    # 1. Estado inicial antes de inscripcion
    init_detail = client.get("/api/events/700", headers=h1)
    assert init_detail.status_code == 200
    assert init_detail.json()["is_registered"] is False
    assert init_detail.json()["registered_count"] == 0

    # 2. Alumno 1 se inscribe (POST /api/events/700/register)
    reg1 = client.post("/api/events/700/register", headers=h1)
    assert reg1.status_code == 200
    assert reg1.json()["is_registered"] is True
    assert reg1.json()["registered_count"] == 1

    # 3. Idempotencia: Alumno 1 vuelve a inscribirse -> sigue en 1
    reg1_dup = client.post("/api/events/700/register", headers=h1)
    assert reg1_dup.status_code == 200
    assert reg1_dup.json()["is_registered"] is True
    assert reg1_dup.json()["registered_count"] == 1

    # 4. Alumno 2 se inscribe -> registered_count sube a 2
    reg2 = client.post("/api/events/700/register", headers=h2)
    assert reg2.status_code == 200
    assert reg2.json()["is_registered"] is True
    assert reg2.json()["registered_count"] == 2

    # 5. Alumno 1 cancela su inscripcion (DELETE /api/events/700/register)
    unreg1 = client.delete("/api/events/700/register", headers=h1)
    assert unreg1.status_code == 200
    assert unreg1.json()["is_registered"] is False
    assert unreg1.json()["registered_count"] == 1

    # 6. Idempotencia en DELETE: cancelar de nuevo mantiene 200 OK y contador en 1
    unreg1_dup = client.delete("/api/events/700/register", headers=h1)
    assert unreg1_dup.status_code == 200
    assert unreg1_dup.json()["is_registered"] is False
    assert unreg1_dup.json()["registered_count"] == 1

    # 7. Errores de autenticacion (401), autorizacion (403) y recurso inexistente (404)
    assert client.post("/api/events/700/register").status_code == 401
    assert client.delete("/api/events/700/register").status_code == 401
    assert client.post("/api/events/700/register", headers=h_out).status_code == 403
    assert client.delete("/api/events/700/register", headers=h_out).status_code == 403
    assert client.post("/api/events/999999/register", headers=h1).status_code == 404
    assert client.delete("/api/events/999999/register", headers=h1).status_code == 404
    # Post 1 es noticia pero NO es evento (is_event=False) -> 404 en /api/events/1/register
    assert client.post("/api/events/1/register", headers=h1).status_code == 404


def test_admin_crud_update_and_delete_news_and_events():
    db = TestingSessionLocal()
    student = User(
        id=75,
        email="estudiante.regular@upa.edu.py",
        full_name="Estudiante Regular",
        role="user",
        groups=["TIE"],
    )
    db.add(student)
    db.commit()
    db.close()

    admin_headers = {
        "Authorization": f"Bearer {create_access_token({'sub': '1', 'email': 'test@upa.edu.py', 'role': 'admin'})}"
    }
    student_headers = {
        "Authorization": f"Bearer {create_access_token({'sub': '75', 'email': 'estudiante.regular@upa.edu.py', 'role': 'user'})}"
    }

    # 1. Estudiante regular recibe 403 en PUT/DELETE de noticias y eventos
    assert client.put("/api/news/1", json={"title": "Intento Hack"}, headers=student_headers).status_code == 403
    assert client.delete("/api/news/1", headers=student_headers).status_code == 403
    assert client.put("/api/events/2", json={"title": "Intento Hack"}, headers=student_headers).status_code == 403
    assert client.delete("/api/events/2", headers=student_headers).status_code == 403

    # 2. Peticiones sin token reciben 401
    assert client.put("/api/news/1", json={"title": "Sin Token"}).status_code == 401
    assert client.delete("/api/news/1").status_code == 401
    assert client.put("/api/events/2", json={"title": "Sin Token"}).status_code == 401
    assert client.delete("/api/events/2").status_code == 401

    # 3. Admin actualiza noticia (PUT /api/news/1)
    upd_news = client.put(
        "/api/news/1",
        json={
            "title": "Busqueda Laboral: Recepcionista Bilingue Actualizada",
            "caption": "Convocatoria extendida hasta viernes",
            "content": "Requisitos actualizados para recepcion.",
            "is_pinned": True,
        },
        headers=admin_headers,
    )
    assert upd_news.status_code == 200
    news_data = upd_news.json()
    assert news_data["id"] == 1
    assert news_data["title"] == "Busqueda Laboral: Recepcionista Bilingue Actualizada"
    assert news_data["summary"] == "Convocatoria extendida hasta viernes"
    assert news_data["is_pinned"] is True

    # 4. Validaciones 400 y 404 en PUT/DELETE de noticias
    assert client.put("/api/news/1", json={"title": "   "}, headers=admin_headers).status_code == 400
    assert client.put("/api/news/1", json={"post_type": "INVALIDO"}, headers=admin_headers).status_code == 400
    assert client.put("/api/news/999999", json={"title": "No Existe"}, headers=admin_headers).status_code == 404
    assert client.delete("/api/news/999999", headers=admin_headers).status_code == 404

    # 5. Admin actualiza evento (PUT /api/events/2)
    now = datetime.now(UTC)
    new_start = (now + timedelta(days=4)).isoformat()
    new_end = (now + timedelta(days=4, hours=2)).isoformat()
    upd_ev = client.put(
        "/api/events/2",
        json={
            "title": "Simposio IA y Etica Profesional",
            "description": "Nueva descripcion extendida del simposio",
            "location": "Aula Magna Edificio Central",
            "event_start": new_start,
            "event_end": new_end,
            "has_registration": True,
        },
        headers=admin_headers,
    )
    assert upd_ev.status_code == 200
    ev_data = upd_ev.json()
    assert ev_data["id"] == 2
    assert ev_data["title"] == "Simposio IA y Etica Profesional"
    assert ev_data["description"] == "Nueva descripcion extendida del simposio"
    assert ev_data["location"] == "Aula Magna Edificio Central"

    # 6. Validaciones 400 y 404 en PUT/DELETE de eventos
    assert client.put("/api/events/2", json={"title": "  "}, headers=admin_headers).status_code == 400
    bad_ev_dates = client.put(
        "/api/events/2",
        json={
            "event_start": (now + timedelta(days=5)).isoformat(),
            "event_end": (now + timedelta(days=4)).isoformat(),
        },
        headers=admin_headers,
    )
    assert bad_ev_dates.status_code == 400
    assert client.put("/api/events/999999", json={"title": "No Existe"}, headers=admin_headers).status_code == 404
    assert client.delete("/api/events/999999", headers=admin_headers).status_code == 404

    # 7. Admin elimina noticia y evento (DELETE /api/news/1 y DELETE /api/events/2)
    del_news = client.delete("/api/news/1", headers=admin_headers)
    assert del_news.status_code == 200
    assert del_news.json()["status"] == "deleted"
    assert del_news.json()["id"] == 1
    assert client.get("/api/news/1", headers=admin_headers).status_code == 404

    del_ev = client.delete("/api/events/2", headers=admin_headers)
    assert del_ev.status_code == 200
    assert del_ev.json()["status"] == "deleted"
    assert del_ev.json()["id"] == 2
    assert client.get("/api/events/2", headers=admin_headers).status_code == 404


def test_device_token_registration_persistence_and_validation():
    admin_headers = {
        "Authorization": f"Bearer {create_access_token({'sub': '1', 'email': 'test@upa.edu.py', 'role': 'admin'})}"
    }

    # 1. Sin autenticacion -> 401
    assert client.post("/api/users/device-token", json={"device_token": "fcm_valid_token_12345"}).status_code == 401

    # 2. Registro valido e idempotente
    resp1 = client.post(
        "/api/users/device-token",
        json={
            "device_token": "fcm_android_token_9876543210abcdef",
            "platform": "android",
        },
        headers=admin_headers,
    )
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["user_id"] == 1
    assert data1["device_token"] == "fcm_android_token_9876543210abcdef"
    assert data1["platform"] == "android"
    assert data1["has_device_token"] is True
    assert "updated_at" in data1

    # Repetir registro con el mismo token actualiza sin duplicar
    resp2 = client.post(
        "/api/users/device-token",
        json={
            "device_token": "fcm_android_token_9876543210abcdef",
            "platform": "android",
        },
        headers=admin_headers,
    )
    assert resp2.status_code == 200
    assert resp2.json()["device_token"] == "fcm_android_token_9876543210abcdef"

    # Verificar persistencia en base de datos
    db = TestingSessionLocal()
    u = db.query(User).filter(User.id == 1).first()
    assert u.device_token == "fcm_android_token_9876543210abcdef"
    assert len(u.device_tokens) == 1
    db.close()

    # 3. Validaciones de error 400 (token vacio, muy corto, con espacios o plataforma invalida)
    for bad_token in ["", "   ", "corto", "token con espacios 123456"]:
        r_bad = client.post(
            "/api/users/device-token",
            json={"device_token": bad_token, "platform": "android"},
            headers=admin_headers,
        )
        assert r_bad.status_code == 400

    r_bad_plat = client.post(
        "/api/users/device-token",
        json={"device_token": "fcm_android_token_9876543210abcdef", "platform": "symbian"},
        headers=admin_headers,
    )
    assert r_bad_plat.status_code == 400


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
        "/api/v1/agenda",
        "/api/news",
        "/api/news/{post_id}",
        "/api/events",
        "/api/events/{event_id}",
        "/api/events/{event_id}/register",
        "/api/users/device-token",
        "/api/classroom/deadlines",
    ]:
        assert required_path in paths, f"Missing {required_path} in OpenAPI spec"

    assert "post" in paths["/api/events/{event_id}/register"]
    assert "delete" in paths["/api/events/{event_id}/register"]
    assert "put" in paths["/api/news/{post_id}"]
    assert "delete" in paths["/api/news/{post_id}"]
    assert "put" in paths["/api/events/{event_id}"]
    assert "delete" in paths["/api/events/{event_id}"]

    components = schema.get("components", {}).get("schemas", {})
    for required_model in [
        "DevLoginRequest",
        "AuthResponse",
        "UserResponse",
        "NewsResponse",
        "EventResponse",
        "EventUpdate",
        "PostUpdate",
        "DeleteResponse",
        "DeviceTokenRequest",
        "DeviceTokenResponse",
        "ClassroomDeadlineResponse",
        "AppStateResponse",
        "AgendaResponse",
    ]:
        assert required_model in components, f"Missing {required_model} in OpenAPI schemas"

    guide_path = Path(__file__).resolve().parent.parent.parent / "docs" / "FRONTEND_INTEGRATION_GUIDE.md"
    assert guide_path.exists()
    guide_text = guide_path.read_text(encoding="utf-8")
    for expected_snippet in [
        "POST /api/auth/dev-login",
        "Authorization: Bearer",
        "/api/v1/app-state",
        "/api/v1/agenda",
        "/api/events/{event_id}/register",
        "/api/users/device-token",
        "PUT /api/news/{post_id}",
        "DELETE /api/news/{post_id}",
        "PUT /api/events/{event_id}",
        "DELETE /api/events/{event_id}",
        "classroom_refresh_token",
        "/api/classroom/deadlines",
    ]:
        assert expected_snippet in guide_text, f"Missing {expected_snippet} in FRONTEND_INTEGRATION_GUIDE.md"


