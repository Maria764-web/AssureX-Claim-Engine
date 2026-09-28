"""
AssureX Document Extraction Service
Parses raw OCR text into structured fields based on document type.
Uses deterministic regex/keyword matching only. No generative AI.
All extracted values come strictly from OCR text.
"""

import re
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path

from backend.extensions import db
from backend.models.document_extraction import (
    DocumentExtraction,
    EXTRACTION_STATUS_PENDING,
    EXTRACTION_STATUS_PROCESSING,
    EXTRACTION_STATUS_COMPLETED,
    EXTRACTION_STATUS_FAILED,
    EXTRACTION_STATUS_NOT_APPLICABLE,
    VERIFY_STATUS_UNVERIFIED,
)
from backend.models.document import (
    Document,
    DOC_TYPE_RECEIPT,
    DOC_TYPE_INVOICE,
    DOC_TYPE_WARRANTY_CARD,
    DOC_TYPE_SERIAL_PHOTO,
    DOC_TYPE_DAMAGE_PHOTO,
    DOC_TYPE_DIAGNOSTIC_REPORT,
    DOC_TYPE_OTHER,
    DOC_TYPE_VIDEO,
)
from backend.services.ocr_service import extract_text_from_document
from backend.utils.helpers import utc_now, generate_uid

logger = logging.getLogger(__name__)

# Sentinel for fields not detected by OCR
NOT_DETECTED = None

# Document types that we attempt OCR on
OCR_APPLICABLE_TYPES = {
    DOC_TYPE_RECEIPT,
    DOC_TYPE_INVOICE,
    DOC_TYPE_WARRANTY_CARD,
    DOC_TYPE_SERIAL_PHOTO,
    DOC_TYPE_DIAGNOSTIC_REPORT,
    DOC_TYPE_OTHER,
}

# Document types we skip OCR for
OCR_NOT_APPLICABLE_TYPES = {DOC_TYPE_DAMAGE_PHOTO, DOC_TYPE_VIDEO}


# ---------------------------------------------------------------------------
# Field extraction helpers (regex-based, deterministic)
# ---------------------------------------------------------------------------

def _search(pattern, text, flags=0):
    """Return first captured group from regex search, or None."""
    import re as _re
    m = _re.search(pattern, text, flags | _re.IGNORECASE)
    if m:
        try:
            val = m.group(1).strip()
        except IndexError:
            val = m.group(0).strip()
        return val if val else None
    return None


def _search_label_value(labels, text):
    """
    Search for a label then capture the value, handling both:
    - Same line:  Label: value
    - Next line:  Label\nvalue   (common in multi-line OCR)
    """
    import re as _re
    for label in labels:
        esc = _re.escape(label)
        # Same line
        m = _re.search(esc + r'[:\s\-.]+([^\n\r]{1,120})', text, _re.IGNORECASE)
        if m:
            val = m.group(1).strip()
            if val:
                return val
        # Next line
        m = _re.search(r'^[ \t]*' + esc + r'[ \t]*$\s*([^\n\r]{1,120})',
                       text, _re.IGNORECASE | _re.MULTILINE)
        if m:
            val = m.group(1).strip()
            if val:
                return val
    return None


_DATE_PATTERN = (
    r'(?:'
    r'\d{1,2}[\s/\-.]+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)'
    r'[a-z]*[\s/\-.]+\d{2,4}'
    r'|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*'
    r'\s+\d{1,2}[,\s]+\d{4}'
    r'|\d{1,2}[/\-.] \d{1,2}[/\-.] \d{2,4}'
    r'|\d{4}[/\-.] \d{1,2}[/\-.] \d{1,2}'
    r')'
)


def _extract_date(text, after_keywords):
    """Find a date after any of the given keywords (same-line and next-line)."""
    import re as _re
    dp = (
        r'(?:'
        r'\d{1,2}[\s/\-.]+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[\s/\-.]+\d{2,4}'
        r'|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2}[,\s]+\d{4}'
        r'|\d{1,2}[/\-.] \d{1,2}[/\-.] \d{2,4}'
        r'|\d{4}[/\-.] \d{1,2}[/\-.] \d{1,2}'
        r')'
    )
    for kw in after_keywords:
        esc = _re.escape(kw)
        m = _re.search(esc + r'[:\s\-.]*(' + dp + r')', text, _re.IGNORECASE)
        if m:
            return m.group(1).strip()
        m = _re.search(r'^[ \t]*' + esc + r'[ \t]*$\s*(' + dp + r')',
                       text, _re.IGNORECASE | _re.MULTILINE)
        if m:
            return m.group(1).strip()
    return None


def _extract_price(text):
    """Find best monetary value: Total Paid > Total > Amount/Price > currency symbol."""
    import re as _re
    m = _re.search(r'total\s+paid[:\s]*([\$\u20ac\u00a3Rs.]*\s*[\d,]+(?:\.\d{1,2})?)',
                   text, _re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m = _re.search(r'\btotal[:\s]*([\$\u20ac\u00a3Rs.]*\s*[\d,]+(?:\.\d{1,2})?)',
                   text, _re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m = _re.search(r'(?:amount|price|cost|paid|payment)[:\s\-]*'
                   r'([\$\u20ac\u00a3Rs.]*\s*[\d,]+(?:\.\d{1,2})?)',
                   text, _re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m = _re.search(r'([\$\u20ac\u00a3][\d,]+(?:\.\d{1,2})?)', text)
    if m:
        return m.group(1).strip()
    return None


def _extract_serial(text):
    """
    Find serial number ONLY when explicitly labelled.
    Never guesses from standalone alphanumeric tokens.
    """
    import re as _re
    m = _re.search(
        r'(?:serial\s*(?:number|no\.?|#)|s/n\b|\bsn\b)[:\s\-]*([A-Z0-9][A-Z0-9\-]{3,40})',
        text, _re.IGNORECASE
    )
    if m:
        val = m.group(1).strip()
        if len(val) >= 4:
            return val
    return None


def extract_receipt_fields(raw_text):
    """
    Extract purchase-related fields from receipt/invoice OCR text.
    Handles multi-line OCR layouts where label and value may be on separate lines.
    """
    import re as _re
    t = raw_text or ""
    fields = {
        "invoice_number": None,
        "invoice_date": None,
        "seller_name": None,
        "customer_name": None,
        "product_name": None,
        "product_model": None,
        "serial_number": None,
        "purchase_price": None,
        "warranty_reference": None,
    }

    # --- Invoice / receipt number ---
    inv_labels = [
        "invoice no.", "invoice no", "invoice number", "invoice #",
        "receipt no.", "receipt no", "receipt number",
        "order no.", "order no", "order number", "order #",
        "ref no", "reference no",
    ]
    raw_inv = _search_label_value(inv_labels, t)
    if raw_inv:
        tok = _re.split(r'\s{2,}|\t', raw_inv)[0].strip()
        if _re.match(r'^[A-Z0-9][A-Z0-9\-\/\.]{2,60}$', tok, _re.IGNORECASE):
            fields["invoice_number"] = tok

    # --- Invoice date ---
    fields["invoice_date"] = _extract_date(
        t, ["invoice date", "purchase date", "date", "receipt date",
            "order date", "sale date", "issued"]
    )

    # --- Seller / retailer name ---
    seller_labels = [
        "retailer", "sold by", "seller", "store", "shop",
        "dealer", "vendor", "merchant", "from",
    ]
    raw_seller = _search_label_value(seller_labels, t)
    if raw_seller:
        cleaned = _re.split(r'\s{3,}|\t|(?=\b(?:payment|invoice|receipt|status)\b)',
                             raw_seller, flags=_re.IGNORECASE)[0].strip()
        if _re.search(r'[A-Za-z]', cleaned):
            fields["seller_name"] = cleaned[:80]

    # --- Customer name ---
    cust_labels = [
        "customer name", "customer", "billed to", "bill to",
        "shipped to", "ship to", "buyer", "purchaser", "client",
    ]
    raw_cust = _search_label_value(cust_labels, t)
    if raw_cust:
        cleaned = raw_cust.lstrip(":").strip()
        if _re.match(r'^[A-Za-z]', cleaned):
            fields["customer_name"] = cleaned[:80]

    # --- Product name ---
    _header_words_pn = {
        'brand', 'qty', 'quantity', 'amount', 'price', 'unit', 'model',
        'no', 'number', 'date', 'total', 'subtotal', 'tax', 'fees', 'type',
    }
    prod_labels = ["description", "product", "item", "model name", "goods"]
    raw_prod = _search_label_value(prod_labels, t)
    if raw_prod and raw_prod.lower().strip() not in _header_words_pn:
        fields["product_name"] = raw_prod[:80]
    if not fields["product_name"]:
        # Fallback: find first substantive line after a product-section header
        m = _re.search(r'(?:description|item|product)[\s\n]+([^\n\r]{3,80})',
                       t, _re.IGNORECASE)
        if m:
            # Take only the first line and filter header words
            val = m.group(1).split('\n')[0].strip()
            if val.lower() not in _header_words_pn and _re.search(r'[A-Za-z]', val):
                fields["product_name"] = val[:80]

    # --- Product model ---
    # Use specific model-number labels only (NOT bare 'model' which matches table headers)
    model_labels = [
        "model no.", "model no", "model number", "model #",
        "part no.", "part no", "part number",
    ]
    # Words that are table column headers, not actual model values
    _table_header_words = {
        'qty', 'quantity', 'amount', 'price', 'unit', 'brand', 'item',
        'description', 'product', 'total', 'subtotal', 'tax', 'fees',
        'model', 'no', 'number', 'date', 'invoice',
    }
    raw_model = _search_label_value(model_labels, t)
    if raw_model:
        tok = _re.split(r'\s{2,}|\t', raw_model)[0].strip()
        if (tok.lower() not in _table_header_words and
                _re.match(r'^[A-Z0-9][A-Z0-9\-.]{1,20}$', tok, _re.IGNORECASE)):
            fields["product_model"] = tok
    if not fields["product_model"]:
        # Compact model code: short alphanumeric ID (e.g. A3090, SM-G990)
        # Must be short enough to be a model code (not an invoice ID like APL-2026-0715-001)
        # Also must not match the invoice number already captured
        inv_num = fields.get("invoice_number") or ""
        for m in _re.finditer(r'\b([A-Z]{1,4}-?[0-9]{3,6})\b', t, _re.IGNORECASE):
            candidate = m.group(1).strip()
            if (candidate.lower() not in _table_header_words
                    and candidate not in inv_num
                    and len(candidate) <= 12):
                fields["product_model"] = candidate
                break

    # --- Serial number (explicit label only, never invented) ---
    fields["serial_number"] = _extract_serial(t)

    # --- Purchase price ---
    fields["purchase_price"] = _extract_price(t)

    # --- Warranty reference (actual ID only, not a duration string) ---
    fields["warranty_reference"] = _search(
        r'warranty\s*(?:ref(?:erence)?|id|no\.?|number|#)[:\s\-]*([A-Z0-9][A-Z0-9\-\/\.]{2,40})',
        t
    )

    # Normalize: convert empty strings to None
    return {k: (v.strip() if isinstance(v, str) and v.strip() else None)
            for k, v in fields.items()}


def extract_warranty_fields(raw_text: str) -> Dict[str, Any]:
    """Extract warranty-related fields from warranty card OCR text."""
    t = raw_text or ""
    fields = {
        "customer_name": None,
        "product_name": None,
        "product_model": None,
        "serial_number": None,
        "warranty_start_date": None,
        "warranty_end_date": None,
        "warranty_duration": None,
        "warranty_reference": None,
        "manufacturer": None,
    }

    fields["customer_name"] = _search(
        r'(?:customer|purchaser|owner|name)[:\s\-]+([A-Za-z][A-Za-z\s\.\-]{1,50})',
        t
    )

    fields["product_name"] = _search(
        r'(?:product|device|appliance|item)[:\s\-]+([A-Za-z0-9][A-Za-z0-9\s\-\_]{2,60})',
        t
    )

    fields["product_model"] = _search(
        r'(?:model\s*(?:no|number|#)?)[:\s\-]+([A-Za-z0-9\-\_]{2,30})',
        t
    )

    fields["serial_number"] = _extract_serial(t)

    fields["warranty_start_date"] = _extract_date(t, ["start date", "purchase date", "date of purchase", "from", "valid from", "activation date"])
    fields["warranty_end_date"] = _extract_date(t, ["end date", "expiry date", "expiration date", "expires", "valid until", "valid to", "to"])
    fields["warranty_duration"] = _search(
        r'(?:warranty\s*(?:period|duration|term|coverage))[:\s\-]+([0-9]{1,2}\s*(?:year|month|yr|mo)[s]?)',
        t
    )

    fields["warranty_reference"] = _search(
        r'(?:warranty\s*(?:no|number|ref|#|card\s*(?:no|number|#)?)?)[:\s\-]+([A-Z0-9\-\/]{3,30})',
        t
    )

    fields["manufacturer"] = _search(
        r'(?:manufacturer|brand|make|mfr)[:\s\-]+([A-Za-z0-9\s\.\-]{2,40})',
        t
    )

    return {k: (v.strip() if isinstance(v, str) and v.strip() else None) for k, v in fields.items()}


def extract_serial_fields(raw_text: str) -> Dict[str, Any]:
    """Extract serial number from serial label photo OCR text."""
    t = raw_text or ""
    fields = {"serial_number": None, "product_model": None}
    fields["serial_number"] = _extract_serial(t)
    fields["product_model"] = _search(
        r'(?:model|mdl)[:\s\-]+([A-Za-z0-9\-\_]{2,30})',
        t
    )
    return {k: (v.strip() if isinstance(v, str) and v.strip() else None) for k, v in fields.items()}


def extract_diagnostic_fields(raw_text: str) -> Dict[str, Any]:
    """Extract key fields from diagnostic/technical report."""
    t = raw_text or ""
    fields = {
        "report_date": None,
        "technician": None,
        "fault_description": None,
    }
    fields["report_date"] = _extract_date(t, ["date", "report date", "tested on", "inspection date"])
    fields["technician"] = _search(
        r'(?:technician|engineer|inspector|tested\s*by|prepared\s*by|signed\s*by)[:\s\-]+([A-Za-z][A-Za-z\s\.]{1,50})',
        t
    )
    # grab first 300 chars as fault description excerpt
    if t.strip():
        fields["fault_description"] = t.strip()[:300]
    return {k: (v.strip() if isinstance(v, str) and v.strip() else None) for k, v in fields.items()}


def _dispatch_extractor(document_type: str, raw_text: str) -> Dict[str, Any]:
    """Route raw text to the appropriate field extractor based on document type."""
    if document_type in (DOC_TYPE_RECEIPT, DOC_TYPE_INVOICE):
        return extract_receipt_fields(raw_text)
    elif document_type == DOC_TYPE_WARRANTY_CARD:
        return extract_warranty_fields(raw_text)
    elif document_type == DOC_TYPE_SERIAL_PHOTO:
        return extract_serial_fields(raw_text)
    elif document_type == DOC_TYPE_DIAGNOSTIC_REPORT:
        return extract_diagnostic_fields(raw_text)
    else:
        # Other/Evidence: return raw text excerpt only
        excerpt = (raw_text or "").strip()[:500] if raw_text else None
        return {"text_excerpt": excerpt}


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def get_or_create_extraction(document: Document) -> DocumentExtraction:
    """Get existing extraction record or create a new Pending one."""
    extraction = DocumentExtraction.query.filter_by(document_id=document.id).first()
    if not extraction:
        extraction = DocumentExtraction(
            document_id=document.id,
            claim_id=document.claim_id,
            extraction_status=EXTRACTION_STATUS_PENDING,
            verification_status=VERIFY_STATUS_UNVERIFIED,
        )
        db.session.add(extraction)
        db.session.flush()
    return extraction


def process_document_ocr(document: Document, upload_root: str) -> DocumentExtraction:
    """
    Full OCR pipeline for a document:
    1. Check if OCR is applicable.
    2. Run OCR extraction.
    3. Parse structured fields.
    4. Persist results.
    5. Update document.ocr_status.
    Returns the DocumentExtraction record.
    """
    extraction = get_or_create_extraction(document)

    # Skip non-OCR document types
    if document.document_type in OCR_NOT_APPLICABLE_TYPES:
        extraction.extraction_status = EXTRACTION_STATUS_NOT_APPLICABLE
        extraction.ocr_engine_used = None
        document.ocr_status = "Not Applicable"
        db.session.commit()
        return extraction

    # Mark as processing
    extraction.extraction_status = EXTRACTION_STATUS_PROCESSING
    document.ocr_status = "Processing"
    db.session.commit()

    # Build absolute file path
    file_path = str(Path(upload_root) / document.stored_path)

    # Run OCR
    ocr_result = extract_text_from_document(file_path, document.file_extension)

    extraction.processing_timestamp = utc_now()
    extraction.ocr_engine_used = ocr_result.get("engine")

    if not ocr_result.get("success"):
        extraction.extraction_status = EXTRACTION_STATUS_FAILED
        extraction.error_message = ocr_result.get("error", "OCR processing failed.")
        document.ocr_status = "Failed"
        db.session.commit()
        return extraction

    raw_text = ocr_result.get("raw_text") or ""
    extraction.raw_text = raw_text

    # Extract structured fields
    try:
        structured = _dispatch_extractor(document.document_type, raw_text)
        extraction.extracted_fields = structured
    except Exception as e:
        logger.exception("Field extraction failed for doc %s", document.document_uid)
        extraction.extracted_fields = {}
        extraction.error_message = f"Field extraction error: {e}"

    extraction.extraction_status = EXTRACTION_STATUS_COMPLETED
    document.ocr_status = "Completed"
    db.session.commit()
    return extraction


def save_verified_fields(extraction: DocumentExtraction, verified_data: Dict[str, Any], verifying_user_id: int) -> None:
    """Persist customer-verified/corrected field values."""
    from backend.models.document_extraction import VERIFY_STATUS_VERIFIED
    extraction.verified_fields = verified_data
    extraction.verification_status = VERIFY_STATUS_VERIFIED
    extraction.verified_at = utc_now()
    extraction.verified_by_user_id = verifying_user_id
    db.session.commit()
