"""Isolated opt-in demonstration and token-protected schema initialization."""

import asyncio
import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Response

from backend.api.routes.rule_engine import RuleAPIRoute
from backend.api.schemas.competition import InitializationRequest, InitializationResult, UpgradeDemo
from backend.core.competition import get_demo_settings, get_setup_settings
from backend.infrastructure.exceptions import AppException
from backend.services.competition import (
    InitializationService,
    get_initialization_service,
    upgrade_demo,
)


def require_demo() -> None:
    if not get_demo_settings().enabled:
        raise AppException(404, "NOT_FOUND", "Not found")


def require_setup(token: Annotated[str | None, Header(alias="X-Setup-Token")] = None) -> None:
    settings = get_setup_settings()
    if not settings.enabled:
        raise AppException(404, "NOT_FOUND", "Not found")
    expected = settings.token.get_secret_value()
    if len(expected) < 24:
        raise AppException(503, "SETUP_NOT_CONFIGURED", "Initialization token must be configured")
    if token is None or not hmac.compare_digest(token.encode(), expected.encode()):
        raise AppException(403, "SETUP_FORBIDDEN", "Invalid initialization token")


demo_router = APIRouter(
    prefix="/api/v1/rule-engine/demo",
    tags=["competition-demo"],
    route_class=RuleAPIRoute,
    dependencies=[Depends(require_demo)],
)
setup_router = APIRouter(
    prefix="/api/v1/rule-engine/setup",
    tags=["internal-initialization"],
    route_class=RuleAPIRoute,
    dependencies=[Depends(require_setup)],
)


@demo_router.get("/upgrade-impact", response_model=UpgradeDemo)
async def simulated_upgrade(response: Response) -> UpgradeDemo:
    response.headers["Cache-Control"] = "no-store"
    return await asyncio.to_thread(upgrade_demo)


@setup_router.post("/initialize", response_model=InitializationResult, include_in_schema=False)
async def initialize(
    payload: InitializationRequest,
    response: Response,
    service: Annotated[InitializationService, Depends(get_initialization_service)],
) -> InitializationResult:
    response.headers["Cache-Control"] = "no-store"
    return await service.initialize()
