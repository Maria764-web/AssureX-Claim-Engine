"""
AssureX Pre-Submission Check Service
Runs lightweight validation checks on a claim BEFORE the customer submits it.
Returns user-friendly warnings so the customer can fix issues early,
instead of finding out after the rule engine hard-rejects the claim.

Severity levels:
  - "error"   : Will almost certainly cause rejection — user should fix this.
  - "warning" : May cause issues — user should review.
  - "info"    : Helpful tip — not blocking.
"""

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Severity constants ────────────────────────────────────────────────────────
SEV_ERROR   = "error"
SEV_WARNING = "warning"
SEV_INFO    = "info"


def _w(severity: str, code: str, message: str, suggestion: str = "") -> Dict[str, str]:
    """Build a single warning dict."""
    return {
        "severity":   severity,
        "code":       code,
        "message":    message,
        "suggestion": suggestion,
    }


# ── Individual checks ─────────────────────────────────────────────────────────

def _check_warranty_status(claim) -> List[Dict]:
    """Warn if warranty is expired or not found."""
    warnings = []
    warranty = getattr(claim, "warranty", None)
    fault_date = getattr(claim, "fault_date", None)

    if not warranty:
        warnings.append(_w(
            SEV_ERROR, "NO_WARRANTY",
            "No warranty record is linked to this product.",
            "Make sure the product was registered with a valid warranty."
        ))
        return warnings

    check_date = fault_date if isinstance(fault_date, date) else date.today()
    status = warranty.calculate_status(check_date)

    if status == "Expired":
        warnings.append(_w(
            SEV_ERROR, "WARRANTY_EXPIRED",
            f"Warranty expired on {warranty.expiry_date}. Claims on expired warranties are rejected.",
            "If you believe this is incorrect, contact support before submitting."
        ))
    elif status == "Nearing Expiry":
        days_left = (warranty.expiry_date - check_date).days if warranty.expiry_date else 0
        warnings.append(_w(
            SEV_WARNING, "WARRANTY_NEARING_EXPIRY",
            f"Warranty expires in {days_left} day(s). Submit as soon as possible.",
            "Claims submitted after expiry cannot be processed."
        ))

    return warnings


def _check_fault_date(claim) -> List[Dict]:
    """Warn if fault date is in the future, or before product purchase date."""
    warnings = []
    fault_date = getattr(claim, "fault_date", None)
    if not fault_date:
        warnings.append(_w(
            SEV_ERROR, "FAULT_DATE_MISSING",
            "Fault date is required.",
            "Please enter the date when the fault first occurred."
        ))
        return warnings

    today = date.today()
    if fault_date > today:
        warnings.append(_w(
            SEV_ERROR, "FAULT_DATE_FUTURE",
            f"Fault date ({fault_date}) is in the future.",
            "Fault date must be today or a past date."
        ))

    product = getattr(claim, "product", None)
    if product:
        purchase_date = getattr(product, "purchase_date", None)
        if purchase_date and fault_date < purchase_date:
            warnings.append(_w(
                SEV_ERROR, "FAULT_DATE_BEFORE_PURCHASE",
                f"Fault date ({fault_date}) is before product purchase date ({purchase_date}).",
                "A fault cannot occur before the product was purchased."
            ))

    return warnings


def _check_required_documents(claim) -> List[Dict]:
    """Warn if receipt or damage photo is missing."""
    warnings = []
    documents = getattr(claim, "documents", []) or []
    doc_types = [(getattr(d, "document_type", "") or "").lower() for d in documents]

    has_receipt = any("receipt" in dt or "invoice" in dt for dt in doc_types)
    has_photo   = any("photo" in dt or "damage" in dt or "diagnostic" in dt for dt in doc_types)

    if not has_receipt:
        warnings.append(_w(
            SEV_ERROR, "MISSING_RECEIPT",
            "Purchase receipt or invoice is missing.",
            "Upload your purchase receipt. Claims without proof of purchase are rejected."
        ))
    if not has_photo:
        warnings.append(_w(
            SEV_ERROR, "MISSING_DAMAGE_PHOTO",
            "Damage photo or diagnostic report is missing.",
            "Upload a clear photo of the damage or a technician's diagnostic report."
        ))
    if not documents:
        warnings.append(_w(
            SEV_INFO, "NO_DOCUMENTS",
            "No documents uploaded yet.",
            "At least a receipt and a damage photo are required before submitting."
        ))

    return warnings


def _check_fault_description(claim) -> List[Dict]:
    """Warn if fault description is too short or missing."""
    warnings = []
    description = (getattr(claim, "fault_description", "") or "").strip()

    if not description:
        warnings.append(_w(
            SEV_ERROR, "FAULT_DESCRIPTION_MISSING",
            "Fault description is required.",
            "Describe what went wrong with the product in detail."
        ))
    elif len(description) < 20:
        warnings.append(_w(
            SEV_WARNING, "FAULT_DESCRIPTION_SHORT",
            f"Fault description is very short ({len(description)} characters).",
            "Provide more detail about the fault — this helps reviewers process your claim faster."
        ))

    return warnings


def _check_duplicate_claim(claim) -> List[Dict]:
    """Warn if a similar claim was recently filed for the same product."""
    warnings = []
    try:
        from backend.services.duplicate_claim_detection import check_duplicate_and_flag
        result = check_duplicate_and_flag(claim)
        if result.get("is_duplicate"):
            count = result.get("high_confidence_duplicates", 0)
            warnings.append(_w(
                SEV_ERROR, "DUPLICATE_CLAIM",
                f"A very similar claim ({count} match(es)) was recently submitted for this product.",
                "Review your existing claims before submitting a new one."
            ))
        elif result.get("potential_duplicates", 0) > 0:
            warnings.append(_w(
                SEV_WARNING, "POSSIBLE_DUPLICATE",
                f"{result['potential_duplicates']} similar claim(s) found for this product.",
                "Check your claims history to avoid duplicate submissions."
            ))
    except Exception as e:
        logger.warning("Pre-submission duplicate check error: %s", e)

    return warnings


def _check_product_age(claim) -> List[Dict]:
    """Warn if product is older than its warranty covers."""
    warnings = []
    product    = getattr(claim, "product", None)
    warranty   = getattr(claim, "warranty", None)
    product_age = getattr(claim, "product_age", None)

    if product and product_age is not None:
        warranty_months = 12
        if warranty and hasattr(warranty, "warranty_duration") and warranty.warranty_duration:
            warranty_months = warranty.warranty_duration
        elif product and hasattr(product, "warranty_length") and product.warranty_length:
            warranty_months = product.warranty_length

        if product_age > warranty_months:
            warnings.append(_w(
                SEV_ERROR, "PRODUCT_AGE_EXCEEDED",
                f"Product is {product_age} months old. Warranty only covers {warranty_months} months.",
                "Claims for products older than their warranty period are rejected."
            ))
        elif product_age > warranty_months * 0.90:
            warnings.append(_w(
                SEV_WARNING, "PRODUCT_AGE_NEAR_LIMIT",
                f"Product is {product_age} months old — close to the {warranty_months}-month warranty limit.",
                "Ensure the fault date is within the warranty coverage period."
            ))

    return warnings


def _check_damage_type(claim) -> List[Dict]:
    """Warn if damage type might be excluded by the warranty."""
    warnings = []
    warranty    = getattr(claim, "warranty", None)
    damage_type = (getattr(claim, "damage_type", "") or "").lower()

    if not damage_type:
        warnings.append(_w(
            SEV_WARNING, "DAMAGE_TYPE_MISSING",
            "Damage type is not specified.",
            "Select the correct damage type from the list."
        ))
        return warnings

    if not warranty:
        return warnings

    exclusions = (getattr(warranty, "exclusions", "") or "").lower()
    physical_kw = ["physical", "impact", "crack", "drop", "scratch", "accidental"]
    water_kw    = ["water", "liquid", "flood", "moisture", "corrosion"]

    is_physical = any(kw in damage_type for kw in physical_kw)
    is_water    = any(kw in damage_type for kw in water_kw)

    if exclusions:
        if is_physical and any(kw in exclusions for kw in physical_kw):
            warnings.append(_w(
                SEV_ERROR, "DAMAGE_EXCLUDED_PHYSICAL",
                "Physical/accidental damage is listed as excluded in this warranty.",
                "Review your warranty terms. This type of damage is typically not covered."
            ))
        elif is_water and any(kw in exclusions for kw in water_kw):
            warnings.append(_w(
                SEV_ERROR, "DAMAGE_EXCLUDED_WATER",
                "Water/liquid damage is listed as excluded in this warranty.",
                "Review your warranty terms. Water damage is typically not covered."
            ))

    return warnings


# ── Public entry point ────────────────────────────────────────────────────────

def run_pre_submission_checks(claim) -> Dict[str, Any]:
    """
    Run all pre-submission checks on a claim object (Draft state).
    Returns a structured result with all warnings grouped by severity.

    Safe to call at any time — never modifies the claim or database.
    """
    all_warnings: List[Dict] = []

    checks = [
        _check_warranty_status,
        _check_fault_date,
        _check_required_documents,
        _check_fault_description,
        _check_duplicate_claim,
        _check_product_age,
        _check_damage_type,
    ]

    for fn in checks:
        try:
            all_warnings.extend(fn(claim))
        except Exception as e:
            logger.error("Pre-submission check error in %s: %s", fn.__name__, e, exc_info=True)

    errors   = [w for w in all_warnings if w["severity"] == SEV_ERROR]
    warnings = [w for w in all_warnings if w["severity"] == SEV_WARNING]
    infos    = [w for w in all_warnings if w["severity"] == SEV_INFO]

    can_submit = len(errors) == 0

    return {
        "can_submit":     can_submit,
        "total_issues":   len(all_warnings),
        "error_count":    len(errors),
        "warning_count":  len(warnings),
        "info_count":     len(infos),
        "errors":         errors,
        "warnings":       warnings,
        "infos":          infos,
        "all_issues":     all_warnings,
        "summary": (
            "Claim is ready to submit." if can_submit
            else f"{len(errors)} issue(s) must be fixed before submitting."
        )
    }
