# routers/ranking.py
from typing import Annotated
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_db
from models import Anime

router = APIRouter(prefix="/ranking", tags=["ranking"])
templates = Jinja2Templates(directory="templates")


@router.get("", response_class=HTMLResponse)
async def get_ranking(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    sort_by: str = "total",
):
    # 읽기 전용 트랜잭션 최적화
    result = await db.execute(select(Anime))
    animes = result.scalars().all()

    if not animes:
        return templates.TemplateResponse(
            "ranking.html",
            {
                "request": request,
                "animes": [],
                "sort_by": sort_by,
                "chart_data": {"labels": [], "counts": [], "category": ""},
            },
        )

    # Prepare list for template
    ranked_list = []
    for a in animes:
        ranked_list.append(
            {
                "name": a.name,
                "total": round(a.total_score, 1),
                "story": round(a.rating_story, 1),
                "visual": round(a.rating_visual, 1),
                "ost": round(a.rating_ost, 1),
                "voice": round(a.rating_voice, 1),
                "char": round(a.rating_char, 1),
                "fun": round(a.rating_fun, 1),
                "matches": a.matches_played,
            }
        )

    # Sorting Logic
    ranked_list.sort(key=lambda x: x.get(sort_by, 0), reverse=True)

    # Chart Data Preparation (Histogram)
    target_key = sort_by
    scores = [x[target_key] for x in ranked_list]

    # 동적 범위 설정 (데이터 분포에 따라)
    min_s = math_floor(min(scores)) if scores else 800
    max_s = math_ceil(max(scores)) if scores else 1800
    # 50점 단위로 범주화
    min_bucket = (min_s // 50) * 50
    max_bucket = ((max_s // 50) + 1) * 50

    labels = []
    counts = []

    for i in range(min_bucket, max_bucket, 50):
        labels.append(f"{i}")
        count = sum(1 for s in scores if i <= s < i + 50)
        counts.append(count)

    chart_data = {
        "labels": labels,
        "counts": counts,
        "category": target_key.upper() if target_key != "total" else "종합 점수",
    }

    return templates.TemplateResponse(
        "ranking.html",
        {
            "request": request,
            "animes": ranked_list,
            "sort_by": sort_by,
            "chart_data": chart_data,
        },
    )


def math_floor(x):
    return int(x)


def math_ceil(x):
    return int(x) + 1
