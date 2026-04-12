"""Claude Vision extraction backend using Anthropic's API."""

import base64
import json
import re
from pathlib import Path

import anthropic
import pymupdf

from doc_intel.config import settings
from doc_intel.extractors.base import BaseExtractor
from doc_intel.models.extraction_result import (
    DocumentField,
    ExtractionResult,
    PageInfo,
)

EXTRACTION_PROMPT = """You are a document extraction assistant.

Analyse this document image and extract ALL fields you can find.
Return a JSON object with this exact structure:

{
  "fields": [
    {"name": "field_name", "value": "field_value", "confidence": 0.95}
  ],
  "page_summary": "brief description of what this page contains"
}

Rules:
- Extract every key-value pair you can find in the document
- Use descriptive snake_case field names (e.g. invoice_total, customer_name)
- confidence is your certainty from 0.0 to 1.0
- Return ONLY the JSON object, no other text
"""


def _pdf_page_to_base64(pdf_path: Path, page_number: int) -> str:
    """Convert a single PDF page to a base64 encoded PNG image."""
    doc = pymupdf.open(str(pdf_path))
    page = doc[page_number]
    # Render at 2x zoom for better quality
    mat = pymupdf.Matrix(2, 2)
    pix = page.get_pixmap(matrix=mat)
    img_bytes = pix.tobytes("png")
    doc.close()
    return base64.standard_b64encode(img_bytes).decode("utf-8")


def _image_to_base64(image_path: Path) -> str:
    """Convert an image file to base64."""
    with open(image_path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


def _get_media_type(file_path: Path) -> str:
    """Return the correct media type for the file."""
    suffix = file_path.suffix.lower()
    media_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".tiff": "image/tiff",
        ".tif": "image/tiff",
        ".bmp": "image/bmp",
    }
    return media_types.get(suffix, "image/png")


class ClaudeVisionExtractor(BaseExtractor):
    """
    Extraction backend using Claude's vision capabilities via Anthropic API.

    Converts documents to images and sends them to Claude with a structured
    extraction prompt. Claude reasons about the document visually and returns
    fields in a consistent schema regardless of document layout.

    Supports: PDF, PNG, JPG, JPEG, TIFF, BMP
    """

    def __init__(self, model: str | None = None) -> None:
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._model = model or settings.anthropic_model

    def supports(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS

    def extract(self, file_path: Path) -> ExtractionResult:
        if not file_path.exists():
            raise FileNotFoundError(f"Document not found: {file_path}")
        if not self.supports(file_path):
            raise ValueError(
                f"Unsupported file type '{file_path.suffix}'. "
                f"Supported: {sorted(self.SUPPORTED_EXTENSIONS)}"
            )

        suffix = file_path.suffix.lower()

        if suffix == ".pdf":
            return self._extract_pdf(file_path)
        else:
            return self._extract_image(file_path)

    def _extract_pdf(self, file_path: Path) -> ExtractionResult:
        """Extract from PDF by processing each page as an image."""
        doc = pymupdf.open(str(file_path))
        page_count = len(doc)
        doc.close()

        all_fields: list[DocumentField] = []
        pages: list[PageInfo] = []

        for page_num in range(page_count):
            print(f"[claude-vision] Processing page {page_num + 1}/{page_count}...")

            image_b64 = _pdf_page_to_base64(file_path, page_num)
            fields, summary = self._call_claude(image_b64, "image/png")

            all_fields.extend(fields)
            pages.append(PageInfo(
                page_number=page_num + 1,
                content=summary,
            ))

        return self._build_result(file_path, all_fields, pages)

    def _extract_image(self, file_path: Path) -> ExtractionResult:
        """Extract from a single image file."""
        media_type = _get_media_type(file_path)
        image_b64 = _image_to_base64(file_path)
        fields, summary = self._call_claude(image_b64, media_type)

        pages = [PageInfo(page_number=1, content=summary)]
        return self._build_result(file_path, fields, pages)

    def _call_claude(
        self, image_b64: str, media_type: str
    ) -> tuple[list[DocumentField], str]:
        """Send image to Claude and parse the response."""
        response = self._client.messages.create(
            model=self._model,
            max_tokens=2048,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": EXTRACTION_PROMPT,
                        },
                    ],
                }
            ],
        )

        raw_text = response.content[0].text
        return self._parse_response(raw_text)

    def _parse_response(self, raw_text: str) -> tuple[list[DocumentField], str]:
        """Parse Claude's JSON response into DocumentField objects."""
        # Strip markdown code blocks if Claude wrapped the JSON
        cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", raw_text).strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            # Claude returned something unexpected — return empty
            return [], raw_text

        fields: list[DocumentField] = []
        for item in data.get("fields", []):
            fields.append(
                DocumentField(
                    name=item.get("name", "unknown"),
                    value=item.get("value"),
                    raw_value=str(item.get("value", "")),
                    confidence=item.get("confidence"),
                )
            )

        summary = data.get("page_summary", "")
        return fields, summary

    def _build_result(
        self,
        source_file: Path,
        fields: list[DocumentField],
        pages: list[PageInfo],
    ) -> ExtractionResult:
        confidences = [f.confidence for f in fields if f.confidence is not None]
        avg_confidence = sum(confidences) / len(confidences) if confidences else None

        return ExtractionResult(
            source_file=source_file,
            extractor="claude-vision",
            model_id=self._model,
            fields=fields,
            pages=pages,
            tables=[],
            confidence=avg_confidence,
            metadata={"backend": "anthropic", "model": self._model},
        )
