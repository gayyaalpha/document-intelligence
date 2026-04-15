# Document Intelligence

A document extraction service that extracts structured data from PDFs and images using two interchangeable backends: **Azure Document Intelligence** (trained models, deterministic, character-accurate OCR) and **Claude Vision** (prompt-driven, flexible schema, handles novel document types). Returns clean, Pydantic-validated JSON.

Built with a pluggable extractor architecture so new backends can be added without touching the core pipeline.

---

## Live Demo

> Coming soon — Azure App Service deployment in progress.

Interactive API docs (Swagger UI) will be available at the live URL where you can upload a document, pick an extractor and model from the dropdowns, and see the JSON output in real time.

---

## Features

- Two extraction backends exposed as separate endpoints:
  - **Azure Document Intelligence** — `prebuilt-layout`, `prebuilt-invoice`, `prebuilt-read`
  - **Claude Vision** — Opus 4.6, Sonnet 4.6, Haiku 4.5
- Multi-page PDFs processed in a single API call per backend (no per-page loops, no cross-page schema drift)
- Document-type classification built into the Claude extractor (invoice, receipt, utility bill, payslip, tax document, bank statement, purchase order, technical drawing, other)
- Canonical snake_case schema per document type (prompted, not trained)
- Supports PDF, PNG, JPG, JPEG, TIFF, BMP
- FastAPI REST API with Swagger dropdowns for extractor and model selection
- CLI for local document processing
- Pluggable extractor architecture — add a new backend without touching the pipeline

---

## Architecture

```
CLI (run.py)          REST API (FastAPI)
      └──────────────────────┘
                 │
                 ▼
         Pipeline (runner.py)
                 │
                 ▼
         BaseExtractor (ABC)
            /          \
           /            \
AzureDocIntelExtractor   ClaudeVisionExtractor
          │                       │
          ▼                       ▼
    Azure DI API         Anthropic Messages API
                                  │
                                  ▼
         ExtractionResult (Pydantic)
                 │
                 ▼
          JSON output
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| API Framework | FastAPI |
| Web Server | Uvicorn |
| Document Extraction | Azure Document Intelligence, Anthropic Claude (Opus / Sonnet / Haiku 4.x) |
| PDF rendering | PyMuPDF |
| Data Validation | Pydantic v2 |
| Configuration | pydantic-settings |
| Cloud Hosting | Azure App Service |

---

## Project Structure

```
document-intelligence/
├── doc_intel/
│   ├── api/
│   │   └── main.py              # FastAPI app — /extract/azure, /extract/claude
│   ├── extractors/
│   │   ├── base.py              # BaseExtractor abstract class
│   │   ├── azure_doc_intel.py   # Azure DI backend
│   │   └── claude_vision.py     # Claude Vision backend (multi-image single-call)
│   ├── models/
│   │   ├── extraction_result.py # Core output schema
│   │   └── document_types.py    # Domain-specific schemas
│   ├── output/
│   │   └── json_writer.py       # JSON file writer
│   ├── pipeline/
│   │   └── runner.py            # Orchestration pipeline
│   └── config.py                # Settings from environment variables
├── docs/
│   └── findings.md              # Comparative analysis of the two backends
├── tests/                       # Mock-based tests (no cloud credentials needed)
├── inputs/                      # Drop documents here (gitignored)
├── outputs/                     # Extracted JSON lands here (gitignored)
├── notebooks/                   # Jupyter exploration notebooks
├── run.py                       # CLI entry point
├── requirements.txt
└── pyproject.toml
```

---

## Getting Started

### Prerequisites
- Python 3.11+
- Azure Document Intelligence resource ([create one](https://portal.azure.com))
- Anthropic API key ([create one](https://console.anthropic.com)) — only required if you want to use the Claude extractor

### Installation

```bash
git clone https://github.com/gayyaalpha/document-intelligence.git
cd document-intelligence

python3.11 -m venv .venv
source .venv/bin/activate

pip install -e ".[dev,api]"
```

### Configuration

```bash
cp .env.example .env
```

Fill in your credentials in `.env`:

```
# Azure Document Intelligence
AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT=https://<your-resource>.cognitiveservices.azure.com/
AZURE_DOCUMENT_INTELLIGENCE_KEY=<your-key>
AZURE_DI_MODEL_ID=prebuilt-layout

# Anthropic (Claude Vision)
ANTHROPIC_API_KEY=<your-anthropic-key>
ANTHROPIC_MODEL=claude-opus-4-6

# Which extractor to use by default: azure | claude
DEFAULT_EXTRACTOR=azure
```

### Run locally

**API:**
```bash
uvicorn doc_intel.api.main:app --reload
# Open http://localhost:8000/docs
```

**CLI (Azure):**
```bash
python run.py inputs/your-document.pdf
python run.py inputs/invoice.pdf --model prebuilt-invoice
```

**CLI (Claude):**
```bash
python run.py inputs/your-document.pdf --extractor claude --model claude-sonnet-4-6
```

### Run tests

```bash
pytest
```

---

## API Endpoints

### `GET /`
Health check.

```json
{ "status": "ok", "version": "0.2.0" }
```

### `POST /extract/azure`

Extract with Azure Document Intelligence.

**Parameters:**
| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `file` | file | yes | — | Document to extract (PDF, PNG, JPG, TIFF, BMP) |
| `model_id` | enum | no | `prebuilt-layout` | `prebuilt-layout`, `prebuilt-invoice`, `prebuilt-read` |

### `POST /extract/claude`

Extract with Claude Vision. Multi-page PDFs are sent as one API call with all page images attached, producing a single unified extraction.

**Parameters:**
| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `file` | file | yes | — | Document to extract (PDF, PNG, JPG, TIFF, BMP) |
| `model_id` | enum | no | `claude-sonnet-4-6` | `claude-opus-4-6`, `claude-sonnet-4-6`, `claude-haiku-4-5` |

**Response (both endpoints):** `ExtractionResult` — Pydantic-validated JSON containing `fields`, `pages`, `tables`, `confidence`, and backend-specific metadata (Claude additionally returns `document_type` and `document_type_confidence` in metadata).

---

## Findings

A detailed comparison of the two backends — strengths, weaknesses, OCR accuracy across Claude tiers, schema consistency across runs, and architectural recommendations — lives in [`docs/findings.md`](docs/findings.md). Headline points:

- **Azure is byte-deterministic.** Claude Vision is not, even at Opus.
- **Claude Vision OCR is tier-dependent.** Haiku misreads long alphanumeric identifiers; Opus was character-perfect across three runs on the tested document.
- **Claude Vision schema stability is *not* tier-dependent** — peripheral field names, table splits, and even field presence drift between runs at every tier.
- **Haiku matches Azure on per-page cost** (~$0.01/page) because Claude's vision image tokens are priced the same across all tiers. Only output text scales with tier.

---

## Roadmap

- [x] Phase 1 — Core extraction pipeline + CLI (Azure DI)
- [x] Phase 2a — FastAPI REST API + Azure App Service deployment
- [x] Phase 2b — Claude Vision backend (Opus / Sonnet / Haiku) with document-type classification
- [x] Phase 2c — Comparative findings write-up (`docs/findings.md`)
- [ ] Phase 3 — Docker: containerise the API for portable local dev and deployment
- [ ] Phase 4 — Self-hosted document extraction backend as a third option (candidates: Docling, Tesseract, Unstructured)
- [ ] Phase 5 — Side-by-side comparison endpoint (run the same document through multiple backends and diff the output)
- [ ] Phase 6 — Frontend with comparison UI

---

## Author

**Gayashan Dewanarayana**
[GitHub](https://github.com/gayyaalpha)
