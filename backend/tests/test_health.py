from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "upa-app-backend"

def test_feed_stub_returns_structure():
    response = client.get("/api/v1/feed")
    assert response.status_code == 200
    data = response.json()
    assert "urgent_banners" in data
    assert "posts" in data

def test_agenda_stub_returns_structure():
    response = client.get("/api/v1/agenda")
    assert response.status_code == 200
    data = response.json()
    assert "events" in data
    assert "deadlines" in data
