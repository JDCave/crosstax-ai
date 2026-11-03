"""Provider-independent AI failure categories and safe public metadata."""

from enum import StrEnum

from pydantic import BaseModel


class AIErrorCategory(StrEnum):
    CONFIGURATION = "configuration"
    AUTHENTICATION = "authentication"
    PERMISSION = "permission"
    RATE_LIMIT = "rate_limit"
    QUOTA = "quota"
    TIMEOUT = "timeout"
    CONNECTION = "connection"
    INVALID_REQUEST = "invalid_request"
    INVALID_RESPONSE = "invalid_response"
    SERVICE_UNAVAILABLE = "service_unavailable"
    INTERNAL = "internal"


REASON_CODES = {
    AIErrorCategory.CONFIGURATION: "AI_NOT_CONFIGURED",
    AIErrorCategory.AUTHENTICATION: "AI_AUTHENTICATION_FAILED",
    AIErrorCategory.PERMISSION: "AI_PERMISSION_DENIED",
    AIErrorCategory.RATE_LIMIT: "AI_RATE_LIMITED",
    AIErrorCategory.QUOTA: "AI_QUOTA_EXCEEDED",
    AIErrorCategory.TIMEOUT: "AI_TIMEOUT",
    AIErrorCategory.CONNECTION: "AI_CONNECTION_ERROR",
    AIErrorCategory.INVALID_REQUEST: "AI_REQUEST_REJECTED",
    AIErrorCategory.INVALID_RESPONSE: "AI_INVALID_RESPONSE",
    AIErrorCategory.SERVICE_UNAVAILABLE: "AI_PROVIDER_UNAVAILABLE",
    AIErrorCategory.INTERNAL: "AI_INTERNAL_ERROR",
}
RETRYABLE = {
    AIErrorCategory.RATE_LIMIT,
    AIErrorCategory.TIMEOUT,
    AIErrorCategory.CONNECTION,
    AIErrorCategory.SERVICE_UNAVAILABLE,
}


class AIErrorInfo(BaseModel):
    category: AIErrorCategory
    retryable: bool

    @classmethod
    def for_category(cls, category: AIErrorCategory) -> "AIErrorInfo":
        return cls(category=category, retryable=category in RETRYABLE)
