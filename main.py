# main.py
from fastapi import FastAPI, Depends, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete, update
from sqlalchemy.sql.expression import func as sql_func
import os
import pandas as pd
import random

from database import engine, Base, get_db
from models import Anime
from rating import update_elo

app = FastAPI()
templates = Jinja2Templates(directory="templates")

@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async with AsyncSession(engine) as session:
        result = await session.execute(select(func.count(Anime.id)))
        count = result.scalar()
        
        if count == 0:
            print("DB가 비어 있습니다.")
            # CSV 파일이 존재할 때만 읽기 시도
            if os.path.exists("animation.csv"):
                print("CSV 데이터를 가져옵니다...")
                df = pd.read_csv("animation.csv")
                for _, row in df.iterrows():
                    base_score = 1200 + (float(row['총점']) - 7.0) * 100 
                    
                    anime = Anime(
                        name=row['이름'],
                        original_rank=row['순위'],
                        rating_story=base_score,
                        rating_visual=base_score,
                        rating_ost=base_score,
                        rating_voice=base_score,
                        rating_char=base_score,
                        rating_fun=base_score
                    )
                    session.add(anime)
                await session.commit()
                print("데이터 로드 완료!")
            else:
                print("주의: animation.csv 파일을 찾을 수 없습니다. 빈 DB로 시작합니다.")

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# --- 대결 시스템 ---
@app.get("/battle", response_class=HTMLResponse)
async def get_battle(request: Request, db: AsyncSession = Depends(get_db)):
    # 랜덤으로 2개 뽑기 (나중에는 비슷한 점수대끼리 뽑는 로직으로 개선 가능)
    # 단순 랜덤보다는 '경기 수가 적은' 애니메이션을 우선 노출하거나,
    # Elo 점수가 비슷한 애니메이션을 매칭하는 것이 좋습니다.
    
    # 여기서는 간단히 랜덤 매칭 구현
    query = await db.execute(select(Anime).order_by(sql_func.random()).limit(2))
    animes = query.scalars().all()
    
    if len(animes) < 2:
        return "애니메이션 데이터가 부족합니다."

    categories = [
        ("story", "스토리"), ("visual", "작화"), ("ost", "OST"), 
        ("voice", "성우"), ("char", "캐릭터"), ("fun", "종합적인 재미")
    ]
    selected_category = random.choice(categories)

    return templates.TemplateResponse("battle.html", {
        "request": request,
        "anime1": animes[0],
        "anime2": animes[1],
        "category_key": selected_category[0],
        "category_name": selected_category[1]
    })

# --- (1) 집중 평가(배치고사) 페이지 라우터 추가 ---
@app.get("/battle/focus/{anime_id}", response_class=HTMLResponse)
async def focus_battle(anime_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    # 1. 주인공(집중 평가 대상) 가져오기
    target_anime = await db.get(Anime, anime_id)
    if not target_anime:
        return "존재하지 않는 애니메이션입니다."

    # 2. 상대방 찾기 (자신 제외 랜덤)
    # 심화: 여기서 target_anime의 점수와 비슷한 상대를 찾으면 더 정교해집니다.
    # 지금은 간단하게 랜덤으로 하되, 자신은 제외합니다.
    query = await db.execute(
        select(Anime).where(Anime.id != anime_id).order_by(sql_func.random()).limit(1)
    )
    opponent = query.scalar()
    
    if not opponent:
        return "상대할 애니메이션 데이터가 부족합니다."

    # 3. 카테고리 랜덤 선정
    categories = [
        ("story", "스토리"), ("visual", "작화"), ("ost", "OST"), 
        ("voice", "성우"), ("char", "캐릭터"), ("fun", "종합적인 재미")
    ]
    selected_category = random.choice(categories)

    # 4. 템플릿 렌더링 (일반 배틀과 동일한 템플릿 사용하되, flag를 넘김)
    return templates.TemplateResponse("battle.html", {
        "request": request,
        "anime1": target_anime,
        "anime2": opponent,
        "category_key": selected_category[0],
        "category_name": selected_category[1],
        "focus_mode": True,      # 집중 모드임을 알림
        "focus_id": anime_id     # 누구를 집중 중인지
    })

# --- (2) 투표 로직 수정 (리다이렉트 처리) ---
@app.post("/battle/vote")
async def vote(
    request: Request,  # Request 객체 추가
    anime1_id: int = Form(...),
    anime2_id: int = Form(...),
    category: str = Form(...),
    winner: str = Form(...),
    redirect_to: str = Form(None),
    db: AsyncSession = Depends(get_db)
):
    a1 = await db.get(Anime, anime1_id)
    a2 = await db.get(Anime, anime2_id)
    
    attr_name = f"rating_{category}"
    old_r1 = getattr(a1, attr_name) # 이전 점수 저장
    old_r2 = getattr(a2, attr_name) # 이전 점수 저장
    
    result_val = 0.5
    if winner == "1": result_val = 1.0
    elif winner == "2": result_val = 0.0
    
    # 점수 업데이트
    new_r1, new_r2 = update_elo(old_r1, old_r2, result_val, a1.matches_played, a2.matches_played)
    
    setattr(a1, attr_name, new_r1)
    setattr(a2, attr_name, new_r2)
    a1.matches_played += 1
    a2.matches_played += 1
    
    await db.commit()
    
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JSONResponse({
            "a1_id": a1.id,
            "a2_id": a2.id,
            "old_r1": round(old_r1),
            "new_r1": round(new_r1),
            "diff_r1": round(new_r1 - old_r1),
            "old_r2": round(old_r2),
            "new_r2": round(new_r2),
            "diff_r2": round(new_r2 - old_r2),
            "next_url": redirect_to if redirect_to else "/battle"
        })

    # 일반 요청이면 기존처럼 리다이렉트
    if redirect_to:
        return RedirectResponse(url=redirect_to, status_code=303)
    else:
        return RedirectResponse(url="/battle", status_code=303)

# --- 랭킹 시스템 ---
@app.get("/ranking", response_class=HTMLResponse)
async def get_ranking(request: Request, sort_by: str = "total", db: AsyncSession = Depends(get_db)):
    # 1. 모든 애니메이션 가져오기
    result = await db.execute(select(Anime))
    animes = result.scalars().all()
    
    if not animes:
        return templates.TemplateResponse("ranking.html", {"request": request, "animes": [], "sort_by": sort_by})

    # --- [신규 추가] 평균 보정 로직 (Inflation 방지) ---
    # 스토리, 작화 등 각 항목별로 평균을 구해서 1200점과의 차이만큼 모든 애니메이션 점수를 이동시킵니다.
    # 이렇게 하면 전체 평균은 항상 1200점으로 유지됩니다.
    
    categories = ['story', 'visual', 'ost', 'voice', 'char', 'fun']
    
    # 변경 사항이 있는지 추적
    is_modified = False 
    
    for cat in categories:
        attr_name = f"rating_{cat}"
        # 해당 카테고리의 현재 평균 계산
        current_avg = sum(getattr(a, attr_name) for a in animes) / len(animes)
        
        # 1200점과의 차이 (예: 평균이 1210점이면 diff는 10)
        diff = current_avg - 1200.0
        
        # 차이가 미세하면 무시 (부동소수점 오차 고려)
        if abs(diff) > 0.1:
            is_modified = True
            for a in animes:
                current_val = getattr(a, attr_name)
                # 모든 애니메이션에서 차이만큼 뺌
                setattr(a, attr_name, current_val - diff)
    
    # 보정된 점수를 DB에 저장 (선택 사항: 조회만 할 거면 commit 안 해도 되지만, 영구 반영하려면 commit)
    if is_modified:
        await db.commit()
    # -----------------------------------------------

    # 2. 랭킹 리스트 생성 (기존 로직)
    ranked_list = []
    for a in animes:
        # 가중치 반영 총점 계산
        total_score = (
            a.rating_story * 1.2 +
            a.rating_visual * 1.0 +
            a.rating_ost * 0.8 +
            a.rating_voice * 0.8 +
            a.rating_char * 1.0 +
            a.rating_fun * 1.2
        ) / 6.0
        
        data = {
            "name": a.name,
            "total": round(total_score, 1),
            "story": round(a.rating_story, 1),
            "visual": round(a.rating_visual, 1),
            "ost": round(a.rating_ost, 1),
            "voice": round(a.rating_voice, 1),
            "char": round(a.rating_char, 1),
            "fun": round(a.rating_fun, 1),
            "matches": a.matches_played
        }
        ranked_list.append(data)
    
    # ... 정렬 및 리턴 (기존 코드와 동일) ...
    if sort_by == "total":
        ranked_list.sort(key=lambda x: x['total'], reverse=True)
    else:
        ranked_list.sort(key=lambda x: x.get(sort_by, 0), reverse=True)

    # --- [신규] 차트 데이터 생성 (분포도) ---
    # 현재 정렬 기준(sort_by)에 대한 점수 분포를 계산합니다.
    # 50점 단위로 구간(Bucket)을 나눕니다.
    
    target_key = sort_by  # total, story, visual ...
    
    # 1. 데이터 추출
    scores = [x[target_key] for x in ranked_list]
    
    # 2. 구간 설정 (예: 800점 ~ 1800점)
    min_score = 800
    max_score = 1800
    step = 50
    labels = []
    counts = []
    
    for i in range(min_score, max_score, step):
        label = f"{i}"
        # 해당 구간에 속하는 애니메이션 수 카운트
        count = sum(1 for s in scores if i <= s < i + step)
        labels.append(label)
        counts.append(count)
        
    # Python 리스트를 그대로 넘기면 템플릿에서 쓰기 편함
    chart_data = {
        "labels": labels,
        "counts": counts,
        "category": target_key.upper() if target_key != "total" else "종합 점수"
    }

    return templates.TemplateResponse("ranking.html", {
        "request": request, 
        "animes": ranked_list,
        "sort_by": sort_by,
        "chart_data": chart_data  # <--- 이 데이터가 추가됨
    })

# --- 관리(Management) 시스템 ---
@app.get("/manage", response_class=HTMLResponse)
async def manage_page(request: Request, db: AsyncSession = Depends(get_db)):
    # 이름순 정렬하여 리스트 가져오기
    result = await db.execute(select(Anime).order_by(Anime.name))
    animes = result.scalars().all()
    
    return templates.TemplateResponse("manage.html", {
        "request": request, 
        "animes": animes
    })

@app.post("/manage/add")
async def add_anime(name: str = Form(...), db: AsyncSession = Depends(get_db)):
    # 공백 제거
    name = name.strip()
    if not name:
        return RedirectResponse(url="/manage", status_code=303)

    # 신규 애니메이션 생성 (기본 점수 1200)
    new_anime = Anime(
        name=name,
        rating_story=1200.0,
        rating_visual=1200.0,
        rating_ost=1200.0,
        rating_voice=1200.0,
        rating_char=1200.0,
        rating_fun=1200.0,
        matches_played=0
    )
    
    db.add(new_anime)
    await db.commit()
    
    return RedirectResponse(url="/manage", status_code=303)

@app.post("/manage/delete")
async def delete_anime(anime_id: int = Form(...), db: AsyncSession = Depends(get_db)):
    # 해당 ID의 애니메이션 삭제
    stmt = delete(Anime).where(Anime.id == anime_id)
    await db.execute(stmt)
    await db.commit()
    
    return RedirectResponse(url="/manage", status_code=303)

@app.post("/manage/edit")
async def edit_anime(
    anime_id: int = Form(...), 
    new_name: str = Form(...), 
    db: AsyncSession = Depends(get_db)
):
    new_name = new_name.strip()
    if not new_name:
        # 빈 이름으로 수정하려 하면 무시하고 리다이렉트
        return RedirectResponse(url="/manage", status_code=303)

    # 비동기 업데이트 쿼리
    stmt = (
        update(Anime)
        .where(Anime.id == anime_id)
        .values(name=new_name)
    )
    await db.execute(stmt)
    await db.commit()
    
    return RedirectResponse(url="/manage", status_code=303)