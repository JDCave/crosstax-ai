"""Isolated versioned endpoints for teammate-to-engine JSON calls."""

from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy.exc import SQLAlchemyError

from backend.api.schemas.rule_engine import (
    CoverageResponse,
    ErrorResponse,
    RuleVersionResponse,
    ValidationRequest,
    ValidationResponse,
)
from backend.infrastructure.exceptions import AppException
from backend.services.rule_api import RuleAPIService, get_rule_api_service


class RuleAPIRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:  # Framework handler signature.
        original = super().get_route_handler()

        async def bounded_handler(request: Request) -> Response:
            try:
                body = bytearray()
                async for chunk in request.stream():
                    if len(body) + len(chunk) > 1_048_576:
                        return JSONResponse(
                            status_code=413, content={"code": "REQUEST_TOO_LARGE", "message": "JSON body exceeds 1 MiB"}
                        )
                    body.extend(chunk)
                request._body = bytes(body)  # Starlette caches request.body() here after its stream is consumed.
                return await original(request)
            except RequestValidationError:
                return JSONResponse(
                    status_code=422,
                    content={"code": "VALIDATION_ERROR", "message": "Invalid request JSON or field values"},
                )
            except AppException:
                raise
            except (SQLAlchemyError, ValueError, OSError):
                return JSONResponse(
                    status_code=503,
                    content={
                        "code": "RULE_ENGINE_UNAVAILABLE",
                        "message": "Rule engine data is unavailable or invalid",
                    },
                )

        return bounded_handler


router = APIRouter(
    prefix="/api/v1/rule-engine",
    tags=["rule-engine"],
    route_class=RuleAPIRoute,
    responses={status: {"model": ErrorResponse} for status in (404, 409, 413, 422, 503)},
)
Service = Annotated[RuleAPIService, Depends(get_rule_api_service)]
SessionID = Annotated[str, Path(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")]


@router.post("/validations", response_model=ValidationResponse)
async def validate(payload: ValidationRequest, service: Service) -> ValidationResponse:
    result = await service.validate(payload.session_id, payload.form_data, payload.policy, payload.indicia_issues)
    return ValidationResponse(session_id=payload.session_id, result=result)


@router.get("/validations/{session_id}", response_model=ValidationResponse)
async def result(session_id: SessionID, service: Service) -> ValidationResponse:
    return ValidationResponse(session_id=session_id, result=await service.result(session_id))


@router.post("/validations/{session_id}/replay", response_model=ValidationResponse)
async def replay(session_id: SessionID, service: Service) -> ValidationResponse:
    return ValidationResponse(session_id=session_id, result=await service.replay(session_id))


@router.get("/rules/current", response_model=RuleVersionResponse)
async def current(service: Service) -> RuleVersionResponse:
    return await service.current()


@router.get("/rules/coverage", response_model=CoverageResponse)
async def coverage(service: Service) -> CoverageResponse:
    return await service.coverage()
