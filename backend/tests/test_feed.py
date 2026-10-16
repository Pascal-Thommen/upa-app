"""Tests for backend campus feed endpoint."""

from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)


def test_feed_status_code():
    response = client.get("/api/v1/feed")
    assert response.status_code == 200


def test_feed_response_structure():
    response = client.get("/api/v1/feed")
    data = response.json()
    assert "urgent_banners" in data
    assert isinstance(data["urgent_banners"], list)
    assert "posts" in data
    assert isinstance(data["posts"], list)
