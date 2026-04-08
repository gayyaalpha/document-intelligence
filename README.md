# Document Intelligence

A document extraction service that uses **Azure Document Intelligence** to extract structured data from PDFs and images, returning clean JSON output.

Built with a pluggable extractor architecture — designed to support multiple backends (Azure DI, vision models, LLMs) without changing the core pipeline.

---

## Live Demo

> Coming soon — Azure App Service deployment in progress.

Interactive API docs (Swagger UI) will be available at the live URL where you can upload a document and see extraction results in real time.

---

## Features

- Extract structured fields, tables, and page content from documents
- Supports PDF, PNG, JPG, JPEG, TIFF, BMP
- Multiple Azure prebuilt models: `prebuilt-layout`, `prebuilt-invoice`, `prebuilt-read`
- REST API built with FastAPI
- CLI for local document processing
- Pluggable extractor architecture — swap backends without touching the pipeline

---

## Architecture

```
CLI (run.py)          REST API (FastAPI)
      └──────────────────────┘
                 ↓
         Pipeline (runner.py)
                 ↓
         BaseExtractor (ABC)
                 ↓
    AzureDocIntelExtractor   VisionModelExtractor (Phase 2)
                 ↓
           Azure DI API
                 ↓
         ExtractionResult (Pydantic)
                 ↓
          JSON output
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| API Framework | FastAPI |
| Web Server | Uvicorn |
| Document Extraction | Azure Document Intelligence |
| Data Validation | Pydantic v2 |
| Configuration | pydantic-settings |
| Cloud Hosting | Azure App Service |

---

## Project Structure

```
document-intelligence/
├── doc_intel/
│   ├── api/
│   │   └── main.py          # FastAPI application
│   ├── extractors/
│   │   ├── base.py          # BaseExtractor abstract class
│   │   ├── azure_doc_intel.py  # Azure DI backend
│   │   └── vision_model.py  # Vision model backend (Phase 2)
│   ├── models/
│   │   ├── extraction_result.py  # Core output schema
│   │   └── document_types.py     # Domain-specific schemas
│   ├── output/
│   │   └── json_writer.py   # JSON file writer
│   ├── pipeline/
│   │   └── runner.py        # Orchestration pipeline
│   └── config.py            # Settings from environment variables
├── tests/                   # Mock-based tests (no Azure credentials needed)
├── inputs/                  # Drop documents here (gitignored)
├── outputs/                 # Extracted JSON files land here (gitignored)
├── notebooks/               # Jupyter exploration notebooks
├── run.py                   # CLI entry point
├── requirements.txt
└── pyproject.toml
```

---

## Getting Started

### Prerequisites
- Python 3.11+
- Azure Document Intelligence resource ([create one here](https://portal.azure.com))

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

Fill in your Azure credentials in `.env`:

```
AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT=https://<your-resource>.cognitiveservices.azure.com/
AZURE_DOCUMENT_INTELLIGENCE_KEY=<your-key>
AZURE_DI_MODEL_ID=prebuilt-layout
```

### Run locally

**API:**
```bash
uvicorn doc_intel.api.main:app --reload
# Open http://localhost:8000/docs
```

**CLI:**
```bash
python run.py inputs/your-document.pdf
python run.py inputs/invoice.pdf --model prebuilt-invoice --dry-run
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
{ "status": "ok", "version": "0.1.0" }
```

### `POST /extract`

Extract structured data from a document.

**Parameters:**
| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `file` | file | yes | — | Document to extract (PDF, PNG, JPG, TIFF) |
| `model_id` | string | no | `prebuilt-layout` | Azure DI model to use |
| `extractor` | string | no | `azure` | Extraction backend |

**Response:** `ExtractionResult` JSON containing fields, pages, tables, and confidence scores.

---

## Roadmap

- [x] Phase 1 — Core extraction pipeline + CLI
- [x] Phase 2 — FastAPI REST API + deployment
- [ ] Phase 3 — Vision model backend (GPT-4o / open source)
- [ ] Phase 4 — Side by side comparison endpoint
- [ ] Phase 5 — Frontend with comparison UI

---

## Author

**Gayashan Dewanarayana**
[GitHub](https://github.com/gayyaalpha)
