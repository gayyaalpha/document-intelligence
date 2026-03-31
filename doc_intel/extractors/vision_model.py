"""
Vision model extraction backend — placeholder for Phase 2.

Replace the NotImplementedError bodies with real implementation when you
integrate a fine-tuned vision model (e.g. Florence-2, Donut, LLaVA, or a
custom model deployed on Azure ML / Hugging Face Inference Endpoints).
"""

from pathlib import Path

from doc_intel.extractors.base import BaseExtractor
from doc_intel.models.extraction_result import ExtractionResult


class VisionModelExtractor(BaseExtractor):
    """
    Extraction backend using a fine-tuned vision model.

    Intended for Phase 2 experimentation. Currently a stub.

    To implement:
    1. Load your model in __init__ (local weights or remote endpoint)
    2. Implement extract() to call the model and map its output to ExtractionResult
    3. Update SUPPORTED_EXTENSIONS if your model handles additional formats
    """

    def __init__(self, model_path: str | None = None) -> None:
        self._model_path = model_path
        # TODO Phase 2: load model weights / initialise inference client here

    def supports(self, file_path: Path) -> bool:
        # Images only for now — PDFs need pre-rendering to images first
        image_extensions = frozenset({".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"})
        return file_path.suffix.lower() in image_extensions

    def extract(self, file_path: Path) -> ExtractionResult:
        raise NotImplementedError(
            "VisionModelExtractor is not yet implemented. "
            "This is a Phase 2 feature — implement in doc_intel/extractors/vision_model.py."
        )
