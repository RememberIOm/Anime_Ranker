# config.py
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    DB_PATH: str = "./anime_rank.db"
    AUTH_USERNAME: str = "admin"
    AUTH_PASSWORD: str = "password"

    # --- Elo Rating Constants ---
    # 초기 진입 시 변동폭 (배치고사 느낌)
    ELO_K_MAX: int = 60
    # 안정화 이후 최소 변동폭
    ELO_K_MIN: int = 24
    # K-Factor가 줄어드는 속도 (높을수록 천천히 줄어듦)
    ELO_DECAY_FACTOR: int = 25

    # --- Matchmaking Constants ---
    MATCH_SMART_RATE: float = 0.8
    MATCH_SCORE_RANGE: int = 300

    # --- Probability Calculation Constants (New) ---
    # 두 상대의 점수가 같을 때의 최대 무승부 확률 (0.0 ~ 1.0)
    # 예: 0.25는 동점일 때 25% 확률로 무승부가 난다고 가정
    ELO_DRAW_MAX: float = 0.25
    # 무승부 확률이 줄어드는 점수 차이의 척도 (Gaussian Scale)
    ELO_DRAW_SCALE: float = 400.0

    class Config:
        env_file = ".env"


@lru_cache
def get_settings():
    return Settings()


settings = get_settings()
