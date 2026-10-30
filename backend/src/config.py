import logging
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("upa.config")

DEFAULT_GOOGLE_CLIENT_ID = "50361321197-om1eptt5qisjn8jeunkjs47o56il7s33.apps.googleusercontent.com"
DEFAULT_ALLOWED_EMAIL_DOMAIN = "upa.edu.py"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_ENV: str = "development"
    PORT: int = 8000
    HOST: str = "0.0.0.0"
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8000,http://localhost:8085,http://100.110.128.107:8000,http://acersrv.netbird.cloud:8000,https://acersrv.netbird.cloud,https://multica.eu1.netbird.services,https://upa-2vgh.eu1.netbird.services,https://upa-pwa-asn9.eu1.netbird.services,https://upa-pwa-io8l.eu1.netbird.services,https://upa-beta.eu1.netbird.services"

    ALLOWED_EMAIL_DOMAIN: str = DEFAULT_ALLOWED_EMAIL_DOMAIN
    GOOGLE_CLIENT_ID: str = DEFAULT_GOOGLE_CLIENT_ID
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = ""  # Optional, sonst dynamisch aus x-forwarded-proto/host
    ALLOWED_GOOGLE_CLIENT_IDS: str = "50361321197-om1eptt5qisjn8jeunkjs47o56il7s33.apps.googleusercontent.com,567912225771-7cf17vkfujmhb4itu2lri0ttssavfmcg.apps.googleusercontent.com"

    # Google Workspace Admin Directory API (Service Account)
    GOOGLE_SERVICE_ACCOUNT_FILE: str = "./secrets/service-account.json"
    GOOGLE_ADMIN_DELEGATED_USER: str = "soporte.ti@upa.edu.py"

    JWT_SECRET: str = "upa_super_secure_jwt_secret_dev_2026"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7

    DATABASE_URL: str = "postgresql://upa_user:upa_password@postgres:5432/upa_app"

    # Social Media & Instagram Sync (@upalemana)
    INSTAGRAM_ACCESS_TOKEN: str = ""
    INSTAGRAM_ACCOUNT_ID: str = ""
    SOCIABLEKIT_EMBED_ID: str = "25723525"
    FEED_SYNC_INTERVAL_MINUTES: int = 60
    FEED_SYNC_ENABLED: bool = True

    # Medien-Upload (Plakate, Banner, Dokumente)
    UPLOAD_DIR: str = "uploads"  # Im Container: /app/uploads (WORKDIR /app), persistent per Volume
    MAX_UPLOAD_SIZE_BYTES: int = 10 * 1024 * 1024
    PUBLIC_BASE_URL: str = ""  # Optional, z. B. https://api.upa.edu.py (sonst Basis-URL des Requests)

    # Push-Benachrichtigungen (Firebase Cloud Messaging HTTP v1)
    FCM_SERVICE_ACCOUNT_FILE: str = "./secrets/fcm-service-account.json"
    FCM_PROJECT_ID: str = ""  # Optional, sonst project_id aus der Service Account Datei
    FCM_TIMEOUT_SECONDS: float = 10.0
    FCM_API_BASE_URL: str = "https://fcm.googleapis.com"

    # Control de IA: Google Gemini (Google AI Studio). Fallback si no hay clave guardada en la base de datos.
    AI_EVENT_EXTRACTION_ENABLED: bool = True
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-1.5-flash"
    GEMINI_API_BASE_URL: str = "https://generativelanguage.googleapis.com"
    GEMINI_TIMEOUT_SECONDS: float = 15.0
    GEMINI_MAX_IMAGE_BYTES: int = 4 * 1024 * 1024

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def allowed_google_client_ids_list(self) -> list[str]:
        ids = [cid.strip() for cid in self.ALLOWED_GOOGLE_CLIENT_IDS.split(",") if cid.strip()]
        if self.GOOGLE_CLIENT_ID and self.GOOGLE_CLIENT_ID not in ids:
            ids.append(self.GOOGLE_CLIENT_ID)
        return ids

    @property
    def google_client_id_configured(self) -> bool:
        """True si el Client ID OAuth esta cargado (no vacio ni placeholder)."""
        cid = (self.GOOGLE_CLIENT_ID or "").strip()
        return bool(cid) and "placeholder" not in cid.lower() and "your-" not in cid.lower()

    @property
    def google_client_secret_configured(self) -> bool:
        """True si el Client Secret OAuth esta cargado (no vacio ni placeholder)."""
        secret = (self.GOOGLE_CLIENT_SECRET or "").strip()
        return bool(secret) and "placeholder" not in secret.lower() and "your-" not in secret.lower()

    @property
    def allowed_email_domain_configured(self) -> bool:
        """True si el dominio institucional esta definido y es valido."""
        return bool((self.ALLOWED_EMAIL_DOMAIN or "").strip())

    @property
    def oauth_credentials_complete(self) -> bool:
        """True si todas las credenciales OAuth imprescindibles estan cargadas."""
        return bool(
            self.google_client_id_configured
            and self.google_client_secret_configured
            and self.allowed_email_domain_configured
        )

    def oauth_config_summary(self) -> dict[str, Any]:
        """Resumen del estado de carga de credenciales OAuth para el logging de arranque."""
        return {
            "google_client_id_configured": self.google_client_id_configured,
            "google_client_secret_configured": self.google_client_secret_configured,
            "allowed_email_domain": (self.ALLOWED_EMAIL_DOMAIN or "").strip(),
            "allowed_email_domain_configured": self.allowed_email_domain_configured,
            "allowed_google_client_ids": self.allowed_google_client_ids_list,
            "oauth_credentials_complete": self.oauth_credentials_complete,
        }


def log_oauth_config_status(target: Settings | None = None) -> None:
    """Registra de forma inequivoca si las credenciales OAuth estan completas al arrancar."""
    config = target or settings
    summary = config.oauth_config_summary()

    if summary["oauth_credentials_complete"]:
        logger.info(
            "Configuracion OAuth COMPLETA: Google Client ID, Client Secret y dominio institucional "
            "(%s) cargados correctamente.",
            summary["allowed_email_domain"] or "sin dominio",
        )
        return

    faltantes = []
    if not summary["google_client_id_configured"]:
        faltantes.append("GOOGLE_CLIENT_ID")
    if not summary["google_client_secret_configured"]:
        faltantes.append("GOOGLE_CLIENT_SECRET")
    if not summary["allowed_email_domain_configured"]:
        faltantes.append("ALLOWED_EMAIL_DOMAIN")

    logger.warning(
        "Configuracion OAuth INCOMPLETA: faltan %s. El login OAuth puede fallar o rechazar "
        "dominios no institucionales.",
        ", ".join(faltantes) or "credenciales no determinadas",
    )


settings = Settings()
