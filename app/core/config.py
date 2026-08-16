from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", extra="ignore")

    PROJECT_NAME: str = "Parts Orders API"
    API_V1_PREFIX: str = "/api/v1"

    DATABASE_URL: str
    DEBUG: bool = False

    SECRET_KEY: str                              # obligatoire, depuis l'environnement
    # ACCESS_TOKEN_EXPIRE_MINUTES: int = 720       # 12h par défaut
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30        # court désormais (le refresh prend le relais)
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30          # durée de vie du refresh token
    JWT_ALGORITHM: str = "HS256"
    CORS_ORIGINS: str = ""

    @property
    def async_database_url(self) -> str:
        url = self.DATABASE_URL
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url


settings = Settings()