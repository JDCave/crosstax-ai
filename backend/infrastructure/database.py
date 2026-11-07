"""SQLAlchemy 2.0 async engine and session factory."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.core.config import get_settings

settings = get_settings()
db = settings.database

engine: AsyncEngine = create_async_engine(
    db.url,
    pool_size=db.pool_size,
    max_overflow=db.max_overflow,
    pool_recycle=db.pool_recycle,
    pool_pre_ping=db.pool_pre_ping,
    echo=db.echo,
    execution_options={"schema_translate_map": {"crosstax": None}} if db.url.startswith("sqlite") else {},
)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def create_worker_database() -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    """Independent worker uses at most one connection (API should use two)."""
    worker_engine = create_async_engine(
        db.url, pool_size=1, max_overflow=0, pool_recycle=db.pool_recycle,
        pool_pre_ping=db.pool_pre_ping, echo=False,
        execution_options={"schema_translate_map": {"crosstax": None}} if db.url.startswith("sqlite") else {},
    )
    return worker_engine, async_sessionmaker(worker_engine, expire_on_commit=False)
