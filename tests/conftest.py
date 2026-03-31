"""Shared test fixtures."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from doc_intel.models.extraction_result import DocumentField, ExtractionResult, PageInfo

# ── Sample data ────────────────────────────────────────────────────────────────

SAMPLE_PDF = Path(__file__).parent / "fixtures" / "sample.pdf"
SAMPLE_PNG = Path(__file__).parent / "fixtures" / "sample.png"


@pytest.fixture()
def sample_extraction_result(tmp_path: Path) -> ExtractionResult:
    """A minimal ExtractionResult for use in output writer tests."""
    return ExtractionResult(
        source_file=tmp_path / "invoice.pdf",
        extractor="azure",
        model_id="prebuilt-invoice",
        fields=[
            DocumentField(name="VendorName", value="Acme Corp", confidence=0.98),
            DocumentField(name="InvoiceTotal", value=1250.00, confidence=0.95),
        ],
        pages=[
            PageInfo(page_number=1, width=8.5, height=11.0, unit="inch", content="Sample text")
        ],
        tables=[
            [["Item", "Qty", "Price"], ["Widget A", "10", "$125.00"]]
        ],
        confidence=0.965,
    )


@pytest.fixture()
def mock_azure_client():
    """Patch the Azure DocumentIntelligenceClient with a mock."""
    with patch(
        "doc_intel.extractors.azure_doc_intel.DocumentIntelligenceClient"
    ) as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        yield mock_instance


@pytest.fixture()
def mock_settings(monkeypatch):
    """Inject minimal settings so tests don't require a real .env file."""
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "https://fake.azure.com/")
    monkeypatch.setenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", "fake-key-00000000")
