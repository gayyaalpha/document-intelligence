"""
Specialised document schemas — grow this as you add domain-specific extractors.

Each class here represents the structured output for a specific document type
(invoice, purchase order, engineering drawing title block, etc.).
These are separate from ExtractionResult: use ExtractionResult.fields to
populate these when you need strongly-typed domain objects.
"""

from pydantic import BaseModel


class InvoiceFields(BaseModel):
    """Fields typically found in an invoice (maps to prebuilt-invoice model)."""

    vendor_name: str | None = None
    vendor_address: str | None = None
    invoice_id: str | None = None
    invoice_date: str | None = None
    due_date: str | None = None
    subtotal: float | None = None
    tax: float | None = None
    total: float | None = None
    currency: str | None = None


class EngineeringDrawingTitleBlock(BaseModel):
    """
    Common title block fields on engineering/technical drawings.
    Populate from ExtractionResult.fields after extraction.
    """

    drawing_number: str | None = None
    revision: str | None = None
    title: str | None = None
    project: str | None = None
    drawn_by: str | None = None
    checked_by: str | None = None
    date: str | None = None
    scale: str | None = None
    sheet: str | None = None
