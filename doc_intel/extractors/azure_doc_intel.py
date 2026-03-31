"""Azure Document Intelligence extraction backend."""

from pathlib import Path

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest
from azure.core.credentials import AzureKeyCredential

from doc_intel.config import settings
from doc_intel.extractors.base import BaseExtractor
from doc_intel.models.extraction_result import (
    BoundingBox,
    DocumentField,
    ExtractionResult,
    PageInfo,
)


def _to_bounding_box(polygon: list[float] | None) -> BoundingBox | None:
    """Convert an Azure polygon (flat list of x,y pairs) to a BoundingBox."""
    if not polygon or len(polygon) < 8:
        return None
    xs = polygon[0::2]
    ys = polygon[1::2]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    return BoundingBox(x=x_min, y=y_min, width=x_max - x_min, height=y_max - y_min)


class AzureDocIntelExtractor(BaseExtractor):
    """
    Extraction backend using Azure Document Intelligence.

    Uses the `azure-ai-documentintelligence` SDK (2023+ package, NOT the
    deprecated azure-ai-formrecognizer). Supports the following prebuilt models:
        - prebuilt-layout    : General layout, tables, text (recommended starting point)
        - prebuilt-read      : Plain text extraction only
        - prebuilt-document  : Key-value pairs + layout
        - prebuilt-invoice   : Structured invoice fields
        - prebuilt-receipt   : Structured receipt fields

    Configure via AZURE_DI_MODEL_ID in your .env file.
    """

    def __init__(self, model_id: str | None = None) -> None:
        self._model_id = model_id or settings.azure_di_model_id
        self._client = DocumentIntelligenceClient(
            endpoint=settings.azure_document_intelligence_endpoint,
            credential=AzureKeyCredential(settings.azure_document_intelligence_key),
        )

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

        with open(file_path, "rb") as f:
            poller = self._client.begin_analyze_document(
                model_id=self._model_id,
                body=f,
                content_type="application/octet-stream",
            )
        result = poller.result()

        return self._map_result(file_path, result)

    def extract_from_url(self, url: str, source_label: str = "url") -> ExtractionResult:
        """Convenience method: extract from a publicly accessible URL."""
        poller = self._client.begin_analyze_document(
            model_id=self._model_id,
            body=AnalyzeDocumentRequest(url_source=url),
        )
        result = poller.result()
        return self._map_result(Path(source_label), result)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _map_result(self, source_file: Path, result: object) -> ExtractionResult:
        """Map the raw Azure SDK result to our ExtractionResult schema."""
        fields: list[DocumentField] = []
        pages: list[PageInfo] = []
        tables: list[list[list[str]]] = []

        # Pages
        for page in getattr(result, "pages", []) or []:
            content_lines = [
                line.content for line in (getattr(page, "lines", []) or [])
            ]
            pages.append(
                PageInfo(
                    page_number=page.page_number,
                    width=getattr(page, "width", None),
                    height=getattr(page, "height", None),
                    unit=getattr(page, "unit", None),
                    content="\n".join(content_lines) if content_lines else None,
                )
            )

        # Key-value pairs (available in prebuilt-document / specialised models)
        for kv in getattr(result, "key_value_pairs", []) or []:
            key_obj = getattr(kv, "key", None)
            value_obj = getattr(kv, "value", None)
            if not key_obj:
                continue
            key_content = getattr(key_obj, "content", "") or ""
            value_content = getattr(value_obj, "content", None) if value_obj else None
            confidence = getattr(kv, "confidence", None)
            polygon = getattr(key_obj, "bounding_regions", [])
            bb = None
            if polygon:
                bb = _to_bounding_box(getattr(polygon[0], "polygon", None))
            fields.append(
                DocumentField(
                    name=key_content,
                    value=value_content,
                    raw_value=value_content,
                    confidence=confidence,
                    bounding_box=bb,
                )
            )

        # Structured fields (available in prebuilt-invoice and similar models)
        for doc in getattr(result, "documents", []) or []:
            for field_name, field_val in (getattr(doc, "fields", {}) or {}).items():
                if field_val is None:
                    continue
                value = getattr(field_val, "value", None) or getattr(
                    field_val, "content", None
                )
                confidence = getattr(field_val, "confidence", None)
                polygon = getattr(field_val, "bounding_regions", [])
                bb = None
                if polygon:
                    bb = _to_bounding_box(getattr(polygon[0], "polygon", None))
                fields.append(
                    DocumentField(
                        name=field_name,
                        value=value,
                        raw_value=str(value) if value is not None else None,
                        confidence=confidence,
                        bounding_box=bb,
                    )
                )

        # Tables
        for table in getattr(result, "tables", []) or []:
            row_count = getattr(table, "row_count", 0)
            col_count = getattr(table, "column_count", 0)
            grid: list[list[str]] = [[""] * col_count for _ in range(row_count)]
            for cell in getattr(table, "cells", []) or []:
                r, c = cell.row_index, cell.column_index
                grid[r][c] = getattr(cell, "content", "") or ""
            tables.append(grid)

        # Average confidence
        confidences = [f.confidence for f in fields if f.confidence is not None]
        avg_confidence = sum(confidences) / len(confidences) if confidences else None

        return ExtractionResult(
            source_file=source_file,
            extractor="azure",
            model_id=self._model_id,
            fields=fields,
            pages=pages,
            tables=tables,
            confidence=avg_confidence,
            metadata={
                "api_version": getattr(result, "api_version", None),
                "content_length": len(getattr(result, "content", "") or ""),
            },
        )
