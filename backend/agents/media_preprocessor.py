"""Shared preprocessing layer for the dual-path extraction (ADR-004 amendment, FR-036).

Scope is strictly limited to document decryption and page enumeration. Field locating and
text attribution MUST NOT live here: ``deterministic_extractor`` and ``vision_parser`` may
both import this module, and nothing else shared between them. Decryption and enumeration
carry no inference, so their correctness is independently verifiable from the document
fingerprint and the page count (Clarification Q2).

Failure attribution (FR-002) is kept distinguishable from "encrypted": an AES-128 document
with an empty user password is accepted (FR-001), while an unlockable-but-password-protected
document and a corrupted document each get their own code. Permission flags such as
no-print / no-copy are not rejection reasons and are never circumvented: only the user
password supplied by the submitting flow (empty for IRD official forms) is used, and the
owner password is not attempted.
"""

from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from pypdf import PdfReader
from pypdf.errors import PdfReadError
from pypdf.generic import DictionaryObject

# Upload bound derived from the transport constraint and recorded explicitly (FR-013
# precedent: bounds come from the interface, never from an implied "unlimited").
MAX_PDF_BYTES = 20 * 1024 * 1024

Template = Literal["INDIVIDUAL", "ENTITY", "CONTROLLING_PERSON", "TERMS"]

# Canonical page counts of the blank IRD templates; a document longer than its template
# baseline carries continuation sheets (FR-004 / R43: extraction MUST NOT truncate).
_TEMPLATE_PAGE_BASELINE: dict[Template, int] = {
    "INDIVIDUAL": 2,
    "ENTITY": 2,
    "CONTROLLING_PERSON": 3,
    "TERMS": 8,
}

# IRD titles use an EN DASH or HYPHEN-MINUS depending on the export; accept both explicitly.
_DASH = "\u2013-"
_TITLE_PATTERNS: tuple[tuple[re.Pattern[str], Template], ...] = (
    (re.compile(rf"self-?certification form\s*[{_DASH}]\s*controlling person", re.I), "CONTROLLING_PERSON"),
    (re.compile(rf"self-?certification form\s*[{_DASH}]\s*individual", re.I), "INDIVIDUAL"),
    (re.compile(rf"self-?certification form\s*[{_DASH}]\s*entity", re.I), "ENTITY"),
    (re.compile(r"meaning of the terms", re.I), "TERMS"),
)


class MediaFailureCode(StrEnum):
    """FR-047: three mutually exclusive intake attributions; "encrypted" is not one of them."""

    PDF_CORRUPTED = "PDF_CORRUPTED"
    PDF_USER_PASSWORD_REQUIRED = "PDF_USER_PASSWORD_REQUIRED"
    PDF_TOO_LARGE = "PDF_TOO_LARGE"


class MediaPreprocessError(Exception):
    def __init__(self, code: MediaFailureCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class PreprocessedPdf:
    """Decrypted document plus the shared-layer facts the contract needs (#/$defs/Document)."""

    fingerprint: str
    is_encrypted: bool
    page_count: int
    structure_tree_available: bool
    has_continuation_sheets: bool
    template: Template | None
    reader: PdfReader

    def to_contract_document(self, holders_declared: int) -> dict[str, object]:
        return {
            "is_encrypted": self.is_encrypted,
            "structure_tree_available": self.structure_tree_available,
            "holders_declared": holders_declared,
            "has_continuation_sheets": self.has_continuation_sheets,
            "fingerprint": self.fingerprint,
        }


def _detect_template(reader: PdfReader) -> Template | None:
    try:
        title = (reader.metadata.title or "") if reader.metadata else ""
    except Exception:  # metadata is advisory; a hostile trailer must not sink intake
        return None
    for pattern, template in _TITLE_PATTERNS:
        if pattern.search(title):
            return template
    return None


def _structure_tree_available(reader: PdfReader) -> bool:
    try:
        root = reader.trailer["/Root"].get_object()
    except Exception:
        return False
    if not isinstance(root, DictionaryObject) or "/StructTreeRoot" not in root:
        return False
    try:
        return root["/StructTreeRoot"].get_object() is not None
    except Exception:
        return False


def preprocess(content: bytes) -> PreprocessedPdf:
    """Decrypt with the empty user password, enumerate pages, fingerprint, and classify flags.

    Raises MediaPreprocessError with an attribution that is distinguishable from
    "encrypted" (FR-002); encryption alone is never a failure (FR-001).
    """
    if len(content) > MAX_PDF_BYTES:
        raise MediaPreprocessError(MediaFailureCode.PDF_TOO_LARGE, "Document exceeds the intake size limit")
    fingerprint = hashlib.sha256(content).hexdigest()
    try:
        reader = PdfReader(io.BytesIO(content))
    except PdfReadError as error:
        raise MediaPreprocessError(MediaFailureCode.PDF_CORRUPTED, f"Document could not be parsed: {error}") from error
    except Exception as error:  # malformed trailers surface as assorted exceptions
        raise MediaPreprocessError(MediaFailureCode.PDF_CORRUPTED, f"Document could not be parsed: {error}") from error

    is_encrypted = reader.is_encrypted
    if is_encrypted:
        try:
            decrypted = reader.decrypt("")
        except Exception as error:  # FileNotDecryptedError / unsupported AES-256 revision
            raise MediaPreprocessError(
                MediaFailureCode.PDF_USER_PASSWORD_REQUIRED,
                "Document requires a non-empty user password",
            ) from error
        if not decrypted:
            raise MediaPreprocessError(
                MediaFailureCode.PDF_USER_PASSWORD_REQUIRED,
                "Document requires a non-empty user password",
            )

    try:
        page_count = len(reader.pages)
        for page in reader.pages:  # force lazy parse so corrupted pages surface here
            _ = page.indirect_reference
    except Exception as error:
        raise MediaPreprocessError(MediaFailureCode.PDF_CORRUPTED, f"Page enumeration failed: {error}") from error

    template = _detect_template(reader)
    baseline = _TEMPLATE_PAGE_BASELINE.get(template) if template is not None else None
    return PreprocessedPdf(
        fingerprint=fingerprint,
        is_encrypted=is_encrypted,
        page_count=page_count,
        structure_tree_available=_structure_tree_available(reader),
        has_continuation_sheets=(baseline is not None and page_count > baseline),
        template=template,
        reader=reader,
    )
