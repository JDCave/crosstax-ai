"""Document intake endpoint: official encrypted self-certification PDFs, accepted not rejected.

Route handlers stay free of business logic: all accept/reject decisions live in
backend/services/document_intake.py (AGENTS.md §Backend Conventions).
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from backend.agents.media_preprocessor import MAX_PDF_BYTES, MediaFailureCode, MediaPreprocessError
from backend.api.schemas.audit import DocumentIntakeResponse, ExtractionPayload
from backend.api.schemas.rule_engine import ErrorResponse
from backend.infrastructure.exceptions import AppException
from backend.services.document_intake import intake_document

router = APIRouter(
    prefix="/api/v1/audit/documents",
    tags=["audit"],
    responses={status: {"model": ErrorResponse} for status in (413, 415, 422)},
)


@router.post(
    "",
    response_model=DocumentIntakeResponse,
    summary="Submit one self-certification PDF as application/pdf bytes (AES-128 empty-user-password forms accepted)",
)
async def submit_document(request: Request) -> DocumentIntakeResponse:
    content_type = request.headers.get("content-type", "")
    media_type = content_type.split(";")[0].strip().lower()
    if media_type and media_type not in ("application/pdf", "application/octet-stream"):
        raise AppException(415, "UNSUPPORTED_MEDIA_TYPE", "Expected application/pdf request body")
    body = await request.body()
    if len(body) > MAX_PDF_BYTES:
        raise AppException(413, str(MediaFailureCode.PDF_TOO_LARGE), "Document exceeds the intake size limit")
    try:
        result = intake_document(body)
    except MediaPreprocessError as error:  # transport-level bound only; other codes are business outcomes
        if error.code is MediaFailureCode.PDF_TOO_LARGE:
            raise AppException(413, str(error.code), error.message) from error
        raise
    return DocumentIntakeResponse(
        status=result.status,
        rejection_code=result.rejection_code,
        verdict=result.verdict,
        holders_detected=result.holders_detected,
        fingerprint=result.fingerprint,
        document=result.document,
        extraction=(
            ExtractionPayload(
                fields=result.extraction.fields,
                anomalies=result.extraction.anomalies,
                structure_tree_used=result.extraction.structure_tree_used,
            )
            if result.extraction is not None
            else None
        ),
        note=result.note,
    )
