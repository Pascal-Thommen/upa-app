"""Tests for backend configuration and settings."""

from pathlib import Path

from src.config import (
    DEFAULT_ALLOWED_EMAIL_DOMAIN,
    DEFAULT_GOOGLE_CLIENT_ID,
    Settings,
    log_oauth_config_status,
)


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


def test_oauth_fallback_defaults_when_env_vars_absent():
    """Sin variables de entorno, Google Client ID y dominio caen a sus fallbacks seguros."""
    settings = Settings(_env_file=None)
    assert settings.GOOGLE_CLIENT_ID == DEFAULT_GOOGLE_CLIENT_ID
    assert settings.GOOGLE_CLIENT_ID == "50361321197-om1eptt5qisjn8jeunkjs47o56il7s33.apps.googleusercontent.com"
    assert settings.ALLOWED_EMAIL_DOMAIN == DEFAULT_ALLOWED_EMAIL_DOMAIN
    assert settings.ALLOWED_EMAIL_DOMAIN == "upa.edu.py"
    assert settings.google_client_id_configured is True
    assert settings.allowed_email_domain_configured is True


def test_oauth_client_id_default_is_registered_in_allowed_ids():
    settings = Settings(_env_file=None)
    assert DEFAULT_GOOGLE_CLIENT_ID in settings.allowed_google_client_ids_list


def test_oauth_credentials_complete_requires_client_secret():
    settings = Settings(_env_file=None)
    assert settings.google_client_secret_configured is False
    assert settings.oauth_credentials_complete is False

    complete = Settings(_env_file=None, GOOGLE_CLIENT_SECRET="secreto-real")
    assert complete.google_client_secret_configured is True
    assert complete.oauth_credentials_complete is True


def test_oauth_placeholder_values_are_not_considered_configured():
    settings = Settings(
        _env_file=None,
        GOOGLE_CLIENT_ID="your-google-client-id.apps.googleusercontent.com",
        GOOGLE_CLIENT_SECRET="your-google-client-secret",
    )
    assert settings.google_client_id_configured is False
    assert settings.google_client_secret_configured is False
    assert settings.oauth_credentials_complete is False


def test_oauth_config_summary_reports_real_state():
    settings = Settings(_env_file=None)
    summary = settings.oauth_config_summary()
    assert summary["google_client_id_configured"] is True
    assert summary["google_client_secret_configured"] is False
    assert summary["allowed_email_domain"] == "upa.edu.py"
    assert summary["oauth_credentials_complete"] is False


def test_log_oauth_config_status_emits_complete(caplog):
    import logging

    complete = Settings(_env_file=None, GOOGLE_CLIENT_SECRET="secreto-real")
    with caplog.at_level(logging.INFO, logger="upa.config"):
        log_oauth_config_status(complete)
    assert "COMPLETA" in caplog.text


def test_log_oauth_config_status_emits_incomplete(caplog):
    import logging

    incomplete = Settings(_env_file=None)
    with caplog.at_level(logging.WARNING, logger="upa.config"):
        log_oauth_config_status(incomplete)
    assert "INCOMPLETA" in caplog.text
    assert "GOOGLE_CLIENT_SECRET" in caplog.text


def test_docker_compose_anchors_google_client_id_and_nginx_caches_static_assets():
    repo_root = Path(__file__).resolve().parent.parent.parent
    compose_text = (repo_root / "docker-compose.yml").read_text(encoding="utf-8")
    assert DEFAULT_GOOGLE_CLIENT_ID in compose_text
    assert "GOOGLE_CLIENT_ID:" in compose_text
    assert "/home/pasc/.config/upa-app/.env" in compose_text
    assert "./backend/.env" in compose_text
    assert "/home/pasc/.config/upa-app/secrets:/app/secrets:ro" in compose_text

    nginx_text = (repo_root / "web-admin" / "nginx.conf").read_text(encoding="utf-8")
    assert "public, max-age=86400" in nginx_text
    assert "no-cache, must-revalidate" in nginx_text
    assert "location = /index.html" in nginx_text


def test_index_html_asset_version_busts_cache_and_roles_header_matches_permissions():
    import re

    repo_root = Path(__file__).resolve().parent.parent.parent
    html = (repo_root / "web-admin" / "index.html").read_text(encoding="utf-8")
    versions = set(re.findall(r"/dashboard/[\w.-]+\.(?:js|css)\?v=([\d.]+)", html))
    assert versions == {"2.3.0"}
    thead = html.split('<tbody id="admin-table-rows"')[0].split('aria-label="Roles"')[1]
    assert thead.count("<th ") == 7
    assert "Historial</th>" in thead
