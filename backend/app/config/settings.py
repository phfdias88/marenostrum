"""
Configuracao centralizada (Pydantic Settings).
Le variaveis de ambiente / .env com tipagem estatica.
"""
from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    APP_ENV: str = "development"
    APP_NAME: str = "MareNostrum API"

    # Postgres
    POSTGRES_HOST: str = "db"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "marenostrum"
    POSTGRES_USER: str = "marenostrum"
    POSTGRES_PASSWORD: str = "changeme"

    # JWT
    JWT_SECRET_KEY: str = Field(..., min_length=16)
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    CORS_ORIGINS: List[str] = ["http://localhost:3000"]

    # Geocoding (Nominatim/OpenStreetMap)
    # User-Agent obrigatorio pela politica de uso do Nominatim.
    # Use o email do projeto para contato em caso de uso abusivo.
    NOMINATIM_USER_AGENT: str = "MareNostrum/0.1 (admin@marenostrum.local)"
    NOMINATIM_BASE_URL: str = "https://nominatim.openstreetmap.org"
    # Cidade/UF default usada quando o contato nao informar — base do MVP
    GEOCODING_DEFAULT_CITY: str = "Juiz de Fora"
    GEOCODING_DEFAULT_STATE: str = "MG"

    @property
    def database_url(self) -> str:
        # psycopg v3 driver
        return (
            f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


@lru_cache
def get_settings() -> Settings:
    """Cache para evitar releitura do .env em cada request."""
    return Settings()  # type: ignore[call-arg]
