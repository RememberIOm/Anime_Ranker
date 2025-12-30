# main.py
import secrets
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Request, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.exception_handlers import (
    http_exception_handler as default_http_exception_handler,
)

from config import settings
from database import engine, Base, AsyncSessionLocal
from services import load_initial_data
from routers import battle, ranking, manage

# --- Security ---
security = HTTPBasic()


def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    """Constant-time comparison for HTTP Basic Auth"""
    current_username_bytes = credentials.username.encode("utf8")
    correct_username_bytes = settings.AUTH_USERNAME.encode("utf8")
    is_correct_username = secrets.compare_digest(
        current_username_bytes, correct_username_bytes
    )

    current_password_bytes = credentials.password.encode("utf8")
    correct_password_bytes = settings.AUTH_PASSWORD.encode("utf8")
    is_correct_password = secrets.compare_digest(
        current_password_bytes, correct_password_bytes
    )

    if not (is_correct_username and is_correct_password):
        # 브라우저가 로그인 창을 띄우게 하려면 WWW-Authenticate 헤더가 필수입니다.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


# --- Lifespan ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        await load_initial_data(session)

    yield

    # Shutdown
    await engine.dispose()


# --- App Init ---
app = FastAPI(lifespan=lifespan, dependencies=[Depends(verify_credentials)])
templates = Jinja2Templates(directory="templates")


# --- Custom Exception Handlers ---
@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    """
    HTTPException(특히 401) 발생 시 브라우저 요청이면 HTML 페이지를 반환합니다.
    """
    if exc.status_code == status.HTTP_401_UNAUTHORIZED:
        # Accept 헤더에 'text/html'이 포함된 경우 (브라우저 접근)
        if "text/html" in request.headers.get("accept", ""):
            return templates.TemplateResponse(
                "401.html",
                {"request": request},
                status_code=exc.status_code,
                # WWW-Authenticate 헤더를 유지해야 브라우저가 상황을 인지합니다.
                # 다만 사용자가 '취소'를 누른 후에는 페이지 본문이 보입니다.
                headers=exc.headers,
            )

    # 그 외의 경우(API 요청 등)는 기본 핸들러(JSON) 사용
    return await default_http_exception_handler(request, exc)


# Include Routers
app.include_router(battle.router)
app.include_router(ranking.router)
app.include_router(manage.router)


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
