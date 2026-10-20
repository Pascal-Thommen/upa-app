from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_ENV: str = "development"
    PORT: int = 8000
    HOST: str = "0.0.0.0"
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8000,http://100.110.128.107:8000,http://acersrv.netbird.cloud:8000,https://acersrv.netbird.cloud,https://multica.eu1.netbird.services"
    
    ALLOWED_EMAIL_DOMAIN: str = "upa.edu.py"
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    
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

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


settings = Settings()
