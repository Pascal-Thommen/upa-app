"""Tests for backend healthcheck endpoint."""

from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)


def test_health_check_status_code():
    response = client.get("/health")
    assert response.status_code == 200


def test_health_check_payload_structure():
    response = client.get("/health")
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "upa-app-backend"
    assert "environment" in data
