"""Document intake (FR-005 / FR-047): one document = one holder, enforced before extraction.

The detection criterion is the holder identity block (Part 1 name + address + date of birth
heading) appearing twice — never a repeat-group count. ``tax_residencies[]`` (R28), the eight
controlling-person slots (R23), and the 11x3 type matrix (R26) are all legitimate repeats and
MUST NOT trigger rejection (SC-012 reverse gate).

Rejected documents never proceed to extraction: taking the first holder or system-splitting
the document are both prohibited (FR-005); a multi-holder submission is a fixable declaration
error, so the verdict is NEED_USER_FIX with the dedicated code MULTI_HOLDER_DOCUMENT (FR-047),
distinct from "encrypted" and from corrupted/undecryptable attributions (FR-001 / FR-002).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from backend.agents.deterministic_extractor import ExtractionResult, extract
from backend.agents.media_preprocessor import MediaFailureCode, MediaPreprocessError, preprocess

# "Part 1 Identification of {Individual|Entity} Account Holder" / "... of Controlling Person".
# Declaration text ("...in Part 1 of this form...") never matches: the heading is required.
_IDENTITY_BLOCK = re.compile(
    r"Identification of (?:Individual |Entity )?Account Holder\b|Identification of Controlling Person\b"
)

Verdict = Literal["AUTO_PASS", "NEED_USER_FIX", "MANUAL_TRIAGE"]


@dataclass(frozen=True)
class IntakeResult:
    status: Literal["ACCEPTED", "REJECTED"]
    rejection_code: str | None
    verdict: Verdict | None
    holders_detected: int
    fingerprint: str | None
    document: dict[str, Any] | None
    extraction: ExtractionResult | None
    note: str | None = None


def count_holder_identity_blocks(reader: Any) -> int:
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    return len(_IDENTITY_BLOCK.findall(text))


def intake_document(content: bytes) -> IntakeResult:
    """Accept official encrypted forms; attribute every failure distinctly (FR-001/002/005/047)."""
    try:
        pre = preprocess(content)
    except MediaPreprocessError as error:
        if error.code is MediaFailureCode.PDF_TOO_LARGE:
            raise
        return IntakeResult(
            status="REJECTED",
            rejection_code=str(error.code),
            verdict="MANUAL_TRIAGE",  # FR-002: undecryptable/damaged goes to a human, never silent
            holders_detected=0,
            fingerprint=None,
            document=None,
            extraction=None,
            note=error.message,
        )

    text_blocks = count_holder_identity_blocks(pre.reader)
    if pre.template == "TERMS" or (pre.template is None and text_blocks == 0):
        return IntakeResult(
            status="ACCEPTED",
            rejection_code=None,
            verdict="MANUAL_TRIAGE",  # not a self-certification form: human triage, not a rejection
            holders_detected=0,
            fingerprint=pre.fingerprint,
            document=pre.to_contract_document(holders_declared=1),
            extraction=None,
            note="NOT_SELF_CERTIFICATION_FORM",
        )

    holders = max(text_blocks, 1)
    if holders > 1:
        return IntakeResult(
            status="REJECTED",
            rejection_code="MULTI_HOLDER_DOCUMENT",
            verdict="NEED_USER_FIX",
            holders_detected=holders,
            fingerprint=pre.fingerprint,
            document=pre.to_contract_document(holders_declared=holders),
            extraction=None,  # never "take the first holder" (FR-005)
            note="Each holder of a joint or multiple account must submit a separate form",
        )

    extraction = extract(pre)
    return IntakeResult(
        status="ACCEPTED",
        rejection_code=None,
        verdict=None,
        holders_detected=holders,
        fingerprint=pre.fingerprint,
        document=pre.to_contract_document(holders_declared=holders),
        extraction=extraction,
    )
