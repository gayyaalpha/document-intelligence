"""Claude Vision extraction backend using Anthropic's API."""

import base64
import json
import re
from pathlib import Path
from typing import Any

import anthropic
import pymupdf

from doc_intel.config import settings
from doc_intel.extractors.base import BaseExtractor
from doc_intel.models.extraction_result import (
    DocumentField,
    ExtractionResult,
    PageInfo,
)

EXTRACTION_PROMPT = """You are a document extraction assistant. Your task has two steps:

1. Identify the document type.
2. Extract structured data into a consistent JSON schema that mirrors the structure used by Azure Document Intelligence (fields, tables, page summaries).

---

## Multi-page documents

The user message may contain ONE OR MORE page images, provided in order. Treat them as a SINGLE DOCUMENT and produce ONE unified extraction:

- Make a single document type classification for the whole document.
- Produce ONE merged list of fields. If the same field appears on multiple pages, include it ONLY ONCE — pick the value with the highest confidence and the clearest text.
- Produce ONE merged list of tables, in the order they appear across pages.
- Return per-page summaries in `page_summaries` array, one entry per image in input order.

---

## Step 1 — Document type

Classify the document into exactly ONE of these categories (use the string value as-is):

- `invoice`            — vendor invoices, bills for goods/services rendered
- `receipt`            — retail receipts, point-of-sale transactions
- `utility_bill`       — electricity, gas, water, phone, internet, broadband bills
- `payslip`            — payroll statements, salary slips, pay advice
- `tax_document`       — tax forms, tax summaries (W-2, 1099, PAYG, etc.)
- `bank_statement`     — bank account statements, transaction history
- `purchase_order`     — purchase orders issued by a buyer to a vendor
- `technical_drawing`  — engineering drawings, CAD drawings, schematics, technical datasheets, product specification pages with dimensional tables
- `other`              — anything that does not clearly fit the above

---

## Step 2 — Output format

Return a JSON object with this EXACT top-level structure:

{
  "document_type": "<one of the categories above>",
  "document_type_confidence": <float 0.0-1.0>,
  "fields": [
    {"name": "<snake_case_name>", "value": "<string value>", "confidence": <float 0.0-1.0>}
  ],
  "tables": [
    {
      "title": "<short description of the table — e.g. 'line_items', 'revision_history', 'bill_of_materials'>",
      "headers": ["<col1>", "<col2>", ...],
      "rows": [
        ["<cell>", "<cell>", ...],
        ["<cell>", "<cell>", ...]
      ]
    }
  ],
  "page_summaries": [
    {"page_number": 1, "summary": "<one-sentence description of page 1>"},
    {"page_number": 2, "summary": "<one-sentence description of page 2>"}
  ]
}

---

## Canonical field names per document type

When the corresponding data is present in the document, use these exact snake_case field names. If a field is not present, OMIT it (do NOT include it with a null or empty value). You may also add additional document-specific fields beyond these — use descriptive snake_case names for those.

### invoice
invoice_number, invoice_date, due_date,
vendor_name, vendor_address, vendor_abn, vendor_email, vendor_phone, vendor_website,
customer_name, customer_address, customer_id,
subtotal, tax_amount, total_amount, amount_due, amount_paid,
currency, payment_terms, payment_reference

### receipt
merchant_name, merchant_address, merchant_abn, merchant_phone,
transaction_date, transaction_time, receipt_number,
subtotal, tax_amount, total_amount, tip_amount,
payment_method, card_last_four, currency

### utility_bill
provider_name, provider_abn, account_number,
customer_name, service_address, billing_address,
bill_date, billing_period_start, billing_period_end, due_date,
previous_balance, current_charges, total_amount, amount_due,
usage_amount, usage_unit, tariff_rate,
payment_reference, biller_code, bpay_reference

### payslip
employer_name, employer_abn, employee_name, employee_id,
pay_period_start, pay_period_end, pay_date,
gross_pay, net_pay, tax_withheld, superannuation, hours_worked, hourly_rate,
year_to_date_gross, year_to_date_tax, year_to_date_super

### tax_document
tax_year, taxpayer_name, taxpayer_id,
employer_name, employer_id,
gross_income, federal_tax, state_tax, total_tax, refund_amount

### bank_statement
bank_name, account_holder, account_number, bsb,
statement_period_start, statement_period_end,
opening_balance, closing_balance, total_credits, total_debits

### purchase_order
po_number, po_date, required_delivery_date,
buyer_name, buyer_address, vendor_name, vendor_address,
subtotal, tax_amount, total_amount, currency, payment_terms

### technical_drawing
drawing_number, part_number, part_name, part_description,
revision, sheet_number, total_sheets, scale, units,
drawn_by, checked_by, approved_by, date_drawn, date_approved,
material, finish, tolerance_standard, projection,
title, project_name, company_name, standard_referenced

### other
Use descriptive snake_case field names based on the document content. Pick names that would be stable across similar documents.

---

## Table extraction guidance

- Extract structured tabular data as objects under `tables` — NOT as individual fields.
- Use descriptive `title` values so downstream code can identify tables by purpose:
  - Invoices → `line_items`
  - Technical drawings → `bill_of_materials`, `revision_history`, `dimensions_table`, `specifications`
  - Payslips → `earnings`, `deductions`, `leave_balances`
  - Bank statements → `transactions`
- Always include `headers`. If the table has no visible header row, infer reasonable column names and set `headers` accordingly.
- Preserve cell values exactly as they appear (including currency symbols, units, tolerances, dashes for empty cells).

---

## Rules

- Return ONLY the JSON object. No markdown code blocks. No commentary. No explanatory text.
- All field names MUST be snake_case.
- All field and cell values MUST be strings (preserve original formatting like "$1,234.56", "M 6", "-0.012/-0.02").
- Do NOT include fields that are not present in the document.
- NEVER include placeholder values like "Not explicitly stated", "Not visible", "N/A", "Unknown", "Missing", "Not provided", "None", or any similar stand-in. If a field is not clearly visible and readable in the document, OMIT the entire field entry from the output. Do not fabricate, infer, or guess values that are not directly visible on the page.
- For multi-page documents: NEVER produce duplicate field entries with the same `name`. If the same field appears on multiple pages, output it ONCE with the highest-confidence value.
- `confidence` reflects your certainty from 0.0 to 1.0: 1.0 for clearly printed unambiguous text, lower for handwriting, partial occlusion, or ambiguous values.
- If the image contains a diagram with labels (e.g. an engineering drawing with labelled features), extract the labels as fields with names like `diagram_label_b`, `diagram_label_k` and values describing what they point to — but only if you can determine what each label references from visible context.
- If you cannot identify the document type at all, use "other" and do your best with generic field names.
"""


def _pdf_to_page_images(pdf_path: Path) -> list[str]:
    """Convert every page of a PDF to a base64-encoded PNG. Opens the PDF once."""
    doc = pymupdf.open(str(pdf_path))
    mat = pymupdf.Matrix(2, 2)  # 2x zoom for better quality
    pages_b64: list[str] = []
    try:
        for page in doc:
            pix = page.get_pixmap(matrix=mat)
            img_bytes = pix.tobytes("png")
            pages_b64.append(base64.standard_b64encode(img_bytes).decode("utf-8"))
    finally:
        doc.close()
    return pages_b64


def _image_to_base64(image_path: Path) -> str:
    """Convert an image file to base64."""
    with open(image_path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


def _get_media_type(file_path: Path) -> str:
    """Return the correct media type for the file."""
    suffix = file_path.suffix.lower()
    media_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".tiff": "image/tiff",
        ".tif": "image/tiff",
        ".bmp": "image/bmp",
    }
    return media_types.get(suffix, "image/png")


class ClaudeVisionExtractor(BaseExtractor):
    """
    Extraction backend using Claude's vision capabilities via Anthropic API.

    Multi-page documents are sent to Claude in a SINGLE API call with all page
    images attached, so Claude can produce a unified extraction with no
    cross-page duplication or naming inconsistency.

    Supports: PDF, PNG, JPG, JPEG, TIFF, BMP
    """

    def __init__(self, model: str | None = None) -> None:
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._model = model or settings.anthropic_model

    def supports(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS

    def extract(self, file_path: Path) -> ExtractionResult:
        if not file_path.exists():
            raise FileNotFoundError(f"Document not found: {file_path}")
        if not self.supports(file_path):
            raise ValueError(
                f"Unsupported file type '{file_path.suffix}'. "
                f"Supported: {sorted(self.SUPPORTED_EXTENSIONS)}"
            )

        suffix = file_path.suffix.lower()

        if suffix == ".pdf":
            return self._extract_pdf(file_path)
        else:
            return self._extract_image(file_path)

    def _extract_pdf(self, file_path: Path) -> ExtractionResult:
        """Extract from a multi-page PDF in a single Claude call with all pages attached."""
        page_images = _pdf_to_page_images(file_path)
        page_count = len(page_images)
        print(
            f"[claude-vision] Sending {page_count} page(s) to Claude in one call "
            f"(model={self._model})..."
        )

        images = [(b64, "image/png") for b64 in page_images]
        parsed = self._call_claude(images)

        pages = self._build_pages(parsed["page_summaries"], page_count)
        return self._build_result(
            file_path,
            parsed["fields"],
            parsed["tables"],
            pages,
            document_type=parsed["document_type"],
            document_type_confidence=parsed["document_type_confidence"],
        )

    def _extract_image(self, file_path: Path) -> ExtractionResult:
        """Extract from a single image file."""
        media_type = _get_media_type(file_path)
        image_b64 = _image_to_base64(file_path)
        parsed = self._call_claude([(image_b64, media_type)])

        pages = self._build_pages(parsed["page_summaries"], 1)
        return self._build_result(
            file_path,
            parsed["fields"],
            parsed["tables"],
            pages,
            document_type=parsed["document_type"],
            document_type_confidence=parsed["document_type_confidence"],
        )

    def _call_claude(self, images: list[tuple[str, str]]) -> dict[str, Any]:
        """
        Send one or more images to Claude in a single API call.

        Args:
            images: List of (base64_data, media_type) tuples, in page order.
        """
        content: list[dict[str, Any]] = []
        for b64, media_type in images:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": b64,
                },
            })
        content.append({"type": "text", "text": EXTRACTION_PROMPT})

        response = self._client.messages.create(
            model=self._model,
            max_tokens=8192,
            messages=[{"role": "user", "content": content}],
        )

        raw_text = response.content[0].text
        return self._parse_response(raw_text)

    def _parse_response(self, raw_text: str) -> dict[str, Any]:
        """Parse Claude's JSON response into the intermediate dict shape."""
        # Strip markdown code blocks if Claude wrapped the JSON despite instructions
        cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", raw_text).strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            # Claude returned something unexpected — return empty structure with raw text as summary
            return {
                "document_type": "other",
                "document_type_confidence": 0.0,
                "fields": [],
                "tables": [],
                "page_summaries": [{"page_number": 1, "summary": raw_text}],
            }

        # Fields
        fields: list[DocumentField] = []
        for item in data.get("fields", []):
            fields.append(
                DocumentField(
                    name=item.get("name", "unknown"),
                    value=item.get("value"),
                    raw_value=str(item.get("value", "")),
                    confidence=item.get("confidence"),
                )
            )

        # Tables — convert Claude's {headers, rows} shape to Azure's list[list[list[str]]]
        tables: list[list[list[str]]] = []
        for table in data.get("tables", []):
            headers = [str(h) for h in table.get("headers", [])]
            rows = [[str(cell) for cell in row] for row in table.get("rows", [])]
            azure_shape = ([headers] if headers else []) + rows
            if azure_shape:
                tables.append(azure_shape)

        # Page summaries — accept either the new `page_summaries` array or
        # the legacy single `page_summary` string for backward compatibility
        page_summaries = data.get("page_summaries")
        if not page_summaries:
            legacy = data.get("page_summary", "")
            page_summaries = [{"page_number": 1, "summary": legacy}] if legacy else []

        return {
            "document_type": data.get("document_type", "other"),
            "document_type_confidence": float(data.get("document_type_confidence", 0.0) or 0.0),
            "fields": fields,
            "tables": tables,
            "page_summaries": page_summaries,
        }

    def _build_pages(
        self, page_summaries: list[dict[str, Any]], expected_count: int
    ) -> list[PageInfo]:
        """Build PageInfo entries from Claude's page summaries, defending against gaps."""
        # Index summaries by page_number for fast lookup
        by_number: dict[int, str] = {}
        for entry in page_summaries:
            try:
                pn = int(entry.get("page_number", 0))
            except (TypeError, ValueError):
                continue
            by_number[pn] = str(entry.get("summary", ""))

        pages: list[PageInfo] = []
        for i in range(1, expected_count + 1):
            pages.append(PageInfo(
                page_number=i,
                content=by_number.get(i, ""),
            ))
        return pages

    def _build_result(
        self,
        source_file: Path,
        fields: list[DocumentField],
        tables: list[list[list[str]]],
        pages: list[PageInfo],
        *,
        document_type: str,
        document_type_confidence: float,
    ) -> ExtractionResult:
        confidences = [f.confidence for f in fields if f.confidence is not None]
        avg_confidence = sum(confidences) / len(confidences) if confidences else None

        return ExtractionResult(
            source_file=source_file,
            extractor="claude-vision",
            model_id=self._model,
            fields=fields,
            pages=pages,
            tables=tables,
            confidence=avg_confidence,
            metadata={
                "backend": "anthropic",
                "model": self._model,
                "document_type": document_type,
                "document_type_confidence": document_type_confidence,
            },
        )
