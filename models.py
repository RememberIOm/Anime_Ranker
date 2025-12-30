# models.py
from sqlalchemy import Column, Integer, String, Float
from database import Base

class Anime(Base):
    __tablename__ = "animes"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    
    # Elo Ratings (기본값 1200)
    rating_story = Column(Float, default=1200.0)
    rating_visual = Column(Float, default=1200.0)
    rating_ost = Column(Float, default=1200.0)
    rating_voice = Column(Float, default=1200.0)
    rating_char = Column(Float, default=1200.0)
    rating_fun = Column(Float, default=1200.0) # 종합적인 재미
    
    # 경기 수 (신뢰도 지표용)
    matches_played = Column(Integer, default=0)

    # 기존 CSV 데이터 참고용 (옵션)
    original_rank = Column(Integer, nullable=True)