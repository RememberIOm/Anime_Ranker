# services.py
import math
import random
import os
import pandas as pd
from typing import Tuple, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_
from sqlalchemy.sql.expression import func as sql_func

from models import Anime
from config import settings


# --- Elo Calculation Logic ---


def get_dynamic_k_factor(matches_played: int) -> float:
    """
    매치 횟수에 따라 K-Factor를 동적으로 계산합니다 (Logistic Decay).
    Formula: K = K_min + (K_max - K_min) * exp(-matches / decay)
    """
    k_diff = settings.ELO_K_MAX - settings.ELO_K_MIN
    decay = math.exp(-matches_played / settings.ELO_DECAY_FACTOR)
    return settings.ELO_K_MIN + k_diff * decay


def calculate_expected_score(rating_a: float, rating_b: float) -> float:
    """
    로지스틱 곡선을 이용한 승률 기대값 계산 (Win + 0.5 * Draw).
    Standard Elo Formula: E_a = 1 / (1 + 10^((Rb - Ra) / 400))
    """
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))


def get_match_probabilities(rating_a: float, rating_b: float) -> Dict[str, float]:
    """
    UI 표시용: 두 점수 차이에 기반하여 승리(A), 무승부, 패배(B승리) 확률을 계산합니다.
    """
    # 1. Elo Expected Score (승리 기댓값)
    expected_a = calculate_expected_score(rating_a, rating_b)

    # 2. 무승부 확률 추정 (Gaussian Function)
    # 점수 차(delta)가 클수록 0에 수렴하며, SCALE 값이 작을수록 더 빨리 0이 됨
    delta = abs(rating_a - rating_b)
    p_draw = settings.ELO_DRAW_MAX * math.exp(-((delta / settings.ELO_DRAW_SCALE) ** 2))

    # 3. 승리/패배 확률 분리
    # E_a = P(Win_A) + 0.5 * P(Draw)
    # Therefore: P(Win_A) = E_a - 0.5 * P(Draw)
    p_win_a = max(0.0, expected_a - 0.5 * p_draw)

    # P(Win_B) = (1 - E_a) - 0.5 * P(Draw)
    expected_b = 1.0 - expected_a
    p_win_b = max(0.0, expected_b - 0.5 * p_draw)

    # 4. 정규화 (합이 정확히 100%가 되도록 보정)
    total_prob = p_win_a + p_draw + p_win_b
    if total_prob == 0:  # 방어 코드
        return {"win_a": 0.0, "draw": 100.0, "win_b": 0.0}

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
) -> Tuple[float, float]:
    """
    Elo Rating 업데이트 계산 (K-Factor 적용)
    """
    expected_a = calculate_expected_score(rating_a, rating_b)
    expected_b = calculate_expected_score(rating_b, rating_a)

    k_a = get_dynamic_k_factor(matches_a)
    k_b = get_dynamic_k_factor(matches_b)

    new_rating_a = rating_a + k_a * (actual_score - expected_a)
    new_rating_b = rating_b + k_b * ((1.0 - actual_score) - expected_b)

    return new_rating_a, new_rating_b


# --- Database Services ---


async def load_initial_data(db: AsyncSession) -> None:
    """DB 초기화: 데이터가 없을 시 CSV 로드"""
    result = await db.execute(select(sql_func.count(Anime.id)))
    count = result.scalar()

    if count == 0 and os.path.exists("animation.csv"):
        print("CSV 데이터를 로드합니다...")
        try:
            df = pd.read_csv("animation.csv")
            for _, row in df.iterrows():
                # 초기 점수 변환 로직 (기존 7.0점 기준 1200점)
                base_score = 1200.0 + (float(row.get("총점", 7.0)) - 7.0) * 100.0
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
    [백그라운드 작업] 점수 인플레이션/디플레이션 방지 보정 (Mean Reversion)
    전체 평균을 1200으로 강제 조정하여 점수가 무한히 팽창하는 것을 막습니다.
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

            # 평균 편차가 1.0 이상일 때만 보정 수행
            if abs(diff) > 1.0:
                is_modified = True
                # SQL Bulk Update가 ORM 객체 순회보다 효율적
                await db.execute(
                    update(Anime).values({attr_name: getattr(Anime, attr_name) - diff})
                )

        if is_modified:
            await db.commit()


async def get_match_pair(
    db: AsyncSession, focus_id: Optional[int] = None
) -> Tuple[Optional[Anime], Optional[Anime]]:
    """
    대결 상대를 선정합니다 (Smart Match + Random).
    점수 차가 적절한(MATCH_SCORE_RANGE) 상대를 우선 매칭하여 데이터 품질을 높입니다.
    """
    # 1. 첫 번째 애니메이션 선택
    if focus_id:
        anime1 = await db.get(Anime, focus_id)
        if not anime1:
            return None, None
    else:
        # 완전 랜덤 선택 (Bias 방지)
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

        # 범위 내 랜덤 선택
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

    # Smart Match 실패 시 (범위 내 상대 없음) 혹은 Random Match 모드일 때
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
