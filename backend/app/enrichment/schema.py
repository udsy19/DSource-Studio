"""MaterialEnrichment — the structured output both providers fill (one schema, no divergence).

Every attribute is {value, confidence, source}. source='missing' (value=None) is how the
model says "I don't know" instead of inventing — the NEVER-fake rule lives in the type.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Source(str, Enum):
    image = "image"
    description = "description"
    title = "title"
    spec_sheet = "spec_sheet"
    inferred = "inferred"
    missing = "missing"


class Attribute(BaseModel):
    value: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source: Source = Source.missing


class MaterialEnrichment(BaseModel):
    primary_material: Attribute = Field(default_factory=Attribute)
    secondary_materials: Attribute = Field(default_factory=Attribute)
    finish: Attribute = Field(default_factory=Attribute)
    color: Attribute = Field(default_factory=Attribute)
    upholstery: Attribute = Field(default_factory=Attribute)
    dimensions: Attribute = Field(default_factory=Attribute)
    weight: Attribute = Field(default_factory=Attribute)
    care: Attribute = Field(default_factory=Attribute)
