"""Pruebas integrales del modelo unificado de Publicaciones, RSVP, Vistas, Historial y UX (SRV-160)."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from src.auth import create_access_token
from src.database import Base, get_db
from src.main import app
from src.models import (
    AdminAuditLog,
    AudienceGroup,
    EventRegistration,
    Post,
    PostView,
    User,
    UserRole,
)
from src.services.push import collect_event_reminder_tokens

engine = create_engine(
    "sqlite:///:memory:",
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


def auth(user_id: int, email: str, role: str) -> dict[str, str]:
    token = create_access_token({"sub": str(user_id), "email": email, "role": role})
    return {"Authorization": f"Bearer {token}"}


ADMIN_ID = 1
ADMIN_EMAIL = "pascal.thommen@upa.edu.py"
EDITOR_ID = 2
EDITOR_EMAIL = "redaccion@upa.edu.py"
STUDENT_A_ID = 3
STUDENT_A_EMAIL = "ana.estudiante@upa.edu.py"
STUDENT_B_ID = 4
STUDENT_B_EMAIL = "luis.estudiante@upa.edu.py"


@pytest.fixture(autouse=True)
def setup_database():
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    db.query(AdminAuditLog).delete()
    db.query(PostView).delete()
    db.query(EventRegistration).delete()
    db.query(Post).delete()
    db.query(AudienceGroup).delete()
    db.query(UserRole).delete()
    db.query(User).delete()

    db.add_all(
        [
            User(id=ADMIN_ID, email=ADMIN_EMAIL, full_name="Pascal Thommen", role="admin", groups=["ALL"]),
            User(id=EDITOR_ID, email=EDITOR_EMAIL, full_name="Equipo Redacción", role="editor", groups=["ALL"]),
            User(
                id=STUDENT_A_ID,
                email=STUDENT_A_EMAIL,
                full_name="Ana Estudiante",
                role="user",
                groups=["ALL", "TIE"],
                device_token="fcm-token-ana-real",
            ),
            User(
                id=STUDENT_B_ID,
                email=STUDENT_B_EMAIL,
                full_name="Luis Estudiante",
                role="user",
                groups=["ALL", "TIE"],
                device_token="fcm-token-luis-real",
            ),
            UserRole(
                id=1,
                email=ADMIN_EMAIL,
                name="Pascal Thommen",
                role="admin",
                permissions=["publicaciones", "grupos", "roles", "apis"],
                is_primary=True,
            ),
            UserRole(
                id=2,
                email=EDITOR_EMAIL,
                name="Equipo Redacción",
                role="editor",
                permissions=["publicaciones"],
                is_primary=False,
            ),
        ]
    )
    db.commit()
    db.close()
    yield
    app.dependency_overrides.clear()


def test_unified_publication_news_event_and_hybrid_lifecycle():
    headers = auth(EDITOR_ID, EDITOR_EMAIL, "editor")
    future_start = (datetime.now(UTC) + timedelta(days=3)).isoformat()
    future_end = (datetime.now(UTC) + timedelta(days=3, hours=2)).isoformat()

    # 1. Publicación híbrida (Noticia + Evento simultáneamente)
    res = client.post(
        "/api/publications",
        json={
            "title": "Foro de Innovación UPA 2026",
            "post_type": "MANUAL",
            "has_registration": True,
            "target_groups": ["ALL", "TIE"],
            "is_news": True,
            "notify_groups": ["TIE"],
            "caption": "Abierta la inscripción para el foro anual",
            "content": "Desarrollo principal del foro con invitados internacionales.",
            "detail_text": "Traer credencial estudiantil para acreditación.",
            "link_label": "Programa completo",
            "link_url": "https://upa.edu.py/foro",
            "category": "VERANSTALTUNG",
            "is_event": True,
            "event_start": future_start,
            "event_end": future_end,
            "location": "Auditorio Central",
            "event_notify_groups": ["TIE"],
            "reminders": [15, 1440],
        },
        headers=headers,
    )
    assert res.status_code == 201
    pub = res.json()
    assert pub["is_news"] is True
    assert pub["is_event"] is True
    assert pub["has_registration"] is True
    assert pub["detail_text"] == "Traer credencial estudiantil para acreditación."
    assert pub["link_label"] == "Programa completo"
    assert pub["link_url"] == "https://upa.edu.py/foro"
    assert pub["notify_groups"] == ["TIE"]
    assert pub["event_notify_groups"] == ["TIE"]
    assert pub["reminders"] == [15, 1440]
    assert pub["is_edited"] is True
    assert pub["published_at"] is not None

    # Aparece tanto en Noticias como en Eventos para los estudiantes
    student_headers = auth(STUDENT_A_ID, STUDENT_A_EMAIL, "user")
    news_ids = [n["id"] for n in client.get("/api/news", headers=student_headers).json()]
    event_ids = [e["id"] for e in client.get("/api/events", headers=student_headers).json()]
    assert pub["id"] in news_ids
    assert pub["id"] in event_ids

    # 2. Permitir quitar todos los recordatorios dejando lista vacía []
    upd = client.put(
        f"/api/publications/{pub['id']}",
        json={"reminders": []},
        headers=headers,
    )
    assert upd.status_code == 200
    assert upd.json()["reminders"] == []


def test_publication_rejects_empty_sections_and_urgent_with_event():
    headers = auth(ADMIN_ID, ADMIN_EMAIL, "admin")
    future_start = (datetime.now(UTC) + timedelta(days=1)).isoformat()

    no_section = client.post(
        "/api/publications",
        json={
            "title": "Sin sección activa",
            "is_news": False,
            "is_event": False,
            "target_groups": ["ALL"],
        },
        headers=headers,
    )
    assert no_section.status_code == 400
    assert "Noticia o Evento" in no_section.json()["detail"]

    urgent_event = client.post(
        "/api/publications",
        json={
            "title": "Aviso urgente inválido",
            "post_type": "EMERGENCY_BANNER",
            "is_news": True,
            "is_event": True,
            "event_start": future_start,
            "target_groups": ["ALL"],
        },
        headers=headers,
    )
    assert urgent_event.status_code == 400
    assert "avisos urgentes" in urgent_event.json()["detail"].lower()


def test_instagram_publication_locks_type_and_date_and_flips_is_edited():
    orig_ts = datetime(2026, 5, 10, 14, 0, tzinfo=UTC)
    db = TestingSessionLocal()
    ig_post = Post(
        instagram_id="ig_999111",
        title="Becas DAAD",
        caption="Becas abiertas",
        content="Becas abiertas para intercambio en Alemania.",
        post_type="INSTAGRAM",
        is_news=True,
        is_event=False,
        is_edited=False,
        published_at=orig_ts,
        permalink="https://www.instagram.com/p/Cxyz123/",
        target_groups=["ALL"],
    )
    db.add(ig_post)
    db.commit()
    ig_id = ig_post.id
    db.close()

    headers = auth(EDITOR_ID, EDITOR_EMAIL, "editor")
    fetched = client.get(f"/api/publications/{ig_id}", headers=headers)
    assert fetched.status_code == 200
    initial = fetched.json()
    assert initial["is_edited"] is False
    assert initial["link_url"] == "https://www.instagram.com/p/Cxyz123/"

    # Intentar cambiar post_type o desactivar is_news en un post de Instagram es rechazado con 400
    future_start = (datetime.now(UTC) + timedelta(days=5)).isoformat()
    assert (
        client.put(
            f"/api/publications/{ig_id}",
            json={"post_type": "MANUAL"},
            headers=headers,
        ).status_code
        == 400
    )
    assert (
        client.put(
            f"/api/publications/{ig_id}",
            json={"is_news": False, "is_event": True, "event_start": future_start},
            headers=headers,
        ).status_code
        == 400
    )

    # Editar contenido, activar Evento e intentar sobreescribir published_at:
    # mantiene tipo INSTAGRAM y fecha original, activa Evento y marca is_edited=True
    edited = client.put(
        f"/api/publications/{ig_id}",
        json={
            "title": "Charla informativa Becas DAAD",
            "post_type": "INSTAGRAM",
            "published_at": future_start,
            "is_news": True,
            "is_event": True,
            "event_start": future_start,
            "location": "Sala de Conferencias",
            "detail_text": "Requisitos e inscripción presencial.",
        },
        headers=headers,
    )
    assert edited.status_code == 200
    body = edited.json()
    assert body["post_type"] == "INSTAGRAM"
    assert body["is_news"] is True
    assert body["is_event"] is True
    assert body["is_edited"] is True
    assert body["reminders"] == [30]
    assert datetime.fromisoformat(body["published_at"]).replace(tzinfo=UTC) == orig_ts


def test_scheduled_publication_hidden_from_students_until_publish_time():
    headers = auth(ADMIN_ID, ADMIN_EMAIL, "admin")
    student_headers = auth(STUDENT_A_ID, STUDENT_A_EMAIL, "user")
    in_two_hours = (datetime.now(UTC) + timedelta(hours=2)).isoformat()

    created = client.post(
        "/api/publications",
        json={
            "title": "Comunicado programado",
            "is_news": True,
            "is_event": False,
            "published_at": in_two_hours,
            "target_groups": ["ALL"],
        },
        headers=headers,
    )
    assert created.status_code == 201
    pub_id = created.json()["id"]

    # Oculto en el feed público y estudiantil mientras la fecha esté en el futuro
    assert pub_id not in [n["id"] for n in client.get("/api/news", headers=student_headers).json()]
    assert pub_id not in [p["id"] for p in client.get("/api/v1/feed").json()["posts"]]

    # Visible para redacción en la lista administrativa
    admin_list = client.get("/api/publications?include_scheduled=true", headers=headers).json()
    assert any(p["id"] == pub_id for p in admin_list)

    # Cambiar a "Al guardar" (published_at=None) lo publica de inmediato
    publish_now = client.put(
        f"/api/publications/{pub_id}",
        json={"published_at": None},
        headers=headers,
    )
    assert publish_now.status_code == 200
    assert pub_id in [n["id"] for n in client.get("/api/news", headers=student_headers).json()]


def test_rsvp_works_on_posts_and_events_and_excludes_declined_from_reminders():
    headers = auth(ADMIN_ID, ADMIN_EMAIL, "admin")
    ana_headers = auth(STUDENT_A_ID, STUDENT_A_EMAIL, "user")
    luis_headers = auth(STUDENT_B_ID, STUDENT_B_EMAIL, "user")

    # Crear publicación tipo Noticia pura con RSVP habilitado
    post_res = client.post(
        "/api/publications",
        json={
            "title": "Encuesta de transporte universitario",
            "is_news": True,
            "is_event": False,
            "has_registration": True,
            "target_groups": ["ALL"],
        },
        headers=headers,
    )
    assert post_res.status_code == 201
    pub_id = post_res.json()["id"]

    # Ana confirma asistencia, Luis confirma y luego se da de baja
    r1 = client.post(f"/api/publications/{pub_id}/rsvp", json={"status": "attending"}, headers=ana_headers)
    assert r1.status_code == 200
    assert r1.json()["attending_count"] == 1

    r2 = client.post(f"/api/publications/{pub_id}/rsvp", json={"status": "attending"}, headers=luis_headers)
    assert r2.status_code == 200
    assert r2.json()["attending_count"] == 2

    r3 = client.post(f"/api/publications/{pub_id}/rsvp", json={"status": "declined"}, headers=luis_headers)
    assert r3.status_code == 200
    assert r3.json()["attending_count"] == 1
    assert r3.json()["declined_count"] == 1

    regs = client.get(f"/api/publications/{pub_id}/registrations", headers=headers).json()
    assert regs["attending_count"] == 1
    assert regs["declined_count"] == 1

    # Verificar exclusión real de recordatorios push para usuarios con baja ("declined")
    db = TestingSessionLocal()
    tokens = collect_event_reminder_tokens(db, pub_id, ["ALL"])
    db.close()
    assert "fcm-token-ana-real" in tokens
    assert "fcm-token-luis-real" not in tokens


def test_unique_views_tracking_and_admin_only_audit_history():
    admin_headers = auth(ADMIN_ID, ADMIN_EMAIL, "admin")
    editor_headers = auth(EDITOR_ID, EDITOR_EMAIL, "editor")
    ana_headers = auth(STUDENT_A_ID, STUDENT_A_EMAIL, "user")
    luis_headers = auth(STUDENT_B_ID, STUDENT_B_EMAIL, "user")

    created = client.post(
        "/api/publications",
        json={
            "title": "Apertura de biblioteca",
            "is_news": True,
            "is_event": False,
            "target_groups": ["ALL"],
        },
        headers=editor_headers,
    )
    assert created.status_code == 201
    pub_id = created.json()["id"]

    # Ana abre dos veces (cuenta como 1 vista única); Luis abre una vez -> total 2 vistas
    v1 = client.post(f"/api/publications/{pub_id}/view", headers=ana_headers)
    v2 = client.post(f"/api/publications/{pub_id}/view", headers=ana_headers)
    v3 = client.get(f"/api/news/{pub_id}", headers=luis_headers)
    assert v1.status_code == 200 and v1.json()["views_count"] == 1
    assert v2.status_code == 200 and v2.json()["views_count"] == 1
    assert v3.status_code == 200
    detail_admin = client.get(f"/api/publications/{pub_id}", headers=editor_headers)
    assert detail_admin.status_code == 200 and detail_admin.json()["views_count"] == 2

    # Editar título genera entrada detallada en historial
    client.put(
        f"/api/publications/{pub_id}",
        json={"title": "Horario extendido de biblioteca"},
        headers=editor_headers,
    )

    # Historial estrictamente restringido a administradores (403 para editor y estudiante)
    assert client.get("/api/history/post", headers=editor_headers).status_code == 403
    assert client.get(f"/api/history/post/{pub_id}", headers=editor_headers).status_code == 403
    assert client.get("/api/history/post", headers=ana_headers).status_code == 403

    hist_res = client.get(f"/api/history/post/{pub_id}", headers=admin_headers)
    assert hist_res.status_code == 200
    entries = hist_res.json()
    assert len(entries) >= 2
    assert any("título" in e["changes"] for e in entries if e["action"] == "UPDATE_POST")


def test_pinned_publication_requires_expires_at_and_video_media_type_is_inferred():
    headers = auth(EDITOR_ID, EDITOR_EMAIL, "editor")
    future_exp = (datetime.now(UTC) + timedelta(days=7)).isoformat()

    # Fijar sin expires_at falla con 400
    missing_exp = client.post(
        "/api/publications",
        json={
            "title": "Publicación fijada sin vencimiento",
            "is_news": True,
            "is_pinned": True,
            "target_groups": ["ALL"],
        },
        headers=headers,
    )
    assert missing_exp.status_code == 400
    assert "expires_at" in missing_exp.json()["detail"]

    # Fijar con expires_at y video MP4 detecta media_type=VIDEO
    ok_res = client.post(
        "/api/publications",
        json={
            "title": "Resumen audiovisual del campus",
            "is_news": True,
            "is_pinned": True,
            "expires_at": future_exp,
            "media_url": "https://api.upa.edu.py/uploads/campus-resumen.mp4",
            "target_groups": ["ALL"],
        },
        headers=headers,
    )
    assert ok_res.status_code == 201
    created = ok_res.json()
    assert created["is_pinned"] is True
    assert created["expires_at"] is not None
    assert created["media_type"] == "VIDEO"


def test_instagram_publication_locks_synchronized_fields_and_extracts_two_line_teaser():
    orig_ts = datetime(2026, 5, 10, 14, 0, tzinfo=UTC)
    full_ig_caption = (
        "Primera línea del post de Instagram.\n"
        "Segunda línea del resumen automático.\n"
        "Tercera línea con detalles adicionales que solo van en el cuerpo.\n"
        "Cuarta línea con hashtags #UPA #Campus"
    )
    db = TestingSessionLocal()
    ig_post = Post(
        instagram_id="ig_888222",
        title="Post Instagram Protegido",
        caption=full_ig_caption,
        content=full_ig_caption,
        post_type="INSTAGRAM",
        is_news=True,
        is_event=False,
        is_edited=False,
        published_at=orig_ts,
        media_url="https://cdn.instagram.com/original.jpg",
        media_type="IMAGE",
        permalink="https://www.instagram.com/p/Corig888/",
        link_url="https://www.instagram.com/p/Corig888/",
        link_label="Ver en Instagram",
        target_groups=["ALL"],
    )
    db.add(ig_post)
    db.commit()
    ig_id = ig_post.id
    db.close()

    headers = auth(EDITOR_ID, EDITOR_EMAIL, "editor")
    updated = client.put(
        f"/api/publications/{ig_id}",
        json={
            "title": "Título editorial personalizado",
            "caption": "Intento de sobrescribir resumen",
            "content": "Intento de sobrescribir contenido sincronizado",
            "media_url": "https://otro.sitio/hack.jpg",
            "link_url": "https://otro.sitio/link",
            "permalink": "https://otro.sitio/link",
            "target_groups": ["ALL", "TIE"],
        },
        headers=headers,
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["title"] == "Título editorial personalizado"
    assert body["caption"] == "Primera línea del post de Instagram.\nSegunda línea del resumen automático."
    assert body["content"] == full_ig_caption
    assert body["media_url"] == "https://cdn.instagram.com/original.jpg"
    assert body["permalink"] == "https://www.instagram.com/p/Corig888/"
    assert body["link_url"] == "https://www.instagram.com/p/Corig888/"
    assert body["target_groups"] == ["ALL", "TIE"]


def test_web_admin_ux_invariants_clean_labels_and_no_legacy_noise():
    web_dir = Path(__file__).resolve().parent.parent.parent / "web-admin"
    index_html = (web_dir / "index.html").read_text(encoding="utf-8")
    app_js = (web_dir / "app.js").read_text(encoding="utf-8")
    editorial_js = (web_dir / "editorial.js").read_text(encoding="utf-8")

    # Textos y controles heredados eliminados (SRV-160 + SRV-168)
    for forbidden_text in (
        "Google OAuth 2.0 Verificado",
        "Google OAuth 2.0 Conectado",
        "Guardar en PostgreSQL",
        "In Zwischenablage kopieren",
        "Comunidad y Distribución",
        "btn-dev-admin-login",
        "Acceso rápido",
    ):
        assert forbidden_text not in index_html
        assert forbidden_text not in app_js

    for removed_field in ("ed-pub-type", "ed-pub-category", "ed-pub-detail-text"):
        assert removed_field not in index_html
        assert removed_field not in editorial_js

    # Casillas de permisos en Roles desmarcadas por defecto
    assert 'id="perm-publications" checked' not in index_html
    assert 'id="perm-groups" checked' not in index_html
    assert 'id="perm-admins" checked' not in index_html
    assert 'id="perm-diagnostic" checked' not in index_html

    # Elementos clave de la arquitectura UX vigente
    assert "Recargar datos" in index_html
    assert 'id="user-menu-btn"' in index_html
    assert 'id="ed-form-pub"' in index_html
    assert 'id="ed-pub-scheduled"' in index_html
    assert 'id="ed-pub-expires-wrap"' in index_html
    assert "Notificar por push" in index_html
    assert 'id="groups-filter-input"' in index_html
    assert 'id="group-workspace-filter"' in index_html
    assert 'id="form-group-editor"' in index_html
    assert 'id="apis-json-details"' in index_html
