# routers/battle.py
import random
from typing import Annotated
from fastapi import APIRouter, Depends, Request, Form, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db, AsyncSessionLocal
from models import Anime
from schemas import VoteResponse
from services import (
    get_match_pair,
    calculate_elo_update,
    normalize_scores_task,
    get_match_probabilities,
    get_anime_rank_info,
)

router = APIRouter(prefix="/battle", tags=["battle"])
templates = Jinja2Templates(directory="templates")

SessionDep = Annotated[AsyncSession, Depends(get_db)]

CATEGORIES = [
    ("story", "스토리"),
    ("visual", "작화"),
    ("ost", "OST"),
    ("voice", "성우"),
    ("char", "캐릭터"),
    ("fun", "종합적인 재미"),
]


@router.get("", response_class=HTMLResponse)
async def get_battle(request: Request, db: SessionDep):
    anime1, anime2 = await get_match_pair(db)

    if not anime1 or not anime2:
        return HTMLResponse(
            content="""
            <div style='text-align:center; padding:50px;'>
                <h2>데이터가 부족합니다.</h2>
                <p>관리자 페이지에서 애니메이션을 추가해주세요.</p>
                <a href='/manage'>관리 페이지로 이동</a>
            </div>
            """,
            status_code=200,
        )

    selected_category = random.choice(CATEGORIES)
    category_key = selected_category[0]

    # 점수 가져오기
    r1 = getattr(anime1, f"rating_{category_key}")
    r2 = getattr(anime2, f"rating_{category_key}")

    # 확률 및 등수 정보 계산
    probs = get_match_probabilities(r1, r2)
    rank1 = await get_anime_rank_info(db, category_key, r1)
    rank2 = await get_anime_rank_info(db, category_key, r2)

    return templates.TemplateResponse(
        "battle.html",
        {
            "request": request,
            "anime1": anime1,
            "anime2": anime2,
            "category_key": category_key,
            "category_name": selected_category[1],
            "probs": probs,
            "rank1": rank1,
            "rank2": rank2,
        },
    )


@router.get("/focus/{anime_id}", response_class=HTMLResponse)
async def focus_battle(anime_id: int, request: Request, db: SessionDep):
    anime1, anime2 = await get_match_pair(db, focus_id=anime_id)

    if not anime1:
        return HTMLResponse("존재하지 않는 애니메이션입니다.", status_code=404)
    if not anime2:
        return HTMLResponse("상대할 애니메이션 데이터가 부족합니다.", status_code=200)

    selected_category = random.choice(CATEGORIES)
    category_key = selected_category[0]

    r1 = getattr(anime1, f"rating_{category_key}")
    r2 = getattr(anime2, f"rating_{category_key}")

    probs = get_match_probabilities(r1, r2)
    rank1 = await get_anime_rank_info(db, category_key, r1)
    rank2 = await get_anime_rank_info(db, category_key, r2)

    return templates.TemplateResponse(
        "battle.html",
        {
            "request": request,
            "anime1": anime1,
            "anime2": anime2,
            "category_key": category_key,
            "category_name": selected_category[1],
            "focus_mode": True,
            "focus_id": anime_id,
            "probs": probs,
            "rank1": rank1,
            "rank2": rank2,
        },
    )


@router.post("/vote", response_model=VoteResponse)
async def vote(
    request: Request,
    background_tasks: BackgroundTasks,
    db: SessionDep,
    anime1_id: int = Form(...),
    anime2_id: int = Form(...),
    category: str = Form(...),
    winner: str = Form(...),
    redirect_to: str = Form(None),
):
    a1 = await db.get(Anime, anime1_id)
    a2 = await db.get(Anime, anime2_id)

    if not a1 or not a2:
        return JSONResponse({"error": "Anime not found"}, status_code=404)

    attr_name = f"rating_{category}"
    old_r1 = getattr(a1, attr_name)
    old_r2 = getattr(a2, attr_name)

    # 1. 변경 전 등수 계산
    info1_old = await get_anime_rank_info(db, category, old_r1)
    info2_old = await get_anime_rank_info(db, category, old_r2)

    # 2. 점수 업데이트 계산
    if winner == "1":
        actual_score = 1.0
    elif winner == "2":
        actual_score = 0.0
    else:
        actual_score = 0.5

    new_r1, new_r2 = calculate_elo_update(
        old_r1, old_r2, actual_score, a1.matches_played, a2.matches_played
    )

    setattr(a1, attr_name, new_r1)
    setattr(a2, attr_name, new_r2)
    a1.matches_played += 1
    a2.matches_played += 1

    await db.commit()

    # 3. 변경 후 등수 계산 (주의: DB에 반영된 새 점수를 기준으로 재조회 필요)
    # 다만 여기서는 count 쿼리이므로, 다른 애니메이션 점수는 그대로라고 가정하고
    # a1, a2의 점수만 변동된 상태에서 쿼리를 날립니다.
    # 이미 commit을 했으므로 DB에는 새 점수가 반영되어 있습니다.

    info1_new = await get_anime_rank_info(db, category, new_r1)
    info2_new = await get_anime_rank_info(db, category, new_r2)

    background_tasks.add_task(normalize_scores_task, AsyncSessionLocal)

    response_data = {
        "a1_id": a1.id,
        "a2_id": a2.id,
        "old_r1": round(old_r1),
        "new_r1": round(new_r1),
        "diff_r1": round(new_r1 - old_r1),
        "old_r2": round(old_r2),
        "new_r2": round(new_r2),
        "diff_r2": round(new_r2 - old_r2),
        # Rank Info
        "old_rank_1": info1_old["rank"],
        "new_rank_1": info1_new["rank"],
        "old_rank_2": info2_old["rank"],
        "new_rank_2": info2_new["rank"],
        "total_animes": info1_old["total"],
        "next_url": redirect_to if redirect_to else "/battle",
    }

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JSONResponse(response_data)

    return RedirectResponse(url=response_data["next_url"], status_code=303)
