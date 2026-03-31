"""Write ExtractionResult to a JSON file."""

import json
from pathlib import Path

from doc_intel.models.extraction_result import ExtractionResult


class JsonWriter:
    """Serialise an ExtractionResult to an indented JSON file."""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def write(self, result: ExtractionResult, output_path: Path | None = None) -> Path:
        """
        Write result to JSON and return the output file path.

        Args:
            result: The extraction result to serialise.
            output_path: Optional explicit destination. If omitted, the file is
                         named after the source document and placed in output_dir.

        Returns:
            Path to the written JSON file.
        """
        if output_path is None:
            stem = result.source_file.stem
            output_path = self.output_dir / f"{stem}.json"

        data = result.model_dump(mode="json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)

        return output_path
