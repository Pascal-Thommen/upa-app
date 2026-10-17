"""Tests for backend agenda and calendar endpoint."""

from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)


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
