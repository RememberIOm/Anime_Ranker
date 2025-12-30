# schemas.py
from pydantic import BaseModel, ConfigDict


class VoteResponse(BaseModel):
    a1_id: int
    a2_id: int
    old_r1: int
    new_r1: int
    diff_r1: int
    old_r2: int
    new_r2: int
    diff_r2: int
    next_url: str

    model_config = ConfigDict(from_attributes=True)
