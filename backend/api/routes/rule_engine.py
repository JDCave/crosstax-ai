"""Isolated versioned endpoints for teammate-to-engine JSON calls."""

from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from cryptography.fernet import InvalidToken
from fastapi import APIRouter, Depends, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy.exc import SQLAlchemyError

from backend.api.schemas.rule_engine import ErrorResponse, ValidationRequest, ValidationResponse
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
            except RequestValidationError as exc:
                from backend.api.schemas.rule_engine import field_errors

                return JSONResponse(
                    status_code=422,
                    content={
                        "code": "VALIDATION_ERROR",
                        "message": "Invalid request JSON or field values",
                        "details": field_errors(exc.errors()),
                    },
                )
            except AppException as exc:
                if request.url.path.startswith("/api/v1/rule-engine/tasks"):
                    return JSONResponse(
                        status_code=exc.status_code,
                        content={"code": exc.code, "message": exc.message},
                        headers={
                            "Cache-Control": "no-store",
                            **({"Retry-After": "1"} if exc.status_code == 503 else {}),
                        },
                    )
                raise
            except (SQLAlchemyError, ValueError, OSError, InvalidToken):
                return JSONResponse(
                    status_code=503,
                    headers={"Retry-After": "1", "Cache-Control": "no-store"},
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
    responses={status: {"model": ErrorResponse} for status in (413, 422, 500, 503)},
)
Service = Annotated[RuleAPIService, Depends(get_rule_api_service)]


@router.post(
    "/validate",
    response_model=ValidationResponse,
    include_in_schema=False,
    summary="Validate structured CRS data and return results synchronously",
)
async def validate(payload: ValidationRequest, service: Service) -> ValidationResponse:
    return await service.validate(payload.form_data, payload.policy, payload.indicia_issues, payload.include_guidance)
