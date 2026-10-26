from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_ENV: str = "development"
    PORT: int = 8000
    HOST: str = "0.0.0.0"
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8000,http://localhost:8085,http://100.110.128.107:8000,http://acersrv.netbird.cloud:8000,https://acersrv.netbird.cloud,https://multica.eu1.netbird.services,https://upa-2vgh.eu1.netbird.services,https://upa-pwa-asn9.eu1.netbird.services,https://upa-pwa-io8l.eu1.netbird.services"

    ALLOWED_EMAIL_DOMAIN: str = "upa.edu.py"
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
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

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def allowed_google_client_ids_list(self) -> list[str]:
        ids = [cid.strip() for cid in self.ALLOWED_GOOGLE_CLIENT_IDS.split(",") if cid.strip()]
        if self.GOOGLE_CLIENT_ID and self.GOOGLE_CLIENT_ID not in ids:
            ids.append(self.GOOGLE_CLIENT_ID)
        return ids


settings = Settings()
