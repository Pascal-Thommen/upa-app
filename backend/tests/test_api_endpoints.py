from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from src.auth import create_access_token
from src.database import Base, get_db
from src.main import app
from src.models import DeviceToken, Post, User

# SQLite In-Memory Engine mit StaticPool für gemeinsamen Speicher aller Connections
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
        author_id=user.id,
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
        author_id=user.id,
    )
    db.add(event)
    db.commit()

    yield
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.pop(get_db, None)


def test_get_publications_endpoint_requires_auth():
    # Ohne Authentifizierung -> 401
    response = client.get("/api/publications")
    assert response.status_code == 401

    # Mit gültigem Token -> 200
    token = create_access_token({"sub": "1", "email": "test@upa.edu.py", "role": "admin"})
    response_auth = client.get("/api/publications", headers={"Authorization": f"Bearer {token}"})
    assert response_auth.status_code == 200
    data = response_auth.json()
    assert len(data) == 2
    assert data[0]["is_pinned"] is True
    assert data[0]["title"] == "¿Qué significa seguir siendo humanos en la era de la IA?"
    assert data[1]["title"] == "Búsqueda Laboral: Recepcionista"


def test_get_agenda_events():
    token = create_access_token({"sub": "1", "email": "test@upa.edu.py", "role": "admin"})
    response_auth = client.get("/api/v1/agenda", headers={"Authorization": f"Bearer {token}"})
    assert response_auth.status_code == 200
    data = response_auth.json()["events"]
    assert len(data) == 1
    assert data[0]["title"] == "¿Qué significa seguir siendo humanos en la era de la IA?"
    assert data[0]["location"] == "Auditorio Edificio 1"
    assert data[0]["has_registration"] is True


def test_filter_by_group():
    token = create_access_token({"sub": "1", "email": "test@upa.edu.py", "role": "admin"})
    response = client.get("/api/v1/feed?group=TIE", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()["posts"]
    assert len(data) == 2


def _assert_no_null_values(obj, path="root", nullable_keys=frozenset({"event_end"})):
    """Verifica recursivamente que ningun campo de un payload JSON sea None (salvo campos explicitamente opcionales)."""
    assert obj is not None, f"Null value found at {path}"
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in nullable_keys and v is None:
                continue
            _assert_no_null_values(v, f"{path}.{k}", nullable_keys)
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            _assert_no_null_values(item, f"{path}[{idx}]", nullable_keys)


def test_anti_conflict_audit_no_null_values_across_endpoints():
    """
    Inserta registros con columnas opcionales en None y verifica que
    /api/auth/me y /api/v1/agenda entreguen objetos JSON completos sin ningun valor null.
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
    pascal = User(
        email="pascal.thommen@upa.edu.py",
        full_name="Pascal Thommen",
        role="admin",
        groups=["ALL", "Semester_4", "TIE"],
    )
    db.add(pascal)
    db.add(sparse_post)
    db.commit()
    db.refresh(pascal)
    pascal_id = pascal.id
    db.close()

    token = create_access_token({"sub": str(pascal_id), "email": "pascal.thommen@upa.edu.py", "role": "admin"})
    headers = {"Authorization": f"Bearer {token}"}

    for endpoint in ["/api/auth/me", "/api/v1/agenda"]:
        resp = client.get(endpoint, headers=headers)
        assert resp.status_code == 200, f"{endpoint} failed with {resp.status_code}"
        payload = resp.json()
        _assert_no_null_values(payload, endpoint)


def test_rbac_group_isolation_on_feed_agenda_and_publications():
    """
    Verifica que un estudiante regular (grupos=['TIE']) no pueda ver ni acceder
    a noticias o eventos exclusivos de docentes ('PROF').
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

    student_token = create_access_token({"sub": "50", "email": "alumno.tie@upa.edu.py", "role": "user"})
    student_headers = {"Authorization": f"Bearer {student_token}"}

    # 1. El estudiante no recibe el post exclusivo de PROF en /api/v1/feed ni forzando ?group=PROF
    feed_resp = client.get("/api/v1/feed", headers=student_headers)
    assert feed_resp.status_code == 200
    feed_titles = [n["title"] for n in feed_resp.json()["posts"]]
    assert "Reunion Exclusiva de Claustro Docente" not in feed_titles

    feed_forced = client.get("/api/v1/feed?group=PROF", headers=student_headers)
    assert feed_forced.status_code == 200
    assert "Reunion Exclusiva de Claustro Docente" not in [n["title"] for n in feed_forced.json()["posts"]]

    # 2. Acceso directo a vista o registro de publicacion restringida retorna 403 Forbidden
    assert client.post("/api/publications/500/view", headers=student_headers).status_code == 403
    assert client.post("/api/events/500/register", headers=student_headers).status_code == 403

    # 3. En cambio, un administrador tiene acceso completo (200 OK)
    admin_token = create_access_token({"sub": "1", "email": "test@upa.edu.py", "role": "admin"})
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    admin_detail = client.get("/api/publications/500", headers=admin_headers)
    assert admin_detail.status_code == 200
    assert admin_detail.json()["title"] == "Reunion Exclusiva de Claustro Docente"


def test_not_found_404_and_bad_request_400_errors():
    admin_token = create_access_token({"sub": "1", "email": "test@upa.edu.py", "role": "admin"})
    headers = {"Authorization": f"Bearer {admin_token}"}

    # 404 en publicacion inexistente
    assert client.get("/api/publications/999999", headers=headers).status_code == 404

    # 400 en creacion de publicacion con titulo vacio
    bad_title = client.post(
        "/api/publications",
        json={"title": "   ", "content": "Contenido", "is_news": True},
        headers=headers,
    )
    assert bad_title.status_code == 400

    # 400 en creacion de publicacion con post_type invalido
    bad_type = client.post(
        "/api/publications",
        json={"title": "Titulo valido", "post_type": "TIPO_INEXISTENTE", "is_news": True},
        headers=headers,
    )
    assert bad_type.status_code == 400

    # 400 cuando event_end es anterior a event_start
    now = datetime.now(UTC)
    bad_dates = client.post(
        "/api/publications",
        json={
            "title": "Evento con fechas invertidas",
            "is_news": True,
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

    h1 = {
        "Authorization": f"Bearer {create_access_token({'sub': '61', 'email': 'alumno1.tie@upa.edu.py', 'role': 'user'})}"
    }
    h2 = {
        "Authorization": f"Bearer {create_access_token({'sub': '62', 'email': 'alumno2.tie@upa.edu.py', 'role': 'user'})}"
    }
    h_out = {
        "Authorization": f"Bearer {create_access_token({'sub': '63', 'email': 'externo.admin@upa.edu.py', 'role': 'user'})}"
    }

    # 1. Alumno 1 se inscribe (POST /api/events/700/register)
    reg1 = client.post("/api/events/700/register", headers=h1)
    assert reg1.status_code == 200
    assert reg1.json()["is_registered"] is True
    assert reg1.json()["registered_count"] == 1

    # 2. Idempotencia: Alumno 1 vuelve a inscribirse -> sigue en 1
    reg1_dup = client.post("/api/events/700/register", headers=h1)
    assert reg1_dup.status_code == 200
    assert reg1_dup.json()["is_registered"] is True
    assert reg1_dup.json()["registered_count"] == 1

    # 3. Alumno 2 se inscribe -> registered_count sube a 2
    reg2 = client.post("/api/events/700/register", headers=h2)
    assert reg2.status_code == 200
    assert reg2.json()["is_registered"] is True
    assert reg2.json()["registered_count"] == 2

    # 4. Alumno 1 cancela su inscripcion (DELETE /api/events/700/register)
    unreg1 = client.delete("/api/events/700/register", headers=h1)
    assert unreg1.status_code == 200
    assert unreg1.json()["is_registered"] is False
    assert unreg1.json()["registered_count"] == 1

    # 5. Idempotencia en DELETE: cancelar de nuevo mantiene 200 OK y contador en 1
    unreg1_dup = client.delete("/api/events/700/register", headers=h1)
    assert unreg1_dup.status_code == 200
    assert unreg1_dup.json()["is_registered"] is False
    assert unreg1_dup.json()["registered_count"] == 1

    # 6. Errores de autenticacion (401), autorizacion (403) y recurso inexistente (404)
    assert client.post("/api/events/700/register").status_code == 401
    assert client.delete("/api/events/700/register").status_code == 401
    assert client.post("/api/events/700/register", headers=h_out).status_code == 403
    assert client.delete("/api/events/700/register", headers=h_out).status_code == 403
    assert client.post("/api/events/999999/register", headers=h1).status_code == 404
    assert client.delete("/api/events/999999/register", headers=h1).status_code == 404
    # Post 1 es noticia pero NO es evento (is_event=False) -> 404 en /api/events/1/register
    assert client.post("/api/events/1/register", headers=h1).status_code == 404


def test_admin_crud_update_and_delete_publications():
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

    # 1. Estudiante regular recibe 403 en PUT/DELETE de publicaciones
    assert client.put("/api/publications/1", json={"title": "Intento Hack"}, headers=student_headers).status_code == 403
    assert client.delete("/api/publications/1", headers=student_headers).status_code == 403

    # 2. Peticiones sin token reciben 401
    assert client.put("/api/publications/1", json={"title": "Sin Token"}).status_code == 401
    assert client.delete("/api/publications/1").status_code == 401

    # 3. Admin actualiza publicacion (PUT /api/publications/2)
    now = datetime.now(UTC)
    new_start = (now + timedelta(days=4)).isoformat()
    new_end = (now + timedelta(days=4, hours=2)).isoformat()
    exp = (now + timedelta(days=10)).isoformat()
    upd_ev = client.put(
        "/api/publications/2",
        json={
            "title": "Simposio IA y Etica Profesional",
            "content": "Nueva descripcion extendida del simposio",
            "location": "Aula Magna Edificio Central",
            "event_start": new_start,
            "event_end": new_end,
            "expires_at": exp,
            "has_registration": True,
        },
        headers=admin_headers,
    )
    assert upd_ev.status_code == 200
    ev_data = upd_ev.json()
    assert ev_data["id"] == 2
    assert ev_data["title"] == "Simposio IA y Etica Profesional"
    assert ev_data["content"] == "Nueva descripcion extendida del simposio"
    assert ev_data["location"] == "Aula Magna Edificio Central"

    # 4. Validaciones 400 y 404 en PUT/DELETE de publicaciones
    assert client.put("/api/publications/1", json={"title": "   "}, headers=admin_headers).status_code == 400
    assert client.put("/api/publications/999999", json={"title": "No Existe"}, headers=admin_headers).status_code == 404
    assert client.delete("/api/publications/999999", headers=admin_headers).status_code == 404

    # 5. Admin elimina publicaciones
    del_news = client.delete("/api/publications/1", headers=admin_headers)
    assert del_news.status_code == 200
    assert del_news.json()["status"] == "deleted"
    assert client.get("/api/publications/1", headers=admin_headers).status_code == 404


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

    # Verificar persistencia en la tabla device_tokens (y que users.device_token ya no existe)
    db = TestingSessionLocal()
    u = db.query(User).filter(User.id == 1).first()
    assert not hasattr(u, "device_token")
    rows = db.query(DeviceToken).filter(DeviceToken.user_id == 1).all()
    assert len(rows) == 1
    assert rows[0].device_token == "fcm_android_token_9876543210abcdef"
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
    for removed_path in [
        "/api/auth/dev-login",
        "/api/auth/groups",
        "/api/users/me",
        "/api/v1/app-state",
        "/api/v1/feed/sync",
        "/api/news",
        "/api/news/{post_id}",
        "/api/events",
        "/api/events/{event_id}",
        "/api/events/{event_id}/registrations",
    ]:
        assert removed_path not in paths

    for required_path in [
        "/api/auth/google",
        "/api/auth/me",
        "/api/v1/feed",
        "/api/v1/agenda",
        "/api/publications",
        "/api/publications/{publication_id}",
        "/api/publications/sync-instagram",
        "/api/events/{event_id}/register",
        "/api/users/device-token",
        "/api/classroom/deadlines",
    ]:
        assert required_path in paths, f"Missing {required_path} in OpenAPI spec"

    assert "post" in paths["/api/events/{event_id}/register"]
    assert "delete" in paths["/api/events/{event_id}/register"]

    components = schema.get("components", {}).get("schemas", {})
    for removed_model in [
        "DevLoginRequest",
        "PostBase",
        "PostCreate",
        "PostUpdate",
        "NewsResponse",
        "EventCreate",
        "EventUpdate",
        "EventRegistrationsResponse",
        "AppStateFeedItem",
        "AppStateUser",
        "AppStateResponse",
    ]:
        assert removed_model not in components

    for required_model in [
        "GoogleLoginRequest",
        "AuthResponse",
        "UserResponse",
        "PublicationWrite",
        "PublicationUpdate",
        "PublicationResponse",
        "EventResponse",
        "DeleteResponse",
        "DeviceTokenRequest",
        "DeviceTokenResponse",
        "ClassroomDeadlineResponse",
        "AgendaResponse",
    ]:
        assert required_model in components, f"Missing {required_model} in OpenAPI schemas"

    guide_path = Path(__file__).resolve().parent.parent.parent / "docs" / "FRONTEND_INTEGRATION_GUIDE.md"
    assert guide_path.exists()
    guide_text = guide_path.read_text(encoding="utf-8")
    assert "POST /api/auth/dev-login" not in guide_text
    for expected_snippet in [
        "POST /api/auth/google",
        "Authorization: Bearer",
        "/api/v1/agenda",
        "/api/events/{event_id}/register",
        "/api/users/device-token",
        "classroom_refresh_token",
        "/api/classroom/deadlines",
        "manifest.webmanifest",
        "/sw.js",
        "/api/publications/autocomplete-ai",
        "/api/ai/config",
    ]:
        assert expected_snippet in guide_text, f"Missing {expected_snippet} in FRONTEND_INTEGRATION_GUIDE.md"


def test_pwa_and_ai_documentation_integrity():
    import re
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent.parent
    md_files = [
        repo_root / "README.md",
        repo_root / "AGENTS.md",
        repo_root / "web-app" / "README.md",
        repo_root / "web-admin" / "README.md",
        repo_root / "docs" / "FRONTEND_INTEGRATION_GUIDE.md",
        repo_root / "docs" / "api_documentation.md",
        repo_root / "docs" / "decisiones_arquitectonicas.md",
        repo_root / "docs" / "functional_spec.md",
        repo_root / "docs" / "especificacion_funcional.md",
        repo_root / "docs" / "google_cloud_setup.md",
        repo_root / "docs" / "LOGBOOK.md",
        repo_root / "docs" / "DATABASE_CLEANUP_AUDIT.md",
    ]

    link_pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")

    for md_path in md_files:
        assert md_path.is_file(), f"Missing markdown file: {md_path}"
        content = md_path.read_text(encoding="utf-8")
        assert content.strip(), f"Empty markdown file: {md_path}"
        if md_path.name != "DATABASE_CLEANUP_AUDIT.md":
            assert "\u2013" not in content, f"En-dash found in {md_path.name}"
            assert "\u2014" not in content, f"Em-dash found in {md_path.name}"
        assert "descartando la alternativa de Progressive Web App" not in content

        for raw_target in link_pattern.findall(content):
            target = raw_target.strip().split("#")[0]
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            resolved = (md_path.parent / target).resolve()
            assert resolved.exists(), f"Broken link '{raw_target}' in {md_path}"

    readme_text = (repo_root / "README.md").read_text(encoding="utf-8")
    for snippet in ("PWA", "web-app/", "TWA", "Autocompletar con IA", "docs/api_documentation.md"):
        assert snippet in readme_text

    api_doc_text = (repo_root / "docs" / "api_documentation.md").read_text(encoding="utf-8")
    for snippet in (
        "Nginx",
        "Acceso Administrativo",
        "/sw.js",
        "/manifest.webmanifest",
        "/api/publications/autocomplete-ai",
        "/api/ai/config",
        "/api/ai/test-connection",
    ):
        assert snippet in api_doc_text
