# database.py
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base

# 환경 변수 DB_PATH가 있으면 사용하고, 없으면 현재 디렉토리의 anime_rank.db 사용
# Fly.io Volume을 /data에 마운트할 예정이므로 서버에서는 /data/anime_rank.db가 됩니다.
DB_PATH = os.getenv("DB_PATH", "./anime_rank.db")
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session