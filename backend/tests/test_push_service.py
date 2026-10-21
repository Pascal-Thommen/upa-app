"""Pruebas del servicio push (FCM HTTP v1) contra un servidor de protocolo local real."""

import json
import socket
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from src.auth import create_access_token
from src.config import settings
from src.database import Base, get_db
from src.main import app
from src.models import AdminAuditLog, DeviceToken, User
from src.services.push import (
    PushConfigurationError,
    PushDispatcher,
    build_emergency_message,
    collect_recipient_tokens,
    load_service_account,
)

from tests.fcm_protocol_server import CLIENT_EMAIL, PROJECT_ID, FcmProtocolServer, generate_rsa_keypair

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


@pytest.fixture(scope="module")
def keypair():
    return generate_rsa_keypair()


@pytest.fixture
def fcm_server(keypair):
    server = FcmProtocolServer(public_key_pem=keypair[1])
    server.start()
    yield server
    server.stop()


def write_service_account(tmp_path, private_pem: str, token_uri: str, **overrides) -> str:
    data = {
        "type": "service_account",
        "project_id": PROJECT_ID,
        "client_email": CLIENT_EMAIL,
        "private_key": private_pem,
        "token_uri": token_uri,
    }
    data.update(overrides)
    path = tmp_path / "fcm-account.json"
    path.write_text(json.dumps(data))
    return str(path)


@pytest.fixture
def dispatcher(fcm_server, keypair, tmp_path):
    account = write_service_account(tmp_path, keypair[0], f"{fcm_server.base_url}/token")
    return PushDispatcher(service_account_file=account, api_base_url=fcm_server.base_url, timeout_seconds=5.0)


# ---------------------------------------------------------------- Dispatcher: Caso normal


@pytest.mark.asyncio
async def test_sends_notification_with_exact_fcm_payload(dispatcher, fcm_server):
    result = await dispatcher.send_to_tokens(
        ["tok-android-0001"],
        title="Clases suspendidas",
        body="Hoy no hay clases por mantenimiento electrico.",
        data={"type": "EMERGENCY_BANNER", "post_id": 7},
    )
    assert (result.attempted, result.sent, result.failed) == (1, 1, 0)
    assert result.invalid_tokens == []
    assert result.skipped_reason is None
    assert fcm_server.messages == [
        {
            "notification": {
                "title": "Clases suspendidas",
                "body": "Hoy no hay clases por mantenimiento electrico.",
            },
            "data": {"type": "EMERGENCY_BANNER", "post_id": "7"},
            "android": {"priority": "HIGH"},
            "token": "tok-android-0001",
        }
    ]


@pytest.mark.asyncio
async def test_duplicate_and_blank_tokens_are_sent_once(dispatcher, fcm_server):
    result = await dispatcher.send_to_tokens(["tok-dup-0001", " tok-dup-0001 ", "", "   ", "tok-dup-0002"], "T", "B")
    assert (result.attempted, result.sent) == (2, 2)
    assert sorted(m["token"] for m in fcm_server.messages) == ["tok-dup-0001", "tok-dup-0002"]


@pytest.mark.asyncio
async def test_access_token_is_cached_across_sends(dispatcher, fcm_server):
    await dispatcher.send_to_tokens(["tok-cache-0001"], "T", "B")
    await dispatcher.send_to_tokens(["tok-cache-0002"], "T", "B")
    assert fcm_server.oauth_requests == 1
    assert len(fcm_server.messages) == 2


@pytest.mark.asyncio
async def test_expired_access_token_is_refreshed_once_and_message_is_delivered(dispatcher, fcm_server):
    fcm_server.reject_first_message_with_401 = True
    result = await dispatcher.send_to_tokens(["tok-refresh-0001"], "T", "B")
    assert (result.sent, result.failed) == (1, 0)
    assert fcm_server.oauth_requests == 2


@pytest.mark.asyncio
async def test_long_text_is_truncated_to_fcm_limits(dispatcher, fcm_server):
    await dispatcher.send_to_tokens(["tok-long-00001"], "t" * 500, "b" * 1000)
    notification = fcm_server.messages[0]["notification"]
    assert len(notification["title"]) == 120
    assert len(notification["body"]) == 240


# ---------------------------------------------------------------- Dispatcher: Casos de error


@pytest.mark.asyncio
async def test_unregistered_token_is_reported_as_invalid_and_others_still_sent(dispatcher, fcm_server):
    result = await dispatcher.send_to_tokens(["tok-good-00001", "dead-token-0001"], "T", "B")
    assert (result.attempted, result.sent, result.failed) == (2, 1, 1)
    assert result.invalid_tokens == ["dead-token-0001"]
    assert [m["token"] for m in fcm_server.messages] == ["tok-good-00001"]


@pytest.mark.asyncio
async def test_fcm_server_error_counts_as_failed_not_invalid(dispatcher):
    result = await dispatcher.send_to_tokens(["boom-token-0001"], "T", "B")
    assert (result.sent, result.failed) == (0, 1)
    assert result.invalid_tokens == []


@pytest.mark.asyncio
async def test_timeout_is_enforced_and_reported(fcm_server, keypair, tmp_path):
    account = write_service_account(tmp_path, keypair[0], f"{fcm_server.base_url}/token")
    slow = PushDispatcher(service_account_file=account, api_base_url=fcm_server.base_url, timeout_seconds=0.4)
    started = time.monotonic()
    result = await slow.send_to_tokens(["slow-token-0001"], "T", "B")
    elapsed = time.monotonic() - started
    assert (result.sent, result.failed) == (0, 1)
    assert elapsed < 1.8, "el timeout explicito no se respeto"


@pytest.mark.asyncio
async def test_network_down_is_reported_as_failure_without_exception(keypair, tmp_path):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        closed_port = sock.getsockname()[1]
    account = write_service_account(tmp_path, keypair[0], f"http://127.0.0.1:{closed_port}/token")
    unreachable = PushDispatcher(
        service_account_file=account, api_base_url=f"http://127.0.0.1:{closed_port}", timeout_seconds=1.0
    )
    result = await unreachable.send_to_tokens(["tok-net-000001", "tok-net-000002"], "T", "B")
    assert (result.attempted, result.sent, result.failed) == (2, 0, 2)


@pytest.mark.asyncio
async def test_oauth_rejection_with_wrong_key_counts_as_failure(fcm_server, tmp_path):
    other_private, _ = generate_rsa_keypair()
    account = write_service_account(tmp_path, other_private, f"{fcm_server.base_url}/token")
    wrong = PushDispatcher(service_account_file=account, api_base_url=fcm_server.base_url, timeout_seconds=2.0)
    result = await wrong.send_to_tokens(["tok-key-000001"], "T", "B")
    assert (result.sent, result.failed) == (0, 1)
    assert fcm_server.messages == []


@pytest.mark.asyncio
async def test_missing_service_account_is_skipped_as_not_configured(tmp_path):
    dispatcher = PushDispatcher(service_account_file=str(tmp_path / "no-existe.json"))
    result = await dispatcher.send_to_tokens(["tok-nocfg-0001"], "T", "B")
    assert result.skipped_reason == "not_configured"
    assert (result.attempted, result.sent, result.failed) == (1, 0, 1)


@pytest.mark.asyncio
async def test_no_recipients_is_skipped(dispatcher, fcm_server):
    result = await dispatcher.send_to_tokens([], "T", "B")
    assert result.skipped_reason == "no_recipients"
    assert result.attempted == 0
    assert fcm_server.oauth_requests == 0


# ---------------------------------------------------------------- Service Account validacion


def test_load_service_account_rejects_corrupt_and_incomplete_files(tmp_path, keypair):
    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{no json")
    with pytest.raises(PushConfigurationError):
        load_service_account(str(corrupt))

    incomplete = tmp_path / "incomplete.json"
    incomplete.write_text(json.dumps({"client_email": CLIENT_EMAIL}))
    with pytest.raises(PushConfigurationError, match="private_key"):
        load_service_account(str(incomplete))

    no_project = write_service_account(tmp_path, keypair[0], "http://x/token", project_id="")
    with pytest.raises(PushConfigurationError, match="project"):
        load_service_account(no_project)


def test_project_id_override_wins_over_file(tmp_path, keypair):
    path = write_service_account(tmp_path, keypair[0], "http://x/token")
    assert load_service_account(path, project_id_override="otro-proyecto").project_id == "otro-proyecto"
    assert load_service_account(path).project_id == PROJECT_ID


# ---------------------------------------------------------------- Base de datos y API


@pytest.fixture
def db_session():
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    db.add_all(
        [
            User(id=1, email="admin@upa.edu.py", full_name="Admin", role="admin", groups=["ALL"]),
            User(id=2, email="tie@upa.edu.py", full_name="Estudiante TIE", role="user", groups=["TIE"],
                 device_token="legacy-token-tie"),
            User(id=3, email="prof@upa.edu.py", full_name="Profesor", role="user", groups=["PROF"]),
            User(id=4, email="sintoken@upa.edu.py", full_name="Sin Token", role="user", groups=["TIE"]),
        ]
    )
    db.add_all(
        [
            DeviceToken(user_id=2, device_token="legacy-token-tie", platform="android"),
            DeviceToken(user_id=2, device_token="tie-phone-token-2", platform="android"),
            DeviceToken(user_id=3, device_token="prof-phone-token", platform="android"),
        ]
    )
    db.commit()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.pop(get_db, None)


def test_collect_recipient_tokens_respects_target_groups(db_session):
    tie_tokens = set(collect_recipient_tokens(db_session, ["TIE"]))
    assert tie_tokens == {"legacy-token-tie", "tie-phone-token-2"}
    assert set(collect_recipient_tokens(db_session, ["PROF"])) == {"prof-phone-token"}
    assert set(collect_recipient_tokens(db_session, ["ALL"])) == {
        "legacy-token-tie",
        "tie-phone-token-2",
        "prof-phone-token",
    }
    assert collect_recipient_tokens(db_session, ["NADIE"]) == []


def admin_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': '1'})}"}


@pytest.fixture
def fcm_settings(monkeypatch, fcm_server, keypair, tmp_path):
    account = write_service_account(tmp_path, keypair[0], f"{fcm_server.base_url}/token")
    monkeypatch.setattr(settings, "FCM_SERVICE_ACCOUNT_FILE", account)
    monkeypatch.setattr(settings, "FCM_PROJECT_ID", "")
    monkeypatch.setattr(settings, "FCM_API_BASE_URL", fcm_server.base_url)
    monkeypatch.setattr(settings, "FCM_TIMEOUT_SECONDS", 5.0)
    return fcm_server


def test_emergency_banner_triggers_push_to_targeted_devices_only(db_session, fcm_settings):
    response = client.post(
        "/api/news",
        json={
            "title": "Evacuacion del edificio B",
            "caption": "Dirigirse al punto de encuentro del campus.",
            "post_type": "EMERGENCY_BANNER",
            "target_groups": ["TIE"],
        },
        headers=admin_headers(),
    )
    assert response.status_code == 201
    post_id = response.json()["id"]

    assert sorted(m["token"] for m in fcm_settings.messages) == ["legacy-token-tie", "tie-phone-token-2"]
    for message in fcm_settings.messages:
        assert message["notification"] == {
            "title": "Evacuacion del edificio B",
            "body": "Dirigirse al punto de encuentro del campus.",
        }
        assert message["data"] == {"type": "EMERGENCY_BANNER", "post_id": str(post_id)}

    audit = db_session.query(AdminAuditLog).filter(AdminAuditLog.action == "TRIGGER_PUSH").one()
    assert audit.target_id == post_id
    assert audit.details == {"post_type": "EMERGENCY_BANNER", "recipients": 2}


def test_manual_post_sends_no_push(db_session, fcm_settings):
    response = client.post(
        "/api/news",
        json={"title": "Charla informativa", "post_type": "MANUAL", "target_groups": ["ALL"]},
        headers=admin_headers(),
    )
    assert response.status_code == 201
    assert fcm_settings.messages == []
    assert fcm_settings.oauth_requests == 0
    assert db_session.query(AdminAuditLog).filter(AdminAuditLog.action == "TRIGGER_PUSH").count() == 0


def test_emergency_banner_is_saved_even_when_fcm_is_unreachable(db_session, monkeypatch, keypair, tmp_path):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        closed_port = sock.getsockname()[1]
    account = write_service_account(tmp_path, keypair[0], f"http://127.0.0.1:{closed_port}/token")
    monkeypatch.setattr(settings, "FCM_SERVICE_ACCOUNT_FILE", account)
    monkeypatch.setattr(settings, "FCM_API_BASE_URL", f"http://127.0.0.1:{closed_port}")
    monkeypatch.setattr(settings, "FCM_TIMEOUT_SECONDS", 1.0)

    response = client.post(
        "/api/news",
        json={"title": "Corte de agua", "post_type": "EMERGENCY_BANNER", "target_groups": ["ALL"]},
        headers=admin_headers(),
    )
    assert response.status_code == 201
    listing = client.get("/api/news", headers=admin_headers())
    assert "Corte de agua" in [item["title"] for item in listing.json()]


def test_emergency_banner_is_saved_when_fcm_is_not_configured(db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "FCM_SERVICE_ACCOUNT_FILE", str(tmp_path / "no-existe.json"))
    response = client.post(
        "/api/news",
        json={"title": "Aviso sin FCM", "post_type": "EMERGENCY_BANNER", "target_groups": ["ALL"]},
        headers=admin_headers(),
    )
    assert response.status_code == 201
    assert response.json()["title"] == "Aviso sin FCM"


def test_build_emergency_message_falls_back_to_title_and_content(db_session):
    from src.models import Post

    only_title = Post(id=11, title="Solo titulo", post_type="EMERGENCY_BANNER")
    assert build_emergency_message(only_title) == (
        "Solo titulo",
        "Solo titulo",
        {"type": "EMERGENCY_BANNER", "post_id": "11"},
    )
    with_content = Post(id=12, title="T", content="Detalle largo", post_type="EMERGENCY_BANNER")
    assert build_emergency_message(with_content)[1] == "Detalle largo"
