# main.py
import secrets
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Request, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

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

# Include Routers
app.include_router(battle.router)
app.include_router(ranking.router)
app.include_router(manage.router)


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
