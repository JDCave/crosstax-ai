"""Intake-layer tests: multi-holder rejection, SC-012 reverse gate, endpoint smoke (T015/T016)."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter

from backend.services.document_intake import count_holder_identity_blocks, intake_document

ASSETS = Path(__file__).resolve().parents[2] / "assets" / "crs-templates"


def pdf_bytes(name: str) -> bytes:
    return (ASSETS / name).read_bytes()


def concatenated_copies(name: str, copies: int) -> bytes:
    source = PdfReader(io.BytesIO(pdf_bytes(name)))
    source.decrypt("")
    writer = PdfWriter()
    for _ in range(copies):
        for page in source.pages:
            writer.add_page(page)
    writer.add_metadata({"/Title": "Self-Certification Form - Individual"})
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


# --- FR-005 / FR-047: rejection branch --------------------------------------------------


def test_two_holder_blocks_reject_whole_document_with_dedicated_code() -> None:
    """SC-012 front gate: MULTI_HOLDER_DOCUMENT + NEED_USER_FIX, never reused attributions."""
    result = intake_document(concatenated_copies("crs-individual-ird.pdf", 2))
    assert result.status == "REJECTED"
    assert result.rejection_code == "MULTI_HOLDER_DOCUMENT"
    assert result.verdict == "NEED_USER_FIX"
    assert result.holders_detected == 2
    assert result.extraction is None  # never "take the first holder"


def test_identity_blocks_counted_per_block_not_per_repeat_group() -> None:
    source = PdfReader(io.BytesIO(pdf_bytes("crs-individual-ird.pdf")))
    source.decrypt("")
    assert count_holder_identity_blocks(source) == 1


# --- SC-012 reverse gate: legal repeats MUST NOT reject ---------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "crs-individual-ird.pdf",  # tax_residencies[] slots (D3 core)
        "crs-entity-ird.pdf",  # 8 controlling-person name slots (1)-(8)
        "crs-controlling-person-ird.pdf",  # 11x3 type matrix + (1)-(3) entity slots
    ],
)
def test_single_holder_with_legal_repeat_groups_is_accepted(name: str) -> None:
    result = intake_document(pdf_bytes(name))
    assert result.status == "ACCEPTED"
    assert result.rejection_code is None
    assert result.holders_detected == 1
    assert result.extraction is not None
    assert result.extraction.fields["holder_type"] == (
        "INDIVIDUAL" if "individual" in name else "ENTITY" if "entity" in name else "CONTROLLING_PERSON"
    )


def test_three_tax_residencies_document_is_not_rejected() -> None:
    """The D3 scenario itself: a holder with 3 residencies must sail through intake."""
    result = intake_document(pdf_bytes("crs-individual-ird.pdf"))
    extracted = result.extraction.fields if result.extraction else {}
    residencies = [k for k in extracted if k.startswith("tax_residencies[")]
    assert result.status == "ACCEPTED"
    assert len(residencies) >= 5 * 4  # 5 printed rows x 5 keys each, all preserved


# --- other attributions reach humans without pretending to be "encrypted" ---------------


def test_undecryptable_and_corrupted_are_triage_not_encrypted_rejection() -> None:
    corrupted = intake_document(b"not a pdf at all")
    assert corrupted.status == "REJECTED"
    assert corrupted.rejection_code == "PDF_CORRUPTED"
    assert corrupted.verdict == "MANUAL_TRIAGE"


def test_terms_reference_sheet_goes_to_triage_without_rejection() -> None:
    """SC-001: the fourth official PDF is still intake-accepted, not rejected as unsupported."""
    result = intake_document(pdf_bytes("crs-terms-ird.pdf"))
    assert result.status == "ACCEPTED"
    assert result.verdict == "MANUAL_TRIAGE"
    assert result.note == "NOT_SELF_CERTIFICATION_FORM"


# --- endpoint smoke (T016) ----------------------------------------------------------------


@pytest.mark.anyio
async def test_documents_endpoint_accepts_encrypted_official_pdf(client) -> None:  # type: ignore[no-untyped-def]
    response = await client.post(
        "/api/v1/audit/documents",
        content=pdf_bytes("crs-individual-ird.pdf"),
        headers={"content-type": "application/pdf"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ACCEPTED"
    assert body["document"]["is_encrypted"] is True
    assert body["extraction"]["fields"]["holder_type"] == "INDIVIDUAL"


@pytest.mark.anyio
async def test_documents_endpoint_reports_multi_holder_with_code_and_verdict(client) -> None:  # type: ignore[no-untyped-def]
    response = await client.post(
        "/api/v1/audit/documents",
        content=concatenated_copies("crs-individual-ird.pdf", 2),
        headers={"content-type": "application/pdf"},
    )
    assert response.status_code == 200  # business outcome, not an HTTP error
    body = response.json()
    assert body["status"] == "REJECTED"
    assert body["rejection_code"] == "MULTI_HOLDER_DOCUMENT"
    assert body["verdict"] == "NEED_USER_FIX"
    assert body["extraction"] is None


@pytest.mark.anyio
async def test_documents_endpoint_rejects_non_pdf_media_type(client) -> None:  # type: ignore[no-untyped-def]
    response = await client.post(
        "/api/v1/audit/documents",
        content=b"hello",
        headers={"content-type": "text/plain"},
    )
    assert response.status_code == 415
