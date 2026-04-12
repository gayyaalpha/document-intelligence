"""
Document Intelligence — FastAPI application.

Endpoints:
    GET  /                    Health check
    POST /extract/azure       Extract using Azure Document Intelligence
    POST /extract/claude      Extract using Claude Vision
"""

import tempfile
from enum import Enum
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile

from doc_intel.models.extraction_result import ExtractionResult
from doc_intel.pipeline.runner import run

app = FastAPI(
    title="Document Intelligence API",
    description="Extract structured data from documents using Azure Document Intelligence and Claude Vision.",
    version="0.2.0",
)

ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"}


# ── Enums for Swagger dropdowns ───────────────────────────────────────────────

class AzureModel(str, Enum):
    prebuilt_layout = "prebuilt-layout"
    prebuilt_invoice = "prebuilt-invoice"
    prebuilt_read = "prebuilt-read"


class ClaudeModel(str, Enum):
    sonnet_4_6 = "claude-sonnet-4-6"
    opus_4_6 = "claude-opus-4-6"
    haiku_4_5 = "claude-haiku-4-5"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _validate_and_save(file: UploadFile, content: bytes) -> Path:
    """Validate file type and write to a temp file. Returns the temp path."""
    suffix = Path(file.filename).suffix.lower() if file.filename else ""
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: {sorted(ALLOWED_EXTENSIONS)}",
        )
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp_path = Path(tmp.name)
    tmp.write(content)
    tmp.close()
    return tmp_path


# ── Health check ───────────────────────────────────────────────────────────────

@app.get("/")
def health_check():
    """Check the API is running."""
    return {"status": "ok", "version": "0.2.0"}


# ── Azure extraction endpoint ─────────────────────────────────────────────────

@app.post("/extract/azure", response_model=ExtractionResult, tags=["Extraction"])
async def extract_azure(
    file: UploadFile = File(..., description="Document to extract (PDF, PNG, JPG, TIFF)"),
    model_id: AzureModel = Query(
        default=AzureModel.prebuilt_layout,
        description="Azure Document Intelligence model",
    ),
):
    """
    Extract structured data using **Azure Document Intelligence**.

    Choose a prebuilt model from the dropdown and upload a document.
    """
    content = await file.read()
    tmp_path = _validate_and_save(file, content)

    try:
        result, _ = run(
            tmp_path,
            extractor_name="azure",
            model_id=model_id.value,
            write_output=False,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {exc}")
    finally:
        tmp_path.unlink(missing_ok=True)

    return result


# ── Claude Vision extraction endpoint ─────────────────────────────────────────

@app.post("/extract/claude", response_model=ExtractionResult, tags=["Extraction"])
async def extract_claude(
    file: UploadFile = File(..., description="Document to extract (PDF, PNG, JPG, TIFF)"),
    model_id: ClaudeModel = Query(
        default=ClaudeModel.sonnet_4_6,
        description="Anthropic Claude model",
    ),
):
    """
    Extract structured data using **Claude Vision** (Anthropic API).

    Choose a Claude model from the dropdown and upload a document.
    """
    content = await file.read()
    tmp_path = _validate_and_save(file, content)

    try:
        result, _ = run(
            tmp_path,
            extractor_name="claude",
            model_id=model_id.value,
            write_output=False,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {exc}")
    finally:
        tmp_path.unlink(missing_ok=True)

    return result
