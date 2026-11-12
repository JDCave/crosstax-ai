"""Request/response models for the document intake endpoint."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ExtractionPayload(BaseModel):
    fields: dict[str, Any]
    anomalies: list[str] = Field(default_factory=list)
    structure_tree_used: bool


class DocumentIntakeResponse(BaseModel):
    status: str = Field(description="ACCEPTED | REJECTED")
    rejection_code: str | None = Field(
        default=None,
        description="MULTI_HOLDER_DOCUMENT | PDF_CORRUPTED | PDF_USER_PASSWORD_REQUIRED; never 'encrypted'",
    )
    verdict: str | None = Field(default=None, description="Existing three-state vocabulary (specs/data-spec.md §1.3)")
    holders_detected: int
    fingerprint: str | None
    document: dict[str, Any] | None = Field(description="contracts/crs-form-data.schema.json#/$defs/Document")
    extraction: ExtractionPayload | None
    note: str | None
