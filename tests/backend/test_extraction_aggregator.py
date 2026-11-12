"""T024 — aggregator tests: three-way comparison, independent counters, third-party recomputation.

Uses the real deterministic extractor on the official individual form for the BOTH-declared
paths, plus a synthetic vision path, so every branch of FR-048 / FR-038 / FR-039 / FR-040 /
SC-004 / SC-009 / SC-011 is exercised against production code (not stubs).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.agents.deterministic_extractor import extract
from backend.agents.extraction_aggregator import aggregate, load_capabilities, row_for_path
from backend.agents.media_preprocessor import preprocess

ASSETS = Path(__file__).resolve().parents[2] / "assets" / "crs-templates"


def deterministic_fields() -> dict[str, object]:
    return extract(preprocess((ASSETS / "crs-individual-ird.pdf").read_bytes())).fields


def test_us4_as1_per_field_marks_and_recomputable_rate() -> None:
    det = deterministic_fields()
    report = aggregate(det, dict(det))  # vision agrees everywhere
    assert report.denominator > 0
    assert report.rate == pytest.approx(1.0)
    # third party can recompute from the comparison list alone (CHK016)
    numerator, denominator, rate = report.recompute()
    assert (numerator, denominator) == (report.numerator, report.denominator)
    assert rate == pytest.approx(report.rate)
    # every BOTH field agrees; VISION_ONLY/TEXT_ONLY legitimately leave as SINGLE_PATH
    for c in report.comparisons:
        assert c.status in ("AGREED", "AGREED_EMPTY", "SINGLE_PATH"), c.status
        if c.capability == "BOTH":
            assert c.status in ("AGREED", "AGREED_EMPTY")


def test_us4_as2_disagreement_retains_both_and_is_not_silently_adopted() -> None:
    det = deterministic_fields()
    vision = dict(det)
    vision["name.last_name"] = "CHAN"
    det["name.last_name"] = "LEE"  # one empty-ish, one filled -> DISAGREED (CHK024/FR-048)
    report = aggregate(det, vision)
    row = next(c for c in report.comparisons if c.path == "name.last_name")
    assert row.status == "DISAGREED"
    assert row.row_id == "R06"
    assert row.capability == "BOTH"
    assert {row.deterministic_value, row.vision_value} == {"LEE", "CHAN"}  # both retained
    assert row.retained_value is None  # neither adopted (FR-038)
    assert "name.last_name" in report.disagreement_paths


def test_empty_vs_filled_is_a_disagreement_not_a_missing_side() -> None:
    """CHK024 ruling: a BOTH field with one empty and one value is DISAGREED, never 'one side missing'."""
    det = deterministic_fields()
    vision = dict(det)
    det["name.first_name"] = None
    vision["name.first_name"] = "DEMO"
    report = aggregate(det, vision)
    row = next(c for c in report.comparisons if c.path == "name.first_name")
    assert row.status == "DISAGREED"


def test_us4_as3_one_path_failure_shrinks_denominator_without_counting_as_disagreement() -> None:
    det = deterministic_fields()
    report = aggregate(det, dict(det), vision_failed_paths=frozenset({"name.last_name"}))
    row = next(c for c in report.comparisons if c.path == "name.last_name")
    assert row.status == "PATH_FAILED"
    assert row.path not in report.disagreement_paths
    counts = {c.status for c in report.comparisons}
    assert "DISAGREED" not in counts
    # failed field is out of the denominator
    _, denominator, _ = report.recompute()
    assert denominator == report.denominator


def test_us4_as4_both_empty_agrees_for_not_compulsory_field() -> None:
    """FR-040: both-empty on a Not-compulsory position is AGREED, not a disagreement."""
    det = {"birth_place": None}
    report = aggregate(det, {"birth_place": None})
    row = next(c for c in report.comparisons if c.path == "birth_place")
    assert row.status == "AGREED_EMPTY"
    assert row.row_id == "R20"
    assert report.numerator == 1 and report.denominator == 1


def test_vision_only_fields_are_never_in_the_denominator_and_counted_separately() -> None:
    """SC-011 + FR-048: declared single-path fields leave the denominator and feed their own counter."""
    det = {"entity.entity_type": None, "name.last_name": "LEE"}
    vision = {"entity.entity_type": "PASSIVE_NFE", "name.last_name": "LEE"}
    report = aggregate(det, vision)
    type_row = next(c for c in report.comparisons if c.path == "entity.entity_type")
    assert type_row.status == "SINGLE_PATH"  # R21 is declared VISION_ONLY
    assert type_row not in [c for c in report.comparisons if c.status in ("AGREED", "AGREED_EMPTY", "DISAGREED")]
    assert report.single_path_fields == 1
    assert report.denominator == 1  # only name.last_name (BOTH) counts


def test_shared_layer_failure_and_single_path_counters_are_independent() -> None:
    """SC-009/SC-011: the two counters never absorb each other."""
    det = {"entity.entity_type": None, "name.last_name": None}
    vision = {"entity.entity_type": None, "name.last_name": None}
    report = aggregate(det, vision, shared_layer_failed_paths=frozenset({"name.last_name"}))
    statuses = {c.path: c.status for c in report.comparisons}
    assert statuses["name.last_name"] == "SHARED_LAYER_FAILED"  # BOTH field, shared-layer failure (SC-009)
    assert statuses["entity.entity_type"] == "SINGLE_PATH"  # R21 static VISION_ONLY, its own counter (SC-011)
    assert report.shared_layer_failures == 1
    assert report.single_path_fields == 1
    assert report.denominator == 0  # neither contributes to the agreement rate


def test_capabilities_loaded_from_mapping_matrix() -> None:
    caps = load_capabilities()
    assert caps["R21"] == "VISION_ONLY"
    assert caps["R28"] == "BOTH"
    assert row_for_path("tax_residencies[0].tin") == "R29"
    assert row_for_path("addresses.1.city") == "R14"


def test_t023_disagreement_degrades_to_blocker_and_agreed_stays_clear() -> None:
    """FR-038 + PRD §8.2 R1 split: two-path disagreement = BLOCKER/NEED_USER_FIX via resolve_verdict."""
    from backend.engine.contracts import AuditIssue
    from backend.engine.verdict import resolve_verdict

    det = {"name.last_name": "LEE", "birth_date": "1990-05-20"}
    vision = {"name.last_name": "CHAN", "birth_date": "1990-05-20"}
    report = aggregate(det, vision)
    issues = [
        AuditIssue(
            code="EXTRACTION_DISAGREEMENT",
            field=c.path,
            severity="BLOCKER",
            message="两路抽取结果不一致, 保留双方原值待人工确认",
            confidence=1.0,
        )
        for c in report.comparisons
        if c.status == "DISAGREED"
    ]
    assert issues and resolve_verdict(issues) == "NEED_USER_FIX"
    # an agreement-only report never blocks
    agreed = aggregate(det, dict(det))
    assert agreed.disagreement_paths == []
    assert resolve_verdict([]) == "AUTO_PASS"
