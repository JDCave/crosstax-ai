"""Shared-layer acceptance tests: four official IRD PDFs, permission flags, failure attribution.

Covers FR-001/FR-002/FR-003/FR-004, US1-AS1-AS4, SC-001 (4/4 accepted), and the
fingerprint/page-count independent verification stated in Clarification Q2.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter

from backend.agents.media_preprocessor import MediaFailureCode, MediaPreprocessError, preprocess

ASSETS = Path(__file__).resolve().parents[2] / "assets" / "crs-templates"

# Registered in assets/crs-templates/README.md (byte-identical re-download from ird.gov.hk, 2026-11-05).
OFFICIAL = {
    "crs-individual-ird.pdf": ("2a1294d624f9fdcfdfb75c57e3cbc37898587abe9449973ba084b1f06a6d444c", 2, "INDIVIDUAL"),
    "crs-entity-ird.pdf": ("4e4fcd4679bf0c10e35b143ad9447639be44d3f76ce8e970e48c415fb5966263", 2, "ENTITY"),
    "crs-controlling-person-ird.pdf": (
        "be5bd468cf2afd89fa821bbfe00093066c7b85ef8374e0c76907bb6f278c53c5",
        3,
        "CONTROLLING_PERSON",
    ),
    "crs-terms-ird.pdf": ("d535aa4c144fc515dd04ff151e6753e0c357132ec671429447a55cfdc6c168ea", 8, "TERMS"),
}


def _pdf_bytes(build) -> bytes:
    writer = PdfWriter()
    build(writer)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


@pytest.mark.parametrize("filename", sorted(OFFICIAL))
def test_official_encrypted_forms_are_accepted(filename: str) -> None:
    """SC-001: zero intake rejections; FR-001: encryption is not a rejection reason."""
    doc = preprocess((ASSETS / filename).read_bytes())
    expected_sha, expected_pages, expected_template = OFFICIAL[filename]
    assert doc.fingerprint == expected_sha  # free pages enumerate identically to the registered baseline
    assert doc.is_encrypted is True
    assert doc.page_count == expected_pages
    assert doc.template == expected_template
    assert doc.structure_tree_available is True  # R48: Tagged PDF with /StructTreeRoot
    assert doc.has_continuation_sheets is False


def test_first_page_text_is_readable_after_decryption() -> None:
    doc = preprocess((ASSETS / "crs-individual-ird.pdf").read_bytes())
    text = doc.reader.pages[0].extract_text() or ""
    assert "Self-Certification Form" in text
    assert "Ref. No." in text


def test_permission_restricted_but_readable_document_is_accepted() -> None:
    """US1-AS3: no-print/no-copy flags are not rejection reasons and are not circumvented."""

    def build(writer: PdfWriter) -> None:
        source = PdfReader(io.BytesIO((ASSETS / "crs-individual-ird.pdf").read_bytes()))
        source.decrypt("")
        for page in source.pages:
            writer.add_page(page)
        writer.encrypt(
            user_password="",
            owner_password="owner-secret",
            algorithm="AES-128",
            permissions_flag=0b0000_0000_0000,
        )

    doc = preprocess(_pdf_bytes(build))
    assert doc.is_encrypted is True
    assert doc.page_count == 2


def test_non_empty_user_password_gets_distinguishable_attribution() -> None:
    """US1-AS4 / FR-002: failure attribution MUST be distinguishable from "encrypted"."""

    def build(writer: PdfWriter) -> None:
        source = PdfReader(io.BytesIO((ASSETS / "crs-individual-ird.pdf").read_bytes()))
        source.decrypt("")
        for page in source.pages:
            writer.add_page(page)
        writer.encrypt(user_password="customer-password", algorithm="AES-128")

    with pytest.raises(MediaPreprocessError) as excinfo:
        preprocess(_pdf_bytes(build))
    assert excinfo.value.code is MediaFailureCode.PDF_USER_PASSWORD_REQUIRED


def test_corrupted_document_gets_distinguishable_attribution() -> None:
    """US1-AS4 / FR-002: corruption attribution is neither "encrypted" nor password-required."""
    with pytest.raises(MediaPreprocessError) as excinfo:
        preprocess(b"%PDF-1.7\nthis trailer never existed\n")
    assert excinfo.value.code is MediaFailureCode.PDF_CORRUPTED

    with pytest.raises(MediaPreprocessError) as excinfo:
        preprocess(b"")
    assert excinfo.value.code is MediaFailureCode.PDF_CORRUPTED


def test_continuation_sheet_over_baseline_is_flagged_not_truncated() -> None:
    """FR-004 / R43: extra pages are recorded; enumeration does not cap at the template baseline."""

    def build(writer: PdfWriter) -> None:
        source = PdfReader(io.BytesIO((ASSETS / "crs-entity-ird.pdf").read_bytes()))
        source.decrypt("")
        for page in source.pages:
            writer.add_page(page)
        writer.add_page(source.pages[0])  # an appended continuation sheet
        writer.add_metadata({"/Title": "Self-Certification Form - Entity"})

    doc = preprocess(_pdf_bytes(build))
    assert doc.page_count == 3
    assert doc.has_continuation_sheets is True


def test_document_flags_map_onto_contract_document_definition() -> None:
    doc = preprocess((ASSETS / "crs-individual-ird.pdf").read_bytes())
    assert doc.to_contract_document(holders_declared=1) == {
        "is_encrypted": True,
        "structure_tree_available": True,
        "holders_declared": 1,
        "has_continuation_sheets": False,
        "fingerprint": doc.fingerprint,
    }
