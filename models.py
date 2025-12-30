# models.py
from sqlalchemy import Integer, String, Float
from sqlalchemy.orm import Mapped, mapped_column
from database import Base


class Anime(Base):
    __tablename__ = "animes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, index=True)

    # Elo Ratings (기본값 1200.0)
    rating_story: Mapped[float] = mapped_column(Float, default=1200.0)
    rating_visual: Mapped[float] = mapped_column(Float, default=1200.0)
    rating_ost: Mapped[float] = mapped_column(Float, default=1200.0)
    rating_voice: Mapped[float] = mapped_column(Float, default=1200.0)
    rating_char: Mapped[float] = mapped_column(Float, default=1200.0)
    rating_fun: Mapped[float] = mapped_column(Float, default=1200.0)  # 종합적인 재미

    # 신뢰도 지표
    matches_played: Mapped[int] = mapped_column(Integer, default=0)

    # 레거시 데이터 참고용
    original_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)

    @property
    def total_score(self) -> float:
        """가중치가 적용된 종합 점수 계산 (읽기 전용 프로퍼티)"""
        return (
            self.rating_story * 1.2
            + self.rating_visual * 1.0
            + self.rating_ost * 0.8
            + self.rating_voice * 0.8
            + self.rating_char * 1.0
            + self.rating_fun * 1.2
        ) / 6.0
