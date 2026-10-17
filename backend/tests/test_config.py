"""Tests for backend configuration and settings."""

from src.config import Settings


def test_default_settings():
    settings = Settings()
    assert settings.PORT == 8000
    assert settings.HOST == "0.0.0.0"
    assert settings.ALLOWED_EMAIL_DOMAIN == "upa.edu.py"
    assert settings.APP_ENV in ("development", "production", "test")


def test_cors_origins_list_parsing():
    settings = Settings(CORS_ORIGINS="http://localhost:3000, http://example.com , https://upa.edu.py")
    origins = settings.cors_origins_list
    assert len(origins) == 3
    assert "http://localhost:3000" in origins
    assert "http://example.com" in origins
    assert "https://upa.edu.py" in origins


def test_cors_origins_list_empty_handling():
    settings = Settings(CORS_ORIGINS="   ,  ,")
    origins = settings.cors_origins_list
    assert len(origins) == 0
