"""Extraction aggregator: per-field-position three-way comparison (FR-048) and recomputable rate (SC-004).

Import graph (FR-036): this module imports BOTH extraction paths; the paths never import each
other and share only ``media_preprocessor``. Enforced statically by
tests/backend/test_agent_import_graph.py.

Rules implemented here (Clarification session 2026-11-05, CHK024 ruling):
- capability comes ONLY from the static ``path_capability`` column of mapping-matrix.csv;
  runtime results never reclassify a field (FR-048 anti-fraud clause);
- declared BOTH, values differ (including one empty / one filled) -> DISAGREED, retain both
  originals, adopt neither (FR-038);
- declared BOTH, both empty -> AGREED_EMPTY, counted as agreement (FR-040);
- declared VISION_ONLY / TEXT_ONLY -> never in the denominator, counted separately (SC-011);
- one path failed at runtime -> its BOTH-declared fields leave the denominator, counted as
  path failure, never as disagreement (FR-039);
- shared-layer (decrypt/enum) failures leave the denominator and feed their own counter,
  never absorbed by the single-path counter (SC-009).
"""

from __future__ import annotations

import csv
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from backend.agents.deterministic_extractor import ExtractionResult
from backend.agents.vision_parser import VisionExtraction

Capability = Literal["BOTH", "VISION_ONLY", "TEXT_ONLY"]
Status = Literal["AGREED", "AGREED_EMPTY", "DISAGREED", "SINGLE_PATH", "PATH_FAILED", "SHARED_LAYER_FAILED"]

_MATRIX = (
    Path(__file__).resolve().parents[2] / ".specify" / "features" / "001-crs-contract" / "mapping-matrix.csv"
)

# Contract path -> mapping-matrix row_id. The row is the capability carrier (FR-048); this map is
# the single place that translates flattened extraction paths back to matrix rows.
_PATH_TO_ROW: tuple[tuple[str, str], ...] = (
    ("x-header.fi_name", "R01"),
    ("x-header.fi_address", "R02"),
    ("x-header.ref_no", "R03"),
    ("name.title", "R05"),
    ("name.last_name", "R06"),
    ("name.first_name", "R07"),
    ("name.middle_names", "R08"),
    ("name.entity_legal_name", "R09"),
    ("name.is_branch", "R09"),
    ("hk_identity.hkid_or_passport", "R10"),
    ("hk_identity.business_registration_number", "R12"),
    ("birth_date", "R19"),
    ("birth_place", "R20"),
    ("entity.entity_type", "R21"),
    ("entity.entity_type_subitem", "R22"),
    ("entity.controlling_person_names", "R23"),
    ("entity.no_natural_person_control", "R24"),
    ("entity.poe_jurisdiction", "R33"),
    ("entity.incorporation_jurisdiction", "R11"),
    ("controlling_person.controlled_entities", "R25"),
    ("declaration.holder_or_authorized_resolved", "R35"),
    ("declaration.signatory_name", "R38"),
    ("declaration.capacity", "R39"),
    ("declaration.has_signature", "R37"),
    ("declaration.signing_date", "R40"),
    ("declaration.power_of_attorney_attached", "R36"),
)
_ADDRESS_ROW = {
    "line1": "R13",
    "city": "R14",
    "subentity": "R15",
    "country": "R16",
    "post_code": "R17",
    "source_layout_anomaly": "R18",
}
_TIN_ROW = {
    "jurisdiction": "R28",
    "tin": "R29",
    "no_tin_reason": "R30",
    "reason_b_explanation": "R31",
    "basis": "R33",
    "reason_c_applicability_unverified": "R34",
}
_CP_ROW = {"entity_name": "R25", "cp_types": "R26", "linked_document_ref": "R03", "link_confidence": "R03"}


def load_capabilities(matrix_path: Path = _MATRIX) -> dict[str, Capability]:
    """Static capability declarations, validated at load: unknown values fail fast (FR-048)."""
    caps: dict[str, Capability] = {}
    with matrix_path.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            raw = str(row["path_capability"]).strip().upper()
            if raw not in ("BOTH", "VISION_ONLY", "TEXT_ONLY"):
                raise ValueError(f"Invalid path_capability {raw!r} for {row['row_id']}")
            caps[row["row_id"]] = raw  # type: ignore[assignment]
    return caps


def row_for_path(path: str) -> str | None:
    """Map a flattened contract path back to its matrix row_id.

    Accepts both flattening conventions: bracketed ("tax_residencies[0].tin", the extractor's)
    and dotted ("tax_residencies.0.tin", the validation engine's).
    """
    normalized = re.sub(r"\[(\d+)\]", r".\1", path)
    if normalized.startswith("addresses."):
        parts = normalized.split(".")
        sub = parts[2] if len(parts) > 2 else ""
        return _ADDRESS_ROW.get(sub)
    if normalized.startswith("tax_residencies."):
        return _TIN_ROW.get(normalized.rsplit(".", 1)[1])
    if normalized.startswith("controlling_person.controlled_entities."):
        return _CP_ROW.get(normalized.rsplit(".", 1)[1])
    for prefix, row_id in _PATH_TO_ROW:
        if normalized == prefix or normalized.startswith(prefix + "."):
            return row_id
    return None


@dataclass
class FieldComparison:
    path: str
    row_id: str | None
    capability: Capability | str
    status: Status
    deterministic_value: Any = None
    vision_value: Any = None
    retained_value: Any = None  # None unless retained (FR-038 retention narrowing)


@dataclass
class AgreementReport:
    comparisons: list[FieldComparison]
    numerator: int
    denominator: int
    rate: float | None
    shared_layer_failures: int
    single_path_fields: int
    path_failures: int
    disagreement_paths: list[str] = field(default_factory=list)
    definition: str = (
        "SC-004: denominator = fields declared path_capability=BOTH whose both paths ran, minus shared-layer "
        "failures; numerator = among those, equal values including both-empty (FR-040). Independent counters: "
        "shared_layer_failures (SC-009), single_path_fields (SC-011), path_failures (FR-039)."
    )

    def recompute(self) -> tuple[int, int, float | None]:
        numerator = sum(1 for c in self.comparisons if c.status in ("AGREED", "AGREED_EMPTY"))
        denominator = sum(1 for c in self.comparisons if c.status in ("AGREED", "AGREED_EMPTY", "DISAGREED"))
        rate = (numerator / denominator) if denominator else None
        return numerator, denominator, rate


def _fields_of(source: ExtractionResult | VisionExtraction | dict[str, Any]) -> dict[str, Any]:
    """Accept either path's result object or a raw field dict (both are valid aggregator inputs)."""
    fields = getattr(source, "fields", None)
    if isinstance(fields, dict):
        return fields
    if isinstance(source, dict):
        return source
    raise TypeError("aggregator input must expose .fields or be a dict")


def aggregate(
    deterministic: ExtractionResult | VisionExtraction | dict[str, Any],
    vision: ExtractionResult | VisionExtraction | dict[str, Any],
    *,
    capabilities: dict[str, Capability] | None = None,
    shared_layer_failed_paths: frozenset[str] = frozenset(),
    deterministic_failed_paths: frozenset[str] = frozenset(),
    vision_failed_paths: frozenset[str] = frozenset(),
) -> AgreementReport:
    deterministic = _fields_of(deterministic)
    vision = _fields_of(vision)
    caps = capabilities if capabilities is not None else load_capabilities()
    paths = sorted(set(deterministic) | set(vision))
    comparisons: list[FieldComparison] = []
    for path in paths:
        row_id = row_for_path(path)
        capability = caps.get(row_id, "BOTH") if row_id else "BOTH"
        det_value = deterministic.get(path)
        vis_value = vision.get(path)
        if capability in ("VISION_ONLY", "TEXT_ONLY"):
            status: Status = "SINGLE_PATH"
        elif path in shared_layer_failed_paths:
            status = "SHARED_LAYER_FAILED"
        elif path in deterministic_failed_paths or path in vision_failed_paths:
            status = "PATH_FAILED"
        elif det_value == vis_value:
            status = "AGREED_EMPTY" if det_value in (None, "", []) else "AGREED"
        else:
            status = "DISAGREED"
        comparison = FieldComparison(
            path=path,
            row_id=row_id,
            capability=capability,
            status=status,
            deterministic_value=det_value,
            vision_value=vis_value,
        )
        # FR-038 retention narrowing: disagreements keep both originals; agreed positions keep one.
        if status == "DISAGREED":
            comparison.retained_value = None  # both originals live in *_value; neither is adopted
        elif status in ("AGREED", "AGREED_EMPTY"):
            comparison.retained_value = det_value
        comparisons.append(comparison)

    counts = Counter(c.status for c in comparisons)
    numerator = counts["AGREED"] + counts["AGREED_EMPTY"]
    denominator = numerator + counts["DISAGREED"]
    return AgreementReport(
        comparisons=comparisons,
        numerator=numerator,
        denominator=denominator,
        rate=(numerator / denominator) if denominator else None,
        shared_layer_failures=counts["SHARED_LAYER_FAILED"],
        single_path_fields=counts["SINGLE_PATH"],
        path_failures=counts["PATH_FAILED"],
        disagreement_paths=[c.path for c in comparisons if c.status == "DISAGREED"],
    )
