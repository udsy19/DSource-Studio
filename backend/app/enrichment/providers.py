"""Vision-LLM enrichers behind one interface (mirrors routers/render.py's provider-agnostic
shape). Gemini for cheap near-duplicate enrichment, Claude for novel items. Both are driven by
the SAME Pydantic schema. SDK imports are lazy so importing this module is cheap and unconfigured
providers simply report available()=False rather than erroring.
"""

from __future__ import annotations

import base64
import io
from typing import Protocol

from PIL import Image

from ..config import settings
from .schema import MaterialEnrichment

_PROMPT = (
    "You are a furniture and decor cataloguer. From the product IMAGE, TITLE, and DESCRIPTION, "
    "extract material attributes. For each attribute set: value (concise, e.g. 'powder-coated "
    "steel', 'solid sheesham wood', 'matte', 'boucle'); confidence 0..1; and source = where the "
    "value came from (image | description | title | inferred). If an attribute is genuinely not "
    "determinable, set value=null, confidence=0, source='missing'. NEVER invent specifics that "
    "the image or text do not support.\n\nTITLE: {title}\nDESCRIPTION: {description}"
)


class VisionEnricher(Protocol):
    name: str
    def available(self) -> bool: ...
    def enrich(self, image: Image.Image, title: str, description: str | None) -> MaterialEnrichment | None: ...


def _jpeg_b64(image: Image.Image) -> str:
    buf = io.BytesIO()
    image.convert("RGB").save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode("ascii")


class GeminiEnricher:
    name = "gemini"

    def __init__(self) -> None:
        self._client = None

    def available(self) -> bool:
        return bool(settings.render_api_key)

    def enrich(self, image: Image.Image, title: str, description: str | None) -> MaterialEnrichment | None:
        if not self.available():
            return None
        from google import genai
        from google.genai import types

        if self._client is None:
            self._client = genai.Client(api_key=settings.render_api_key)
        resp = self._client.models.generate_content(
            model=settings.enrich_gemini_model,
            contents=[image, _PROMPT.format(title=title, description=description or "(none)")],
            config=types.GenerateContentConfig(
                response_mime_type="application/json", response_schema=MaterialEnrichment,
            ),
        )
        parsed = getattr(resp, "parsed", None)
        if isinstance(parsed, MaterialEnrichment):
            return parsed
        return MaterialEnrichment.model_validate_json(resp.text) if resp.text else None


class ClaudeEnricher:
    name = "claude"

    def __init__(self) -> None:
        self._client = None

    def available(self) -> bool:
        return bool(settings.anthropic_api_key)

    def enrich(self, image: Image.Image, title: str, description: str | None) -> MaterialEnrichment | None:
        if not self.available():
            return None
        import anthropic

        if self._client is None:
            self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        tool = {
            "name": "record_material_attributes",
            "description": "Record the product's extracted material attributes.",
            "input_schema": MaterialEnrichment.model_json_schema(),
        }
        msg = self._client.messages.create(
            model=settings.enrich_claude_model, max_tokens=1024, tools=[tool],
            tool_choice={"type": "tool", "name": "record_material_attributes"},
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                             "data": _jpeg_b64(image)}},
                {"type": "text", "text": _PROMPT.format(title=title, description=description or "(none)")},
            ]}],
        )
        for block in msg.content:
            if block.type == "tool_use":
                return MaterialEnrichment.model_validate(block.input)
        return None


def build_enrichers() -> dict[str, VisionEnricher]:
    return {"gemini": GeminiEnricher(), "claude": ClaudeEnricher()}
