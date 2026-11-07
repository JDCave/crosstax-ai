"""Public two-step task API for the upstream audit pipeline."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Response

from backend.api.routes.rule_engine import RuleAPIRoute
from backend.api.schemas.rule_engine import ErrorResponse
from backend.api.schemas.rule_tasks import TaskRequest, TaskResponse
from backend.services.rule_tasks import TaskService, get_task_service

router = APIRouter(
    prefix="/api/v1/rule-engine/tasks",
    tags=["rule-engine"],
    route_class=RuleAPIRoute,
    responses={status: {"model": ErrorResponse} for status in (404, 409, 410, 413, 422, 503)},
)
Service = Annotated[TaskService, Depends(get_task_service)]
Key = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        min_length=16,
        max_length=128,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Opaque random key; reuse for transport retries",
    ),
]


@router.post("", status_code=202, response_model=TaskResponse, summary="Persist a validation task")
async def submit(payload: TaskRequest, response: Response, service: Service, idempotency_key: Key) -> TaskResponse:
    result = await service.submit(payload, idempotency_key)
    response.headers["Location"] = f"/api/v1/rule-engine/tasks/{result.task_id}"
    response.headers["Retry-After"] = "1"
    response.headers["Cache-Control"] = "no-store"
    return result


@router.get("/{task_id}", response_model=TaskResponse, summary="Poll validation status and retrieve its result")
async def get_task(task_id: UUID, response: Response, service: Service) -> TaskResponse:
    result = await service.get(str(task_id))
    response.headers["Cache-Control"] = "no-store"
    if result.poll_after_ms:
        response.headers["Retry-After"] = "1"
    return result
