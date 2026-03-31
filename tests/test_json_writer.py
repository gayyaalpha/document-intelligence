"""Tests for JsonWriter."""

import json
from pathlib import Path

import pytest

from doc_intel.models.extraction_result import ExtractionResult
from doc_intel.output.json_writer import JsonWriter


def test_write_creates_file(tmp_path: Path, sample_extraction_result: ExtractionResult):
    writer = JsonWriter(output_dir=tmp_path)
    output_path = writer.write(sample_extraction_result)

    assert output_path.exists()
    assert output_path.suffix == ".json"


def test_write_valid_json(tmp_path: Path, sample_extraction_result: ExtractionResult):
    writer = JsonWriter(output_dir=tmp_path)
    output_path = writer.write(sample_extraction_result)

    with open(output_path) as f:
        data = json.load(f)

    assert data["extractor"] == "azure"
    assert data["model_id"] == "prebuilt-invoice"
    assert len(data["fields"]) == 2
    assert data["fields"][0]["name"] == "VendorName"


def test_write_custom_output_path(tmp_path: Path, sample_extraction_result: ExtractionResult):
    custom_path = tmp_path / "custom_output.json"
    writer = JsonWriter(output_dir=tmp_path)
    output_path = writer.write(sample_extraction_result, output_path=custom_path)

    assert output_path == custom_path
    assert custom_path.exists()


def test_write_creates_output_dir(tmp_path: Path, sample_extraction_result: ExtractionResult):
    nested_dir = tmp_path / "deep" / "nested"
    writer = JsonWriter(output_dir=nested_dir)
    output_path = writer.write(sample_extraction_result)

    assert output_path.exists()


def test_roundtrip_preserves_fields(tmp_path: Path, sample_extraction_result: ExtractionResult):
    writer = JsonWriter(output_dir=tmp_path)
    output_path = writer.write(sample_extraction_result)

    with open(output_path) as f:
        data = json.load(f)

    assert data["confidence"] == pytest.approx(0.965)
    assert len(data["pages"]) == 1
    assert data["pages"][0]["unit"] == "inch"
    assert len(data["tables"]) == 1
    assert data["tables"][0][0] == ["Item", "Qty", "Price"]
