"""
Orchestration pipeline: resolve extractor → extract → write output.

Adding a new backend:
  1. Implement BaseExtractor in doc_intel/extractors/your_extractor.py
  2. Add it to EXTRACTOR_REGISTRY below
  3. That's it — the CLI and future API pick it up automatically.
"""

from pathlib import Path
from typing import TYPE_CHECKING

from doc_intel.config import settings
from doc_intel.models.extraction_result import ExtractionResult
from doc_intel.output.json_writer import JsonWriter

if TYPE_CHECKING:
    from doc_intel.extractors.base import BaseExtractor

# ── Extractor registry ─────────────────────────────────────────────────────────
# Lazy imports keep startup fast and avoid importing optional heavy dependencies
# (torch, transformers) until they're actually needed.


def _get_extractor(name: str, model_id: str | None = None) -> "BaseExtractor":
    if name == "azure":
        from doc_intel.extractors.azure_doc_intel import AzureDocIntelExtractor

        return AzureDocIntelExtractor(model_id=model_id)
    if name == "claude":
        from doc_intel.extractors.claude_vision import ClaudeVisionExtractor

        return ClaudeVisionExtractor(model=model_id)
    if name == "vision":
        from doc_intel.extractors.vision_model import VisionModelExtractor

        return VisionModelExtractor()
    raise ValueError(
        f"Unknown extractor '{name}'. Available: azure, claude, vision"
    )


# ── Public API ─────────────────────────────────────────────────────────────────


def run(
    file_path: Path,
    *,
    extractor_name: str | None = None,
    model_id: str | None = None,
    output_dir: Path | None = None,
    write_output: bool = True,
) -> tuple[ExtractionResult, Path | None]:
    """
    Run the full extraction pipeline on a single document.

    Args:
        file_path: Path to the document to process.
        extractor_name: Which backend to use. Defaults to settings.default_extractor.
        output_dir: Where to write the JSON output. Defaults to settings.output_dir.
        write_output: Set False to skip writing to disk (useful in tests / API).

    Returns:
        A tuple of (ExtractionResult, output_path | None).
    """
    extractor_name = extractor_name or settings.default_extractor
    output_dir = output_dir or settings.output_dir

    extractor = _get_extractor(extractor_name, model_id=model_id)

    if not extractor.supports(file_path):
        raise ValueError(
            f"Extractor '{extractor_name}' does not support file type '{file_path.suffix}'"
        )

    print(f"[runner] Extracting '{file_path.name}' with extractor='{extractor_name}' ...")
    result = extractor.extract(file_path)
    print(
        f"[runner] Done. {len(result.fields)} fields, "
        f"{len(result.pages)} pages, {len(result.tables)} tables."
    )

    output_path: Path | None = None
    if write_output:
        writer = JsonWriter(output_dir)
        output_path = writer.write(result)
        print(f"[runner] Output written to: {output_path}")

    return result, output_path
