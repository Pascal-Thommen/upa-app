"""Tests for database connectivity and readiness probe."""

from collections.abc import Generator

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from src.database import check_db_connection, get_db
from src.main import app

client = TestClient(app)


def test_readiness_check_status_code():
    response = client.get("/ready")
    assert response.status_code == 200


def test_readiness_check_payload_structure():
    response = client.get("/ready")
    data = response.json()
    assert "status" in data
    assert "database" in data
    assert data["service"] == "upa-app-backend"
    assert data["status"] in ("ready", "not_ready")


def test_database_connection_check():
    # SQLite connection initialized in test environment should be healthy
    is_connected = check_db_connection()
    assert is_connected is True


def test_database_get_db_session_yields():
    gen = get_db()
    assert isinstance(gen, Generator)
    session = next(gen)
    assert isinstance(session, Session)
    # Ensure generator cleanup
    try:
        next(gen)
    except StopIteration:
        pass
