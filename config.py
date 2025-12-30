# config.py
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    DB_PATH: str = "./anime_rank.db"
    AUTH_USERNAME: str = "admin"
    AUTH_PASSWORD: str = "password"

    # Elo Ranking Constants
    ELO_K_FACTOR_DEFAULT: int = 32
    ELO_K_FACTOR_PLACEMENT: int = 64
    ELO_PLACEMENT_MATCHES: int = 10

    class Config:
        env_file = ".env"


@lru_cache
def get_settings():
    return Settings()


settings = get_settings()
