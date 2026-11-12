"""T025 — FR-036 independence, statically: the two extraction paths never import each other.

media_preprocessor is the only module the deterministic and vision paths may share; the
aggregator imports both. Any violation is a structural breach of the dual-path requirement,
catchable without running the pipeline.
"""

from __future__ import annotations

import ast
from pathlib import Path

AGENTS = Path(__file__).resolve().parents[2] / "backend" / "agents"


def imports(module: str) -> set[str]:
    tree = ast.parse((AGENTS / f"{module}.py").read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
        elif isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
    return {f.split(".")[-1] for f in found}


def agent_siblings(module: str) -> set[str]:
    """Only backend.agents sibling modules, ignoring shared stdlib/provider imports."""
    known = {"media_preprocessor", "deterministic_extractor", "vision_parser", "extraction_aggregator", "remediation"}
    return imports(module) & known


def test_deterministic_and_vision_paths_do_not_import_each_other() -> None:
    assert "vision_parser" not in imports("deterministic_extractor")
    assert "deterministic_extractor" not in imports("vision_parser")


def test_paths_share_only_media_preprocessor() -> None:
    det = agent_siblings("deterministic_extractor")
    vis = agent_siblings("vision_parser")
    assert "media_preprocessor" in det
    assert "media_preprocessor" in vis
    # the only backend.agents module both extraction paths may depend on
    shared = det & vis
    assert shared <= {"media_preprocessor"}


def test_aggregator_imports_both_extraction_paths() -> None:
    """plan.md §Structure Decision: extraction_aggregator imports both paths (FR-036 graph)."""
    agg = agent_siblings("extraction_aggregator")
    assert "deterministic_extractor" in agg
    assert "vision_parser" in agg


def test_paths_do_not_import_the_aggregator_back() -> None:
    assert "extraction_aggregator" not in agent_siblings("deterministic_extractor")
    assert "extraction_aggregator" not in agent_siblings("vision_parser")


def test_vision_parser_is_not_imported_by_intake_or_routes_layer_logic() -> None:
    intake_path = Path(__file__).resolve().parents[2] / "backend" / "services" / "document_intake.py"
    intake = intake_path.read_text(encoding="utf-8")
    assert "vision_parser" not in intake  # deterministic-only intake; vision is a separate pipeline stage
