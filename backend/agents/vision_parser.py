"""Vision extraction path (ADR-004, D4): rasterize at 300 DPI, ask Qwen-VL for the same flat fields.

FR-036 independence: the vision path shares only the shared layer with the deterministic path.
It MUST NOT import deterministic_extractor; the import graph is asserted by
tests/backend/test_agent_import_graph.py. Routed callers MUST go through VisionParserAgent
(AGENTS.md: no direct Vision API from routes).

Rasterization is an injected seam: the approved V1 dependency covers PDF parsing, not
image rendering (pdf2image needs poppler binaries). Production wiring is pending a team
dependency decision; the agent, prompt, and response parsing are real and test-wired.
"""

from __future__ import annotations

import base64
import json
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx

from backend.agents.media_preprocessor import PreprocessedPdf
from backend.core.ai_metrics import AICallMetrics
from backend.core.bailian import BailianSettings
from backend.infrastructure.bailian import BailianClient

VisionFailureReason = str

SYSTEM_PROMPT = (
    "You are a PDF form field extractor. Return ONLY a JSON object mapping the requested field "
    "paths to values read from the attached self-certification form images. Use null for blank or "
    "illegible fields. Preserve letters, digits and punctuation exactly as printed; do not guess."
)

# flattened contract paths per template (same vocabulary the aggregator compares)
_TEMPLATE_PATHS: dict[str, tuple[str, ...]] = {
    "INDIVIDUAL": (
        "x-header.ref_no",
        "name.title",
        "name.last_name",
        "name.first_name",
        "name.middle_names",
        "birth_date",
        "birth_place",
        "hk_identity.hkid_or_passport",
        "addresses[0].line1",
        "addresses[0].city",
        "addresses[0].subentity",
        "addresses[0].country",
        "addresses[0].post_code",
        "addresses[1].line1",
        "addresses[1].city",
        "addresses[1].subentity",
        "addresses[1].country",
        "addresses[1].post_code",
        "tax_residencies[0].jurisdiction",
        "tax_residencies[0].tin",
        "tax_residencies[0].no_tin_reason",
        "tax_residencies[0].reason_b_explanation",
        "declaration.signatory_name",
        "declaration.capacity",
        "declaration.signing_date",
    ),
}
_RASTERIZE_REQUIRED = VisionFailureReason("RASTERIZER_NOT_WIRED")


class VisionPathError(Exception):
    """Runtime failure of the vision path (FR-039: path-level failure, never a disagreement)."""

    def __init__(self, reason: VisionFailureReason, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message


@dataclass
class VisionExtraction:
    fields: dict[str, Any]
    metrics: AICallMetrics = field(default_factory=AICallMetrics)
    degraded: str | None = None


def paths_for_template(template: str | None) -> tuple[str, ...]:
    return _TEMPLATE_PATHS.get(template or "", ())


def _page_image_message(pages: Sequence[bytes]) -> dict[str, Any]:
    content: list[dict[str, Any]] = [
        {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(page).decode()}}
        for page in pages
    ]
    return {"role": "user", "content": content}


class VisionParserAgent:
    """Single public agent class per AGENTS.md; provider transport is injectable for tests."""

    def __init__(
        self,
        settings: BailianSettings,
        transport: httpx.AsyncBaseTransport | None = None,
        rasterize: Callable[[PreprocessedPdf], Sequence[bytes]] | None = None,
    ) -> None:
        self.settings = settings
        self.transport = transport
        self.rasterize = rasterize

    async def parse_pdf(self, pre: PreprocessedPdf) -> VisionExtraction:
        """The vision path starts from the shared layer's decrypted+enumerated output only."""
        if self.rasterize is None:
            raise VisionPathError(
                _RASTERIZE_REQUIRED, "300 DPI rasterizer is not wired (pending team dependency approval)"
            )
        try:
            pages = list(self.rasterize(pre))
        except Exception as error:
            raise VisionPathError("RASTERIZATION_FAILED", f"Page rasterization failed: {error}") from error
        return await self.parse_pages(pages, pre.template)

    async def parse_pages(self, pages: Sequence[bytes], template: str | None) -> VisionExtraction:
        requested = paths_for_template(template)
        if not pages:
            raise VisionPathError("NO_PAGES", "Vision path received no page images")
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": "Requested field paths: " + json.dumps(list(requested)) + ". Read the attached pages.",
            },
        ]
        metrics = AICallMetrics()
        deadline = time.monotonic() + self.settings.timeout_seconds
        async with httpx.AsyncClient(
            transport=self.transport,
            timeout=self.settings.timeout_seconds,
            follow_redirects=False,
            trust_env=False,  # ambient Windows NO_PROXY entries must not kill provider calls
        ) as client:
            provider = BailianClient(self.settings, client, metrics, deadline)
            body = await provider.complete([*messages, _page_image_message(pages)])
        try:
            text = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise VisionPathError("BAD_PROVIDER_RESPONSE", "Vision response missing choices") from error
        try:
            raw = json.loads(text) if isinstance(text, str) else text
        except (TypeError, ValueError) as error:
            raise VisionPathError("BAD_PROVIDER_RESPONSE", "Vision response is not JSON") from error
        if not isinstance(raw, dict):
            raise VisionPathError("BAD_PROVIDER_RESPONSE", "Vision response JSON is not an object")
        fields = {path: raw.get(path) for path in requested}
        return VisionExtraction(fields=fields, metrics=metrics)
