"""Core output schema — every extraction backend produces an ExtractionResult."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class BoundingBox(BaseModel):
    """Normalised bounding box (0.0–1.0 of page dimensions)."""

    x: float
    y: float
    width: float
    height: float


class DocumentField(BaseModel):
    """A single extracted key-value pair from the document."""

    name: str
    value: Any = None
    confidence: float | None = None
    bounding_box: BoundingBox | None = None
    # Raw value before any type coercion (useful for debugging)
    raw_value: str | None = None


class PageInfo(BaseModel):
    page_number: int
    width: float | None = None
    height: float | None = None
    unit: str | None = None  # e.g. "inch", "pixel"
    # Full page text content (from layout/read models)
    content: str | None = None


class ExtractionResult(BaseModel):
    """
    Backend-agnostic extraction envelope.

    Both AzureDocIntelExtractor and future vision backends return this type,
    so output writers, the pipeline, and the future API layer deal with one
    consistent schema.
    """

    # Source document
    source_file: Path
    # Which extractor produced this result
    extractor: str
    # Model/version used
    model_id: str | None = None

    # Structured fields extracted from the document
    fields: list[DocumentField] = Field(default_factory=list)
    # Per-page information (text content, dimensions)
    pages: list[PageInfo] = Field(default_factory=list)
    # Raw tables as list-of-list-of-str (header row first)
    tables: list[list[list[str]]] = Field(default_factory=list)

    # Overall confidence (average of field confidences if not provided directly)
    confidence: float | None = None

    # Timestamps
    extracted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Catch-all for backend-specific metadata not covered above
    metadata: dict[str, Any] = Field(default_factory=dict)
