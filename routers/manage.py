# routers/manage.py
from typing import Annotated
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, update

from database import get_db
from models import Anime

router = APIRouter(prefix="/manage", tags=["manage"])
templates = Jinja2Templates(directory="templates")

# Annotated Type Hint
SessionDep = Annotated[AsyncSession, Depends(get_db)]


@router.get("", response_class=HTMLResponse)
async def manage_page(request: Request, db: SessionDep):
    result = await db.execute(select(Anime).order_by(Anime.name))
    animes = result.scalars().all()
    return templates.TemplateResponse(
        "manage.html", {"request": request, "animes": animes}
    )


@router.post("/add")
async def add_anime(db: SessionDep, name: str = Form(...)):
    if not name.strip():
        return RedirectResponse(url="/manage", status_code=303)

    new_anime = Anime(name=name.strip())
    db.add(new_anime)
    await db.commit()
    return RedirectResponse(url="/manage", status_code=303)


@router.post("/delete")
async def delete_anime(db: SessionDep, anime_id: int = Form(...)):
    await db.execute(delete(Anime).where(Anime.id == anime_id))
    await db.commit()
    return RedirectResponse(url="/manage", status_code=303)


@router.post("/edit")
async def edit_anime(
    db: SessionDep, anime_id: int = Form(...), new_name: str = Form(...)
):
    if not new_name.strip():
        return RedirectResponse(url="/manage", status_code=303)

    stmt = update(Anime).where(Anime.id == anime_id).values(name=new_name.strip())
    await db.execute(stmt)
    await db.commit()
    return RedirectResponse(url="/manage", status_code=303)
