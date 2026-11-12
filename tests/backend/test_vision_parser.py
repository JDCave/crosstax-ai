"""T021 tests — VisionParserAgent with a mocked provider (real model quality not yet accepted).

Rasterization is mocked at the injectable seam (production rasterizer pending team dependency
approval, plan.md §尚未完成). These tests pin the agent's request shape, response parsing, and
its handoff into the aggregator as a second comparable path.
"""

from __future__ import annotations

import json

import httpx
import pytest

from backend.agents.extraction_aggregator import aggregate
from backend.agents.vision_parser import VisionParserAgent, VisionPathError
from backend.core.bailian import BailianSettings


def settings(**overrides):
    return BailianSettings(model="qwen-vl-max", base_url="https://dashscope.test/compatible-mode/v1", **overrides)


def envelope(fields: dict[str, object]) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(fields)}}], "usage": {}})


def fake_pages() -> list[bytes]:
    return [b"\x89PNG fake-page-1", b"\x89PNG fake-page-2"]


async def test_parse_pages_sends_images_and_returns_flattened_fields() -> None:
    captured: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return envelope({"name.last_name": "CHAN", "name.first_name": "DEMO", "birth_date": None})

    agent = VisionParserAgent(settings(), httpx.MockTransport(handler))
    result = await agent.parse_pages(fake_pages(), "INDIVIDUAL")
    assert result.fields["name.last_name"] == "CHAN"
    assert result.fields["birth_date"] is None
    assert "name.middle_names" in result.fields  # full requested vocabulary returned, missing -> null
    body = captured[0]
    assert body["model"] == "qwen-vl-max"
    content = body["messages"][-1]["content"]
    assert any(part.get("type") == "image_url" for part in content)  # pages attached as image parts


async def test_unknown_response_keys_are_dropped_not_trusted() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return envelope({"name.last_name": "CHAN", "invented.path": "garbage"})

    agent = VisionParserAgent(settings(), httpx.MockTransport(handler))
    result = await agent.parse_pages(fake_pages(), "INDIVIDUAL")
    assert "invented.path" not in result.fields


async def test_non_json_provider_response_fails_as_path_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "I cannot parse this form"}}]})

    agent = VisionParserAgent(settings(), httpx.MockTransport(handler))
    with pytest.raises(VisionPathError) as excinfo:
        await agent.parse_pages(fake_pages(), "INDIVIDUAL")
    assert excinfo.value.reason == "BAD_PROVIDER_RESPONSE"


async def test_parse_pdf_requires_wired_rasterizer() -> None:
    from pathlib import Path

    from backend.agents.media_preprocessor import preprocess

    official = preprocess((Path("assets/crs-templates/crs-individual-ird.pdf")).read_bytes())
    agent = VisionParserAgent(settings(), httpx.MockTransport(lambda request: envelope({})))
    with pytest.raises(VisionPathError) as excinfo:
        await agent.parse_pdf(official)
    assert excinfo.value.reason == "RASTERIZER_NOT_WIRED"


async def test_vision_and_deterministic_outputs_are_comparable_by_the_aggregator() -> None:
    """The D4 oracle end-to-end (vision mocked): equal fields agree, differing ones are DISAGREED."""
    det = {"name.last_name": "CHAN", "name.first_name": "DEMO", "birth_date": "1990-05-20"}

    def handler(request: httpx.Request) -> httpx.Response:
        return envelope({"name.last_name": "CHAN", "name.first_name": "DEM0", "birth_date": "1990-05-20"})

    agent = VisionParserAgent(settings(), httpx.MockTransport(handler))
    vis = await agent.parse_pages(fake_pages(), "INDIVIDUAL")
    report = aggregate(det, vis.fields)
    statuses = {c.path: c.status for c in report.comparisons}
    assert statuses["name.last_name"] == "AGREED"
    assert statuses["birth_date"] == "AGREED"
    assert statuses["name.first_name"] == "DISAGREED"
    assert report.disagreement_paths == ["name.first_name"]
    assert report.rate is not None and report.rate < 1.0
