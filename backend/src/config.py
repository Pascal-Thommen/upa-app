
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_ENV: str = "development"
    PORT: int = 8000
    HOST: str = "0.0.0.0"
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8000"
    
    ALLOWED_EMAIL_DOMAIN: str = "upa.edu.py"
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    
    JWT_SECRET: str = "upa_super_secure_jwt_secret_dev_2026"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7
    
    SOCIABLEKIT_EMBED_ID: str = ""
    SOCIABLEKIT_API_URL: str = "https://data.sociablekit.com/api/v1/posts"
    
    DATABASE_URL: str = "postgresql://upa_user:upa_password@postgres:5432/upa_app"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
