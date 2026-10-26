"""Tests for CORS middleware behavior."""

from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)


def test_cors_headers_allowed_origin():
    response = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_cors_preflight_request():
    response = client.options(
        "/api/v1/feed",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
