"""Pruebas de integracion para la agenda consolidada y el estado de inicio (app-state)."""

import time
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from src.api.classroom import _DEADLINES_CACHE, clear_classroom_cache
from src.auth import create_access_token
from src.database import Base, get_db
from src.main import app
from src.models import EventRegistration, Post, User
from src.schemas.classroom import (
    ClassroomDeadlineResponse,
    ClassroomDueDate,
    ClassroomDueTime,
)

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
def setup_agenda_database():
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    clear_classroom_cache()
    db = TestingSessionLocal()

    student = User(
        id=10,
        email="estudiante.tie@upa.edu.py",
        full_name="Estudiante TIE",
        role="user",
        groups=["TIE", "ALL"],
        classroom_token="ya29.valid_cached_token",
    )
    admin = User(
        id=1,
        email="pascal.thommen@upa.edu.py",
        full_name="Pascal Thommen",
        role="admin",
        groups=["ALL"],
    )
    db.add_all([student, admin])
    db.commit()

    now = datetime.now(UTC)

    # Evento futuro 2 (en 5 dias)
    ev_later = Post(
        id=202,
        title="Simposio de Robotica Industrial",
        caption="Presentacion de proyectos de ingenieria",
        content="Demostracion en laboratorio central",
        post_type="MANUAL",
        is_news=True,
        is_event=True,
        event_start=now + timedelta(days=5),
        event_end=now + timedelta(days=5, hours=2),
        location="Laboratorio de Robotica",
        has_registration=True,
        target_groups=["ALL", "TIE"],
    )

    # Evento futuro 1 (en 1 dia)
    ev_sooner = Post(
        id=201,
        title="Charla de Ciberseguridad Bancaria",
        caption="Conferencia abierta para TIE",
        content="Seguridad en infraestructuras criticas",
        post_type="MANUAL",
        is_news=True,
        is_event=True,
        event_start=now + timedelta(days=1),
        event_end=now + timedelta(days=1, hours=2),
        location="Auditorio Principal",
        has_registration=True,
        target_groups=["TIE"],
    )

    # Evento pasado (hace 60 dias, fuera de la ventana activa de 35 dias)
    ev_past = Post(
        id=203,
        title="Evento Historico Pasado",
        content="Ya finalizado",
        post_type="MANUAL",
        is_news=False,
        is_event=True,
        event_start=now - timedelta(days=60),
        event_end=now - timedelta(days=60, hours=1),
        location="Aula 101",
        target_groups=["ALL"],
    )

    # Evento exclusivo de docentes (restringido para estudiante)
    ev_prof = Post(
        id=204,
        title="Claustro Exclusivo Docentes",
        content="Solo profesores",
        post_type="MANUAL",
        is_news=False,
        is_event=True,
        event_start=now + timedelta(days=2),
        location="Sala de Consejo",
        target_groups=["PROF"],
    )

    db.add_all([ev_later, ev_sooner, ev_past, ev_prof])
    db.commit()

    # Inscribir al estudiante en ev_sooner
    reg = EventRegistration(post_id=201, user_id=10, status="attending")
    db.add(reg)
    db.commit()
    db.close()

    yield

    clear_classroom_cache()
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.pop(get_db, None)


def test_agenda_status_code():
    response = client.get("/api/v1/agenda")
    assert response.status_code == 200


def test_agenda_response_structure():
    response = client.get("/api/v1/agenda")
    data = response.json()
    assert "events" in data
    assert isinstance(data["events"], list)
    assert "deadlines" in data
    assert isinstance(data["deadlines"], list)
    assert "items" in data
    assert isinstance(data["items"], list)


def test_agenda_chronological_consolidation_of_events_and_deadlines():
    now = datetime.now(UTC)
    dl_dt = now + timedelta(days=3)
    formatted_dl = f"{dl_dt.year:04d}-{dl_dt.month:02d}-{dl_dt.day:02d} 23:59"

    _DEADLINES_CACHE["estudiante.tie@upa.edu.py"] = (
        time.time(),
        [
            ClassroomDeadlineResponse(
                id="hw_301",
                assignment_id="hw_301",
                course_id="course_1",
                course="Arquitectura de Software",
                course_name="Arquitectura de Software",
                title="Entrega de Diagrama C4",
                description="Subir PDF a Classroom",
                due_date=ClassroomDueDate(year=dl_dt.year, month=dl_dt.month, day=dl_dt.day),
                due_time=ClassroomDueTime(hours=23, minutes=59),
                due_date_formatted=formatted_dl,
                alternate_link="https://classroom.google.com/c/course_1/a/hw_301",
                max_points=100.0,
            )
        ],
    )

    token = create_access_token({"sub": "10", "email": "estudiante.tie@upa.edu.py", "role": "user"})
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.get("/api/v1/agenda", headers=headers)
    assert resp.status_code == 200
    data = resp.json()

    # Verificar eventos reales ordenados cronologicamente (sin pasado ni PROF)
    events = data["events"]
    assert len(events) == 2
    assert events[0]["id"] == 201
    assert events[0]["title"] == "Charla de Ciberseguridad Bancaria"
    assert events[0]["is_registered"] is True
    assert events[0]["registered_count"] == 1
    assert events[1]["id"] == 202
    assert events[1]["title"] == "Simposio de Robotica Industrial"
    assert events[1]["is_registered"] is False
    assert events[1]["registered_count"] == 0

    # Verificar plazos de Classroom
    deadlines = data["deadlines"]
    assert len(deadlines) == 1
    assert deadlines[0]["id"] == "hw_301"
    assert deadlines[0]["title"] == "Entrega de Diagrama C4"

    # Verificar linea de tiempo consolidada en orden cronologico estricto:
    # 1. Charla (+1d) -> 2. Entrega (+3d) -> 3. Simposio (+5d)
    items = data["items"]
    assert len(items) == 3
    assert [i["title"] for i in items] == [
        "Charla de Ciberseguridad Bancaria",
        "Entrega de Diagrama C4",
        "Simposio de Robotica Industrial",
    ]
    assert [i["item_type"] for i in items] == ["EVENT", "DEADLINE", "EVENT"]


def test_app_state_legacy_endpoint_removed():
    assert client.get("/api/v1/app-state").status_code == 404


def test_oct26_event_visible_in_agenda_and_paraguay_24h_optional_end():
    """
    Caso real SRV-212: un evento creado para el 26/10/2026 (Lunes 26 de octubre) en formato
    paraguayo DD/MM/YYYY y 24h HH:mm (15:30 a 16:30 o con fin opcional vacio) es inmediatamente
    visible en /api/v1/agenda y en el calendario mensual del estudiante.
    """
    admin_token = create_access_token({"sub": "1", "email": "pascal.thommen@upa.edu.py", "role": "admin"})
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    student_token = create_access_token({"sub": "10", "email": "estudiante.tie@upa.edu.py", "role": "user"})
    student_headers = {"Authorization": f"Bearer {student_token}"}

    # 1. Crear evento del 26 de octubre usando DD/MM/YYYY y 24h HH:mm con fin opcional omitido
    create_oct26 = client.post(
        "/api/publications",
        json={
            "title": "Jornada Académica del 26 de Octubre",
            "content": "Actividad oficial del campus UPA",
            "is_news": True,
            "is_event": True,
            "event_date": "26/10/2026",
            "event_start_time": "15:30",
            "event_end": None,
            "location": "Auditorio Principal",
            "target_groups": ["docentes", "egresados", "estudiantes", "staff"],
        },
        headers=admin_headers,
    )
    assert create_oct26.status_code == 201
    created_pub = create_oct26.json()
    assert created_pub["event_date"] == "26/10/2026"
    assert created_pub["event_start_time"] == "15:30"
    assert created_pub["event_end"] is None
    assert created_pub["event_end_time"] == ""
    assert created_pub["event_start_formatted"] == "26/10/2026 15:30"

    # 2. Verificar que aparece en /api/v1/agenda del estudiante con sort_key en el dia 2026-10-26
    agenda_res = client.get("/api/v1/agenda", headers=student_headers)
    assert agenda_res.status_code == 200
    agenda_data = agenda_res.json()
    ev_match = next((e for e in agenda_data["events"] if e["id"] == created_pub["id"]), None)
    assert ev_match is not None, "El evento del 26 de octubre debe ser visible en la agenda"
    assert ev_match["event_date"] == "26/10/2026"
    assert ev_match["event_start_time"] == "15:30"
    assert ev_match["event_end"] is None
    assert ev_match["event_end_time"] == ""

    item_match = next(
        (i for i in agenda_data["items"] if i["item_type"] == "EVENT" and i["id"] == str(created_pub["id"])),
        None,
    )
    assert item_match is not None
    assert item_match["sort_key"] == "2026-10-26 15:30"

    # 3. Actualizar con hora de fin en el mismo dia (16:30 en formato 24h)
    upd_same_day = client.put(
        f"/api/publications/{created_pub['id']}",
        json={"event_end_time": "16:30"},
        headers=admin_headers,
    )
    assert upd_same_day.status_code == 200
    upd_body = upd_same_day.json()
    assert upd_body["event_end"] is not None
    assert upd_body["event_end_time"] == "16:30"
    assert upd_body["event_end_formatted"] == "26/10/2026 16:30"

    # 4. Rechazar fin de evento en otro dia calendario (mismo dia obligatorio)
    bad_other_day = client.put(
        f"/api/publications/{created_pub['id']}",
        json={"event_end": "27/10/2026 16:30"},
        headers=admin_headers,
    )
    assert bad_other_day.status_code == 400
    assert "mismo día" in bad_other_day.json()["detail"].lower()
