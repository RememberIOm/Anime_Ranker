# services.py
import math
import random
import os
import pandas as pd
from typing import Tuple, Dict, Optional, Any
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
    expected_a = calculate_expected_score(rating_a, rating_b)
    delta = abs(rating_a - rating_b)

    # 무승부 확률 추정
    p_draw = settings.ELO_DRAW_MAX * math.exp(-((delta / settings.ELO_DRAW_SCALE) ** 2))

    # 승리/패배 확률 분리
    p_win_a = max(0.0, expected_a - 0.5 * p_draw)

    expected_b = 1.0 - expected_a
    p_win_b = max(0.0, expected_b - 0.5 * p_draw)

    # 정규화
    total_prob = p_win_a + p_draw + p_win_b
    if total_prob == 0:
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


async def get_anime_rank_info(
    db: AsyncSession, category: str, score: float
) -> Dict[str, Any]:
    """
    특정 카테고리 점수를 기준으로 해당 점수의 등수와 상위 퍼센트를 계산합니다.
    """
    # 전체 개수
    total_query = select(sql_func.count(Anime.id))
    total_result = await db.execute(total_query)
    total_count = total_result.scalar() or 1  # 0 나누기 방지

    # 나보다 점수가 높은 항목의 개수 (Standard Competition Ranking: 1 2 2 4...)
    # getattr(Anime, f"rating_{category}") 대신 동적 컬럼 매핑이 필요하나,
    # SQLAlchemy Core 레벨에서는 리터럴 컬럼명 사용이 복잡하므로 로직으로 처리.
    # 여기서는 단순화를 위해 모든 항목을 가져오는 대신 SQL count를 사용합니다.

    target_col = getattr(Anime, f"rating_{category}")
    rank_query = select(sql_func.count(Anime.id)).where(target_col > score)
    rank_result = await db.execute(rank_query)
    higher_rank_count = rank_result.scalar()

    current_rank = higher_rank_count + 1
    percentile = (current_rank / total_count) * 100.0

    return {
        "rank": current_rank,
        "total": total_count,
        "top_percent": round(percentile, 1),
    }


async def load_initial_data(db: AsyncSession) -> None:
    """DB 초기화: 데이터가 없을 시 CSV 로드"""
    result = await db.execute(select(sql_func.count(Anime.id)))
    count = result.scalar()

    if count == 0 and os.path.exists("animation.csv"):
        print("CSV 데이터를 로드합니다...")
        try:
            df = pd.read_csv("animation.csv")
            for _, row in df.iterrows():
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
    """[백그라운드 작업] 점수 인플레이션 방지 (Mean Reversion)"""
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
                await db.execute(
                    update(Anime).values({attr_name: getattr(Anime, attr_name) - diff})
                )

        if is_modified:
            await db.commit()


async def get_match_pair(
    db: AsyncSession, focus_id: Optional[int] = None
) -> Tuple[Optional[Anime], Optional[Anime]]:
    """대결 상대를 선정합니다 (Smart Match + Random)."""
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
