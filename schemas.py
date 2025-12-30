# schemas.py
from pydantic import BaseModel, ConfigDict
from typing import Optional


class VoteResponse(BaseModel):
    a1_id: int
    a2_id: int

    # 점수 정보
    old_r1: int
    new_r1: int
    diff_r1: int
    old_r2: int
    new_r2: int
    diff_r2: int

    # 등수 정보 (New)
    old_rank_1: int
    new_rank_1: int
    old_rank_2: int
    new_rank_2: int
    total_animes: int

    next_url: str

    model_config = ConfigDict(from_attributes=True)
