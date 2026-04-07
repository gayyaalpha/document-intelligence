"""
Document Intelligence — FastAPI application.

Endpoints:
    GET  /              Health check
    POST /extract       Extract structured data from an uploaded document
"""

import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse

from doc_intel.models.extraction_result import ExtractionResult
from doc_intel.pipeline.runner import run

app = FastAPI(
    title="Document Intelligence API",
    description="Extract structured data from documents using Azure Document Intelligence.",
    version="0.1.0",
)


# ── Health check ───────────────────────────────────────────────────────────────

@app.get("/")
def health_check():
    """Check the API is running."""
    return {"status": "ok", "version": "0.1.0"}


# ── Extract endpoint ───────────────────────────────────────────────────────────

@app.post("/extract", response_model=ExtractionResult)
async def extract(
    file: UploadFile = File(..., description="Document to extract (PDF, PNG, JPG, TIFF)"),
    model_id: str = Query(
        default="prebuilt-layout",
        description="Azure DI model: prebuilt-layout | prebuilt-invoice | prebuilt-document | prebuilt-read",
    ),
    extractor: str = Query(
        default="azure",
        description="Extraction backend: azure | vision",
    ),
):
    """
    Upload a document and extract structured data from it.

    Returns fields, page content, tables, and confidence scores.
    """
    # Validate file type
    suffix = Path(file.filename).suffix.lower() if file.filename else ""
    allowed = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"}
    if suffix not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: {sorted(allowed)}",
        )

    # Write uploaded file to a temp location on disk
    # Azure SDK needs a real file path, not an in-memory stream
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp_path = Path(tmp.name)
        content = await file.read()
        tmp.write(content)

    try:
        result, _ = run(
            tmp_path,
            extractor_name=extractor,
            model_id=model_id,
            write_output=False,   # don't save to disk, just return JSON
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {exc}")
    finally:
        # Always clean up the temp file
        tmp_path.unlink(missing_ok=True)

    return result
