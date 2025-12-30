# services.py
import math
import random
import pandas as pd
import os
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, and_
from sqlalchemy.sql.expression import func as sql_func

from models import Anime
from config import settings


# --- Elo Calculation Logic ---


def get_dynamic_k_factor(matches_played: int) -> float:
    """
    매치 횟수에 따라 K-Factor를 동적으로 계산합니다.
    Formula: K = K_min + (K_max - K_min) * exp(-matches / decay)
    """
    k_diff = settings.ELO_K_MAX - settings.ELO_K_MIN
    decay = math.exp(-matches_played / settings.ELO_DECAY_FACTOR)
    return settings.ELO_K_MIN + k_diff * decay


def calculate_expected_score(rating_a: float, rating_b: float) -> float:
    """
    로지스틱 곡선을 이용한 승률 기대값 계산 (E_a)
    E_a = P(Win) + 0.5 * P(Draw)
    """
    return 1 / (1 + 10 ** ((rating_b - rating_a) / 400))


def get_match_probabilities(rating_a: float, rating_b: float) -> dict[str, float]:
    """
    두 점수 차이에 기반하여 승리(A), 무승부, 패배(B승리) 확률을 계산합니다.
    Draw 확률은 점수 차가 0일 때 최대값(ELO_DRAW_MAX)을 가지며, 차이가 클수록 줄어듭니다.
    """
    # 1. Elo Expected Score (승리 기댓값: 승리 + 절반의 무승부)
    expected_a = calculate_expected_score(rating_a, rating_b)

    # 2. 무승부 확률 추정 (Gaussian Function)
    # 점수 차이가 클수록 무승부 확률은 0에 수렴
    delta = abs(rating_a - rating_b)
    p_draw = settings.ELO_DRAW_MAX * math.exp(-((delta / settings.ELO_DRAW_SCALE) ** 2))

    # 3. 승리/패배 확률 분리
    # E_a = P(Win_A) + 0.5 * P(Draw)
    # 따라서 P(Win_A) = E_a - 0.5 * P(Draw)
    p_win_a = max(0.0, expected_a - 0.5 * p_draw)

    # P(Win_B)도 동일한 방식으로 계산 (expected_b = 1 - expected_a)
    expected_b = 1.0 - expected_a
    p_win_b = max(0.0, expected_b - 0.5 * p_draw)

    # 4. 정규화 (합이 정확히 100%가 되도록 조정)
    total_prob = p_win_a + p_draw + p_win_b

    return {
        "win_a": round((p_win_a / total_prob) * 100, 1),
        "draw": round((p_draw / total_prob) * 100, 1),
        "win_b": round((p_win_b / total_prob) * 100, 1),
    }


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
    [백그라운드 작업] 점수 인플레이션/디플레이션 방지 보정
    """
    async with db_factory() as db:
        categories = ["story", "visual", "ost", "voice", "char", "fun"]
        is_modified = False

        result = await db.execute(select(Anime))
        animes = result.scalars().all()

        if not animes:
            return

        for cat in categories:
            attr_name = f"rating_{cat}"
            total_val = sum(getattr(a, attr_name) for a in animes)
            current_avg = total_val / len(animes)
            diff = current_avg - 1200.0

            if abs(diff) > 1.0:
                is_modified = True
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
    대결 상대를 선정합니다 (Smart Match + Random).
    """
    # 1. 첫 번째 애니메이션 선택
    if focus_id:
        anime1 = await db.get(Anime, focus_id)
        if not anime1:
            return None, None
    else:
        query = select(Anime).order_by(sql_func.random()).limit(1)
        result = await db.execute(query)
        anime1 = result.scalar()

    if not anime1:
        return None, None

    # 2. 두 번째 애니메이션 선택 (Smart Match 로직)
    use_smart_match = random.random() < settings.MATCH_SMART_RATE
    anime2 = None

    if use_smart_match:
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
