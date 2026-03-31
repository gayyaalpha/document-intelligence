"""Abstract base class for all extraction backends."""

from abc import ABC, abstractmethod
from pathlib import Path

from doc_intel.models.extraction_result import ExtractionResult


class BaseExtractor(ABC):
    """
    Every extraction backend (Azure Document Intelligence, vision models, etc.)
    must implement this interface. The pipeline and CLI work against this
    abstraction — swapping backends requires no changes outside the extractor.
    """

    @abstractmethod
    def extract(self, file_path: Path) -> ExtractionResult:
        """
        Run extraction on a single document file.

        Args:
            file_path: Path to the document (PDF, PNG, JPEG, TIFF, BMP, HEIF).

        Returns:
            An ExtractionResult containing all extracted fields, page content,
            and tables.

        Raises:
            FileNotFoundError: If file_path does not exist.
            ValueError: If the file type is not supported by this extractor.
        """
        ...

    @abstractmethod
    def supports(self, file_path: Path) -> bool:
        """
        Return True if this extractor can handle the given file type.

        Use this to guard calls to extract() or to auto-select an extractor.
        """
        ...

    # Shared helper — available to all subclasses
    SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(
        {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".heif"}
    )
