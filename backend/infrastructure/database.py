"""SQLAlchemy 2.0 async engine and session factory."""

from __future__ import annotations

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
)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncSession:  # type: ignore[misc]
    """FastAPI dependency that yields an async database session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
