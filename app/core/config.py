from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    PROJECT_NAME: str = "VOD SaaS Platform"
    API_V1_STR: str = "/api/v1"
    
    # Database
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str = "vod_saas"
    # Port is usually 5432
    DATABASE_URL: Optional[str] = None

    @property
    def async_database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    # JWT
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # B2 Storage
    B2_APPLICATION_KEY_ID: str
    B2_APPLICATION_KEY: str
    B2_BUCKET_NAME: str = "vod-saas-creators-media"
    B2_ENDPOINT: str = "https://f002.backblazeb2.com" # Default Friendly URL Endpoint
    B2_PUBLIC_URL: Optional[str] = None # Optional CDN override (e.g. Cloudflare)

settings = Settings()
