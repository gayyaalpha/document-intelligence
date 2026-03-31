"""Tests for AzureDocIntelExtractor — all Azure calls are mocked."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from doc_intel.models.extraction_result import ExtractionResult


@pytest.fixture()
def extractor(mock_settings):
    """Create an AzureDocIntelExtractor with mocked Azure credentials."""
    with patch("doc_intel.extractors.azure_doc_intel.DocumentIntelligenceClient"):
        from doc_intel.extractors.azure_doc_intel import AzureDocIntelExtractor

        return AzureDocIntelExtractor(model_id="prebuilt-layout")


def test_supports_pdf(extractor):
    assert extractor.supports(Path("document.pdf")) is True


def test_supports_png(extractor):
    assert extractor.supports(Path("scan.png")) is True


def test_does_not_support_docx(extractor):
    assert extractor.supports(Path("report.docx")) is False


def test_extract_raises_file_not_found(extractor):
    with pytest.raises(FileNotFoundError):
        extractor.extract(Path("/nonexistent/document.pdf"))


def test_extract_raises_for_unsupported_type(extractor, tmp_path):
    fake_docx = tmp_path / "report.docx"
    fake_docx.write_text("not a real document")
    with pytest.raises(ValueError, match="Unsupported file type"):
        extractor.extract(fake_docx)


def _make_mock_azure_result():
    """Build a minimal mock of the Azure SDK AnalyzeResult."""
    result = MagicMock()
    result.api_version = "2024-11-30"
    result.content = "Sample document content"

    # One page
    page = MagicMock()
    page.page_number = 1
    page.width = 8.5
    page.height = 11.0
    page.unit = "inch"
    line = MagicMock()
    line.content = "Hello World"
    page.lines = [line]
    result.pages = [page]

    # One key-value pair
    kv = MagicMock()
    kv.key.content = "Invoice Number"
    kv.value.content = "INV-001"
    kv.confidence = 0.97
    kv.key.bounding_regions = []
    result.key_value_pairs = [kv]

    result.documents = []

    # One table
    table = MagicMock()
    table.row_count = 2
    table.column_count = 2
    cell_00 = MagicMock()
    cell_00.row_index, cell_00.column_index, cell_00.content = 0, 0, "Header A"
    cell_01 = MagicMock()
    cell_01.row_index, cell_01.column_index, cell_01.content = 0, 1, "Header B"
    cell_10 = MagicMock()
    cell_10.row_index, cell_10.column_index, cell_10.content = 1, 0, "Value A"
    cell_11 = MagicMock()
    cell_11.row_index, cell_11.column_index, cell_11.content = 1, 1, "Value B"
    table.cells = [cell_00, cell_01, cell_10, cell_11]
    result.tables = [table]

    return result


def test_extract_maps_fields_correctly(extractor, tmp_path):
    fake_pdf = tmp_path / "invoice.pdf"
    fake_pdf.write_bytes(b"%PDF-fake")

    mock_result = _make_mock_azure_result()
    extractor._client.begin_analyze_document.return_value.result.return_value = mock_result

    result: ExtractionResult = extractor.extract(fake_pdf)

    assert result.extractor == "azure"
    assert result.model_id == "prebuilt-layout"
    assert len(result.pages) == 1
    assert result.pages[0].content == "Hello World"
    assert len(result.fields) == 1
    assert result.fields[0].name == "Invoice Number"
    assert result.fields[0].value == "INV-001"
    assert result.fields[0].confidence == pytest.approx(0.97)
    assert len(result.tables) == 1
    assert result.tables[0][0] == ["Header A", "Header B"]
    assert result.tables[0][1] == ["Value A", "Value B"]
