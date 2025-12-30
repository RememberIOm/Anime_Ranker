# database.py
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from config import settings

DATABASE_URL = f"sqlite+aiosqlite:///{settings.DB_PATH}"

# check_same_thread=False is needed for SQLite with asyncio
engine = create_async_engine(
    DATABASE_URL, echo=False, connect_args={"check_same_thread": False}
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
