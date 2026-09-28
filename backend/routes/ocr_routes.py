"""
AssureX OCR Routes Blueprint
Provides secure authenticated API endpoints for:
- Triggering OCR processing on a document
- Retrieving OCR extraction results
- Customer verification / correction of extracted data
All endpoints enforce existing RBAC and IDOR protections.
"""

from datetime import datetime
from pathlib import Path

from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required, current_user

from backend.extensions import db
from backend.models.document import Document
from backend.models.document_extraction import (
    DocumentExtraction,
    EXTRACTION_STATUS_COMPLETED,
    EXTRACTION_STATUS_FAILED,
    EXTRACTION_STATUS_NOT_APPLICABLE,
    EXTRACTION_STATUS_PENDING,
    VERIFY_STATUS_NEEDS_CORRECTION,
    VERIFY_STATUS_VERIFIED,
    VERIFY_STATUS_UNVERIFIED,
)
from backend.services.document_extraction_service import (
    get_or_create_extraction,
    process_document_ocr,
    save_verified_fields,
)
from backend.utils.helpers import utc_now
from backend.utils.security import check_resource_ownership, ROLE_CUSTOMER

ocr_bp = Blueprint("ocr", __name__, url_prefix="/api/documents")


def _get_document_owner_id(doc: Document) -> int:
    """Resolve the effective owner user ID for a document."""
    if doc.user_id:
        return doc.user_id
    if doc.claim:
        return doc.claim.user_id
    if doc.product:
        return doc.product.user_id
    return None


def _check_doc_access(document_id: int):
    """
    Load document and check IDOR ownership.
    Returns (doc, error_response_tuple_or_None).
    """
    doc = db.session.get(Document, document_id)
    if not doc:
        return None, (jsonify({"success": False, "message": "Document not found."}), 404)

    owner_id = _get_document_owner_id(doc)
    if owner_id and not check_resource_ownership(owner_id):
        return None, (jsonify({
            "success": False,
            "error": "Forbidden",
            "message": "Access forbidden: You do not have permission to access this document."
        }), 403)

    return doc, None


# ---------------------------------------------------------------------------
# POST /api/documents/<id>/ocr
# Trigger or re-trigger OCR processing for a document
# ---------------------------------------------------------------------------
@ocr_bp.route("/<int:document_id>/ocr", methods=["POST"])
@login_required
def process_ocr(document_id: int):
    """Trigger OCR processing for a document. Customer, Service Center, Admin."""
    doc, err = _check_doc_access(document_id)
    if err:
        return err

    extraction = DocumentExtraction.query.filter_by(document_id=doc.id).first()

    # Allow retry only if previously failed or pending; block re-run of completed unless force
    force = request.json.get("force", False) if request.is_json else False

    if extraction and extraction.extraction_status == EXTRACTION_STATUS_COMPLETED and not force:
        return jsonify({
            "success": True,
            "message": "OCR already completed. Use force=true to reprocess.",
            "extraction": extraction.to_dict()
        }), 200

    if extraction and extraction.extraction_status == EXTRACTION_STATUS_NOT_APPLICABLE:
        return jsonify({
            "success": True,
            "message": "OCR is not applicable for this document type.",
            "extraction": extraction.to_dict()
        }), 200

    upload_root = current_app.config.get("UPLOAD_FOLDER", "uploads")

    try:
        extraction = process_document_ocr(doc, upload_root)
        return jsonify({
            "success": True,
            "message": "OCR processing completed." if extraction.extraction_status == EXTRACTION_STATUS_COMPLETED else "OCR processing failed.",
            "extraction": extraction.to_dict()
        }), 200
    except Exception as e:
        return jsonify({"success": False, "message": f"OCR processing error: {e}"}), 500


# ---------------------------------------------------------------------------
# GET /api/documents/<id>/ocr
# Retrieve OCR extraction result
# ---------------------------------------------------------------------------
@ocr_bp.route("/<int:document_id>/ocr", methods=["GET"])
@login_required
def get_ocr_result(document_id: int):
    """Get OCR extraction result for a document."""
    doc, err = _check_doc_access(document_id)
    if err:
        return err

    extraction = DocumentExtraction.query.filter_by(document_id=doc.id).first()
    if not extraction:
        return jsonify({
            "success": False,
            "message": "No OCR result found for this document.",
            "ocr_status": doc.ocr_status
        }), 404

    return jsonify({
        "success": True,
        "document": doc.to_dict(),
        "extraction": extraction.to_dict()
    }), 200


# ---------------------------------------------------------------------------
# POST /api/documents/<id>/ocr/verify
# Save customer-verified / corrected extracted field values
# ---------------------------------------------------------------------------
@ocr_bp.route("/<int:document_id>/ocr/verify", methods=["POST"])
@login_required
def verify_ocr_fields(document_id: int):
    """
    Save customer-verified/corrected OCR extracted values.
    Validates field types where possible. Preserves raw OCR text.
    """
    doc, err = _check_doc_access(document_id)
    if err:
        return err

    extraction = DocumentExtraction.query.filter_by(document_id=doc.id).first()
    if not extraction:
        return jsonify({
            "success": False,
            "message": "No OCR extraction record found. Please trigger OCR first."
        }), 404

    if extraction.extraction_status in (EXTRACTION_STATUS_PENDING, EXTRACTION_STATUS_NOT_APPLICABLE):
        return jsonify({
            "success": False,
            "message": "OCR has not been processed yet for this document."
        }), 400

    if not request.is_json:
        return jsonify({"success": False, "message": "JSON request body required."}), 400

    data = request.get_json() or {}
    verified_fields = data.get("verified_fields", {})
    mark_needs_correction = data.get("needs_correction", False)

    if not isinstance(verified_fields, dict):
        return jsonify({"success": False, "message": "verified_fields must be a JSON object."}), 400

    # Normalize date fields to ISO 8601 (YYYY-MM-DD) before validation.
    # This allows '15 July 2026', '15 Jul 2026', 'July 15, 2026', '15/07/2026'
    # to all pass validation and be stored in a canonical form.
    _date_fields = {"invoice_date", "warranty_start_date", "warranty_end_date", "report_date"}
    for df in _date_fields:
        if df in verified_fields and verified_fields[df] and isinstance(verified_fields[df], str):
            verified_fields[df] = _normalize_date_to_iso(verified_fields[df])

    # Auto-clear purchase_price if OCR misread a non-numeric value (e.g. "bank transfer")
    price_raw = verified_fields.get("purchase_price")
    if price_raw and isinstance(price_raw, str):
        price_cleaned = price_raw.replace(",", "").replace("$", "").replace("£", "").replace("€", "").replace("Rs", "").replace("PKR", "").replace("/-", "").strip()
        try:
            float(price_cleaned)
        except ValueError:
            verified_fields["purchase_price"] = ""

    # Validate fields
    validation_errors = _validate_verification_fields(verified_fields)
    if validation_errors:
        return jsonify({
            "success": False,
            "message": "Validation failed.",
            "errors": validation_errors
        }), 400

    # Sanitize values
    sanitized = {}
    for k, v in verified_fields.items():
        if isinstance(v, str):
            sanitized[k] = v.strip()[:500]  # safe length cap
        elif v is None or isinstance(v, (int, float)):
            sanitized[k] = v
        else:
            sanitized[k] = str(v).strip()[:500]

    if mark_needs_correction:
        extraction.verification_status = VERIFY_STATUS_NEEDS_CORRECTION
        extraction.verified_fields = sanitized
        extraction.verified_at = utc_now()
        extraction.verified_by_user_id = current_user.id
        db.session.commit()
        return jsonify({
            "success": True,
            "message": "Extraction marked as needing correction.",
            "extraction": extraction.to_dict()
        }), 200

    # Save as verified
    save_verified_fields(extraction, sanitized, current_user.id)
    return jsonify({
        "success": True,
        "message": "Extracted information verified and saved successfully.",
        "extraction": extraction.to_dict()
    }), 200


def _validate_verification_fields(fields: dict) -> list:
    """
    Validate verification field values.
    Returns list of error messages, empty if valid.
    """
    errors = []

    # Date fields
    date_fields = ["invoice_date", "warranty_start_date", "warranty_end_date", "report_date"]
    for f in date_fields:
        val = fields.get(f)
        if val and isinstance(val, str) and val.strip():
            if not _is_valid_date_string(val.strip()):
                errors.append(f"'{f}' must be a valid date.")

    # Warranty dates: end must not precede start
    start = fields.get("warranty_start_date")
    end = fields.get("warranty_end_date")
    if start and end and isinstance(start, str) and isinstance(end, str):
        parsed_start = _parse_date_flexible(start)
        parsed_end = _parse_date_flexible(end)
        if parsed_start and parsed_end and parsed_end < parsed_start:
            errors.append("Warranty end date must not precede warranty start date.")

    # Serial number length
    sn = fields.get("serial_number")
    if sn and isinstance(sn, str) and len(sn.strip()) > 100:
        errors.append("Serial number must not exceed 100 characters.")

    # Invoice number - if provided, must not be empty
    inv = fields.get("invoice_number")
    if inv is not None and isinstance(inv, str) and not inv.strip():
        errors.append("Invoice number cannot be empty if provided.")

    # purchase_price is pre-sanitized in the route before validation reaches here

    # Name fields reasonable length
    for fname in ["customer_name", "seller_name", "manufacturer", "technician"]:
        val = fields.get(fname)
        if val and isinstance(val, str) and len(val.strip()) > 200:
            errors.append(f"'{fname}' exceeds maximum length of 200 characters.")

    return errors


def _is_valid_date_string(s: str) -> bool:
    """Try parsing common date formats, including word-month variants."""
    for fmt in (
        "%Y-%m-%d",
        "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d",
        "%d-%m-%Y", "%d.%m.%Y",
        # Word-month formats
        "%d %B %Y",  # 15 July 2026
        "%d %b %Y",  # 15 Jul 2026
        "%B %d, %Y", # July 15, 2026
        "%b %d, %Y", # Jul 15, 2026
        "%B %d %Y",  # July 15 2026
        "%b %d %Y",  # Jul 15 2026
    ):
        try:
            datetime.strptime(s.strip(), fmt)
            return True
        except ValueError:
            continue
    return False


def _parse_date_flexible(s: str):
    """Return datetime object or None. Supports word-month formats."""
    for fmt in (
        "%Y-%m-%d",
        "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d",
        "%d-%m-%Y", "%d.%m.%Y",
        "%d %B %Y",
        "%d %b %Y",
        "%B %d, %Y",
        "%b %d, %Y",
        "%B %d %Y",
        "%b %d %Y",
    ):
        try:
            return datetime.strptime(s.strip(), fmt)
        except ValueError:
            continue
    return None


def _normalize_date_to_iso(s: str) -> str:
    """
    Convert any supported date format to ISO 8601 (YYYY-MM-DD).
    Returns the original string unchanged if it cannot be parsed.
    This ensures the validator always sees a canonical form.
    """
    if not s or not isinstance(s, str) or not s.strip():
        return s
    dt = _parse_date_flexible(s.strip())
    if dt:
        return dt.strftime("%Y-%m-%d")
    return s  # return as-is; the validator will reject it

