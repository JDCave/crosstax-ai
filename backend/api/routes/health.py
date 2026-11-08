"""Health check endpoints for liveness and readiness probes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database import get_session

router = APIRouter()


@router.get("/health", summary="Liveness probe")
async def health() -> dict[str, str]:
    """Return OK if the service is running."""
    return {"status": "ok"}


@router.get("/ready", summary="Readiness probe")
async def ready(session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    """Return OK if the service and its dependencies are ready."""
    try:
        await session.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail=f"Database unavailable: {exc}") from exc
