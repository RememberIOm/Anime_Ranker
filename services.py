# services.py
import math
import random
import pandas as pd
import os
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, and_, or_
from sqlalchemy.sql.expression import func as sql_func

from models import Anime
from config import settings


# --- Elo Calculation Logic ---


def get_dynamic_k_factor(matches_played: int) -> float:
    """
    매치 횟수에 따라 K-Factor를 동적으로 계산합니다.
    초반에는 높고(빠른 자리 잡기), 후반에는 낮아집니다(안정화).
    Formula: K = K_min + (K_max - K_min) * exp(-matches / decay)
    """
    k_diff = settings.ELO_K_MAX - settings.ELO_K_MIN
    decay = math.exp(-matches_played / settings.ELO_DECAY_FACTOR)
    return settings.ELO_K_MIN + k_diff * decay


def calculate_expected_score(rating_a: float, rating_b: float) -> float:
    """
    로지스틱 곡선을 이용한 승률 기대값 계산
    """
    return 1 / (1 + 10 ** ((rating_b - rating_a) / 400))


def calculate_elo_update(
    rating_a: float,
    rating_b: float,
    actual_score: float,  # 1.0 (Win), 0.5 (Draw), 0.0 (Lose)
    matches_a: int,
    matches_b: int,
) -> tuple[float, float]:
    """
    Elo Rating 업데이트 계산
    """
    expected_a = calculate_expected_score(rating_a, rating_b)
    expected_b = calculate_expected_score(rating_b, rating_a)

    k_a = get_dynamic_k_factor(matches_a)
    k_b = get_dynamic_k_factor(matches_b)

    new_rating_a = rating_a + k_a * (actual_score - expected_a)
    new_rating_b = rating_b + k_b * ((1 - actual_score) - expected_b)

    return new_rating_a, new_rating_b


# --- Database Services ---


async def load_initial_data(db: AsyncSession) -> None:
    """DB 초기화: 데이터가 없을 시 CSV 로드"""
    result = await db.execute(select(func.count(Anime.id)))
    count = result.scalar()

    if count == 0 and os.path.exists("animation.csv"):
        print("CSV 데이터를 로드합니다...")
        try:
            df = pd.read_csv("animation.csv")
            for _, row in df.iterrows():
                # 기존 평점을 Elo 1200 기준으로 변환 (대략적인 매핑)
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


async def normalize_scores_task(db_factory) -> None:
    """
    [백그라운드 작업]
    전체 평균 점수가 1200점에서 너무 벗어나지 않도록 보정합니다. (인플레이션/디플레이션 방지)
    사용자 경험을 해치지 않기 위해 미세한 조정만 수행합니다.
    """
    async with db_factory() as db:
        categories = ["story", "visual", "ost", "voice", "char", "fun"]
        is_modified = False

        # 통계 쿼리
        # (실제 서비스에서는 캐싱하거나 매번 돌리지 않는 것이 좋음)
        result = await db.execute(select(Anime))
        animes = result.scalars().all()

        if not animes:
            return

        for cat in categories:
            attr_name = f"rating_{cat}"
            total_val = sum(getattr(a, attr_name) for a in animes)
            current_avg = total_val / len(animes)
            diff = current_avg - 1200.0

            # 평균이 1점 이상 차이나면 보정 실행 (너무 잦은 보정 방지)
            if abs(diff) > 1.0:
                is_modified = True
                # SQL 차원에서 일괄 업데이트 (Python Loop보다 효율적)
                stmt = update(Anime).values(
                    {attr_name: getattr(Anime, attr_name) - diff}
                )
                await db.execute(stmt)

        if is_modified:
            await db.commit()


async def get_match_pair(
    db: AsyncSession, focus_id: int | None = None
) -> tuple[Anime | None, Anime | None]:
    """
    대결 상대를 선정합니다.
    1. Focus 모드: 해당 ID와 적절한 상대를 매칭.
    2. 일반 모드:
       - 80% 확률: 점수대가 비슷한 '라이벌' 매칭 (Smart Match).
       - 20% 확률: 완전 랜덤 매칭 (랭킹 고착화 방지).
    """
    # 1. 첫 번째 애니메이션 선택 (Anime A)
    if focus_id:
        anime1 = await db.get(Anime, focus_id)
        if not anime1:
            return None, None
    else:
        # 무작위로 하나 선택
        # (개선점: 매치 수가 적은 애니메이션을 우선 노출하는 로직을 추가할 수도 있음)
        query = select(Anime).order_by(sql_func.random()).limit(1)
        result = await db.execute(query)
        anime1 = result.scalar()

    if not anime1:
        return None, None

    # 2. 두 번째 애니메이션 선택 (Anime B)
    # Smart Match 여부 결정 (Focus 모드거나, 랜덤 확률에 당첨될 경우)
    use_smart_match = random.random() < settings.MATCH_SMART_RATE
    anime2 = None

    if use_smart_match:
        # Anime A의 종합 점수 기준으로 ±Range 내의 상대 검색
        # 단, 카테고리가 랜덤으로 정해지므로 total_score 대신 평균적인 매칭을 위해 total_score 프로퍼티 사용 불가
        # DB 레벨 계산이 복잡하므로, 가장 최근 갱신된 rating_fun(종합재미) 혹은 단순 랜덤성을 섞음.
        # 여기서는 rating_fun(종합 재미)이 대표성이 있다고 가정하고 이를 기준으로 범위 검색.
        target_score = anime1.rating_fun
        min_score = target_score - settings.MATCH_SCORE_RANGE
        max_score = target_score + settings.MATCH_SCORE_RANGE

        query = (
            select(Anime)
            .where(
                and_(
                    Anime.id != anime1.id,
                    Anime.rating_fun >= min_score,
                    Anime.rating_fun <= max_score,
                )
            )
            .order_by(sql_func.random())
            .limit(1)
        )
        result = await db.execute(query)
        anime2 = result.scalar()

    # Smart Match 대상을 못 찾았거나(범위 밖), 랜덤 매칭 턴인 경우
    if not anime2:
        query = (
            select(Anime)
            .where(Anime.id != anime1.id)
            .order_by(sql_func.random())
            .limit(1)
        )
        result = await db.execute(query)
        anime2 = result.scalar()

    return anime1, anime2
