#!/usr/bin/env python3
"""
CLI entry point for Document Intelligence.

Usage examples:
    python run.py invoice.pdf
    python run.py drawing.png --extractor azure --model prebuilt-layout
    python run.py report.pdf --output-dir /tmp/results
    python run.py invoice.pdf --extractor azure --model prebuilt-invoice --dry-run
"""

import argparse
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract structured data from documents using Document Intelligence.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("file", type=Path, help="Path to the document to process")
    parser.add_argument(
        "--extractor",
        default=None,
        choices=["azure", "vision"],
        help="Extraction backend to use (default: from .env DEFAULT_EXTRACTOR)",
    )
    parser.add_argument(
        "--model",
        default=None,
        dest="model_id",
        help=(
            "Azure DI model ID to use, e.g. prebuilt-layout, prebuilt-invoice "
            "(overrides AZURE_DI_MODEL_ID in .env)"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for JSON output (default: from .env OUTPUT_DIR)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run extraction but do not write output to disk",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    file_path: Path = args.file.resolve()
    if not file_path.exists():
        print(f"Error: file not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    # Override model ID via CLI if provided
    if args.model_id:
        import os

        os.environ["AZURE_DI_MODEL_ID"] = args.model_id

    from doc_intel.pipeline.runner import run

    try:
        result, output_path = run(
            file_path,
            extractor_name=args.extractor,
            output_dir=args.output_dir,
            write_output=not args.dry_run,
        )
    except (ValueError, FileNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        import json

        print(json.dumps(result.model_dump(mode="json"), indent=2, default=str))
    else:
        print(f"\nDone. Result saved to: {output_path}")


if __name__ == "__main__":
    main()
