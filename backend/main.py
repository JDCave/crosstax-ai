"""FastAPI application factory, lifespan, and middleware registration."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend import __version__
from backend.api.routes import health
from backend.core.config import Settings, get_settings
from backend.core.logging.config import setup_logging
from backend.core.logging.middleware import RequestIdMiddleware
from backend.infrastructure.database import engine
from backend.infrastructure.exceptions import register_exception_handlers

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage startup and shutdown lifecycle."""
    settings = get_settings()
    setup_logging(settings.log_level, settings.log_format)
    logger.info("Starting CrossTax AI v%s (env=%s)", __version__, settings.environment)
    yield
    await engine.dispose()
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="CrossTax AI",
        version=__version__,
        description="CRS exemption determination AI system",
        lifespan=lifespan,
    )

    _register_middleware(app, settings)
    _register_routers(app)
    register_exception_handlers(app)

    return app


def _register_middleware(app: FastAPI, settings: Settings) -> None:
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def _register_routers(app: FastAPI) -> None:
    app.include_router(health.router, tags=["health"])


app = create_app()
