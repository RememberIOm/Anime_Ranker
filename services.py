# services.py
import math
import pandas as pd
import os
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from sqlalchemy.sql.expression import func as sql_func

from models import Anime
from config import settings


# --- Elo Calculation Logic ---
def get_k_factor(matches_played: int) -> int:
    if matches_played < settings.ELO_PLACEMENT_MATCHES:
        return settings.ELO_K_FACTOR_PLACEMENT
    return settings.ELO_K_FACTOR_DEFAULT


def calculate_expected_score(rating_a: float, rating_b: float) -> float:
    return 1 / (1 + 10 ** ((rating_b - rating_a) / 400))


def calculate_elo_update(
    rating_a: float,
    rating_b: float,
    actual_score: float,
    matches_a: int,
    matches_b: int,
):
    expected_a = calculate_expected_score(rating_a, rating_b)
    expected_b = calculate_expected_score(rating_b, rating_a)

    k_a = get_k_factor(matches_a)
    k_b = get_k_factor(matches_b)

    new_a = rating_a + k_a * (actual_score - expected_a)
    new_b = rating_b + k_b * ((1 - actual_score) - expected_b)

    return new_a, new_b


# --- Database Services ---
async def load_initial_data(db: AsyncSession):
    """DB가 비어있을 경우 CSV에서 데이터를 로드합니다."""
    result = await db.execute(select(func.count(Anime.id)))
    count = result.scalar()

    if count == 0 and os.path.exists("animation.csv"):
        print("CSV 데이터를 로드합니다...")
        try:
            df = pd.read_csv("animation.csv")
            for _, row in df.iterrows():
                base_score = 1200 + (float(row.get("총점", 7.0)) - 7.0) * 100
                anime = Anime(
                    name=row["이름"],
                    original_rank=row.get("순위", 0),
                    rating_story=base_score,
                    rating_visual=base_score,
                    rating_ost=base_score,
                    rating_voice=base_score,
                    rating_char=base_score,
                    rating_fun=base_score,
                )
                db.add(anime)
            await db.commit()
            print("데이터 로드 완료.")
        except Exception as e:
            print(f"데이터 로드 중 오류 발생: {e}")


async def normalize_scores_task(db_factory):
    """
    백그라운드 작업: 전체 평균 점수가 1200점에서 너무 벗어나지 않도록 보정합니다.
    (인플레이션/디플레이션 방지)
    """
    async with db_factory() as db:
        categories = ["story", "visual", "ost", "voice", "char", "fun"]
        is_modified = False

        # 모든 애니메이션 가져오기 (메모리 효율을 위해 필요한 컬럼만 가져오는 것이 좋으나, 로직상 전체 객체 로드)
        result = await db.execute(select(Anime))
        animes = result.scalars().all()

        if not animes:
            return

        for cat in categories:
            attr_name = f"rating_{cat}"
            total_val = sum(getattr(a, attr_name) for a in animes)
            current_avg = total_val / len(animes)
            diff = current_avg - 1200.0

            # 평균이 0.5점 이상 차이나면 보정 실행
            if abs(diff) > 0.5:
                is_modified = True
                stmt = update(Anime).values(
                    {attr_name: getattr(Anime, attr_name) - diff}
                )
                await db.execute(stmt)

        if is_modified:
            await db.commit()


async def get_random_pair(
    db: AsyncSession, focus_id: int | None = None
) -> tuple[Anime | None, Anime | None]:
    """대결 상대를 랜덤하게 선택합니다. Focus 모드일 경우 하나는 고정됩니다."""
    if focus_id:
        anime1 = await db.get(Anime, focus_id)
        if not anime1:
            return None, None

        query = (
            select(Anime)
            .where(Anime.id != focus_id)
            .order_by(sql_func.random())
            .limit(1)
        )
        result = await db.execute(query)
        anime2 = result.scalar()
    else:
        query = select(Anime).order_by(sql_func.random()).limit(2)
        result = await db.execute(query)
        animes = result.scalars().all()
        if len(animes) < 2:
            return None, None
        anime1, anime2 = animes[0], animes[1]

    return anime1, anime2
