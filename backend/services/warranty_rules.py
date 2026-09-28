"""
AssureX Warranty Rules Engine
Deterministic rule checks: warranty validity, damage coverage, exclusions,
serial number match, and document completeness for claim evaluation.
"""

import logging
from datetime import date
from typing import Dict, Any, List, Tuple, Optional

from backend.extensions import db
from backend.models.rule_result import (
    RuleResult,
    RULE_STATUS_PASSED,
    RULE_STATUS_FAILED,
    RULE_STATUS_WARNING,
    RULE_STATUS_INCONCLUSIVE
)
from backend.utils.helpers import utc_now

logger = logging.getLogger(__name__)


def _save_rule_result(claim_id: int, rule_name: str, status: str, result: str, details: str = "") -> RuleResult:
    rr = RuleResult(
        claim_id=claim_id,
        rule_name=rule_name,
        rule_status=status,
        rule_result=result,
        details=details,
        checked_at=utc_now()
    )
    db.session.add(rr)
    return rr


def check_warranty_active(claim) -> Dict[str, Any]:
    """Rule 1: Warranty must be active on the fault date."""
    warranty = getattr(claim, "warranty", None)
    fault_date = getattr(claim, "fault_date", None)

    if not warranty:
        return {
            "rule_name": "Warranty Active Check",
            "status": RULE_STATUS_FAILED,
            "result": "No Warranty Linked",
            "details": "Claim has no associated warranty record.",
            "passed": False
        }

    check_date = fault_date if isinstance(fault_date, date) else date.today()
    status = warranty.calculate_status(check_date)

    if status == "Expired":
        return {
            "rule_name": "Warranty Active Check",
            "status": RULE_STATUS_FAILED,
            "result": "Warranty Expired",
            "details": f"Warranty expired on {warranty.expiry_date}. Fault date: {fault_date}.",
            "passed": False
        }
    if status in ("Active", "Nearing Expiry", "Extended"):
        return {
            "rule_name": "Warranty Active Check",
            "status": RULE_STATUS_PASSED,
            "result": f"Warranty {status}",
            "details": f"Warranty valid until {warranty.expiry_date}.",
            "passed": True
        }

    return {
        "rule_name": "Warranty Active Check",
        "status": RULE_STATUS_WARNING,
        "result": f"Warranty Status: {status}",
        "details": "Warranty status could not be definitively confirmed.",
        "passed": False
    }


def check_damage_type_covered(claim) -> Dict[str, Any]:
    """Rule 2: Damage type must not be in warranty exclusions."""
    warranty = getattr(claim, "warranty", None)
    damage_type = (getattr(claim, "damage_type", "") or "").lower()

    if not warranty:
        return {
            "rule_name": "Damage Coverage Check",
            "status": RULE_STATUS_INCONCLUSIVE,
            "result": "No Warranty",
            "details": "Cannot verify coverage without a linked warranty.",
            "passed": False
        }

    exclusions_raw = getattr(warranty, "exclusions", "") or ""
    exclusions_lower = exclusions_raw.lower()

    physical_keywords = ["physical", "impact", "crack", "drop", "scratch", "accidental", "cosmetic", "casing damage"]
    water_keywords = ["water", "liquid", "flood", "moisture", "corrosion"]

    is_physical = any(kw in damage_type for kw in physical_keywords)
    is_water = any(kw in damage_type for kw in water_keywords)

    excluded = False
    exclusion_reason = ""

    if exclusions_lower:
        if any(kw in exclusions_lower for kw in physical_keywords) and is_physical:
            excluded = True
            exclusion_reason = "Physical/accidental damage is excluded under this warranty."
        elif any(kw in exclusions_lower for kw in water_keywords) and is_water:
            excluded = True
            exclusion_reason = "Water/liquid damage is excluded under this warranty."
        elif damage_type and damage_type in exclusions_lower:
            excluded = True
            exclusion_reason = f"Damage type '{damage_type}' found in warranty exclusions."

    if excluded:
        return {
            "rule_name": "Damage Coverage Check",
            "status": RULE_STATUS_FAILED,
            "result": "Damage Not Covered",
            "details": exclusion_reason,
            "passed": False
        }

    covered_raw = getattr(warranty, "covered_items", "") or ""
    return {
        "rule_name": "Damage Coverage Check",
        "status": RULE_STATUS_PASSED,
        "result": "Damage Covered",
        "details": f"No exclusion found for damage type: {damage_type or 'unspecified'}.",
        "passed": True
    }


def check_serial_number_match(claim) -> Dict[str, Any]:
    """Rule 3: Extracted serial number from documents must match product record."""
    product = getattr(claim, "product", None)
    extractions = getattr(claim, "extractions", []) or []

    if not product:
        return {
            "rule_name": "Serial Number Match",
            "status": RULE_STATUS_INCONCLUSIVE,
            "result": "No Product",
            "details": "Cannot verify serial number without product record.",
            "passed": False
        }

    prod_sn = (getattr(product, "serial_number", "") or "").strip().lower()

    if not extractions:
        return {
            "rule_name": "Serial Number Match",
            "status": RULE_STATUS_WARNING,
            "result": "No OCR Data",
            "details": "No document OCR data available to verify serial number.",
            "passed": True  # warning but don't hard-fail for missing OCR
        }

    extracted_sns = []
    for ext in extractions:
        vf = getattr(ext, "verified_fields", {}) or {}
        ef = getattr(ext, "extracted_fields", {}) or {}
        sn = vf.get("serial_number") or ef.get("serial_number")
        if sn:
            extracted_sns.append(str(sn).strip().lower())

    if not extracted_sns:
        return {
            "rule_name": "Serial Number Match",
            "status": RULE_STATUS_WARNING,
            "result": "Serial Not Extracted",
            "details": "Serial number could not be extracted from submitted documents.",
            "passed": True
        }

    if any(sn == prod_sn for sn in extracted_sns):
        return {
            "rule_name": "Serial Number Match",
            "status": RULE_STATUS_PASSED,
            "result": "Serial Match",
            "details": f"Extracted serial number matches product record ({product.serial_number}).",
            "passed": True
        }

    return {
        "rule_name": "Serial Number Match",
        "status": RULE_STATUS_FAILED,
        "result": "Serial Mismatch",
        "details": f"Extracted serial(s) {extracted_sns} do not match product record ({prod_sn}).",
        "passed": False
    }


def check_required_documents(claim) -> Dict[str, Any]:
    """Rule 4: Receipt/Invoice and Damage Photo must be present."""
    documents = getattr(claim, "documents", []) or []
    doc_types = [(getattr(d, "document_type", "") or "").lower() for d in documents]

    has_receipt = any("receipt" in dt or "invoice" in dt for dt in doc_types)
    has_damage_photo = any("photo" in dt or "damage" in dt or "diagnostic" in dt for dt in doc_types)

    missing = []
    if not has_receipt:
        missing.append("Receipt or Invoice")
    if not has_damage_photo:
        missing.append("Damage Photo or Diagnostic Report")

    if missing:
        return {
            "rule_name": "Required Documents Check",
            "status": RULE_STATUS_FAILED,
            "result": "Missing Documents",
            "details": f"Missing required documents: {', '.join(missing)}.",
            "passed": False
        }

    return {
        "rule_name": "Required Documents Check",
        "status": RULE_STATUS_PASSED,
        "result": "All Required Documents Present",
        "details": f"{len(documents)} documents submitted. Receipt and damage photo confirmed.",
        "passed": True
    }


def check_product_age_within_warranty(claim) -> Dict[str, Any]:
    """Rule 5: Product age at fault date must be within warranty duration."""
    product = getattr(claim, "product", None)
    warranty = getattr(claim, "warranty", None)
    product_age = getattr(claim, "product_age", None)

    if not product:
        return {
            "rule_name": "Product Age vs Warranty Duration",
            "status": RULE_STATUS_INCONCLUSIVE,
            "result": "No Product",
            "details": "Cannot check age without product record.",
            "passed": False
        }

    if product_age is None:
        return {
            "rule_name": "Product Age vs Warranty Duration",
            "status": RULE_STATUS_WARNING,
            "result": "Age Unknown",
            "details": "Product age at fault date could not be determined.",
            "passed": True
        }

    warranty_months = getattr(product, "warranty_length", 12) or 12
    if warranty and hasattr(warranty, "warranty_duration"):
        warranty_months = warranty.warranty_duration or warranty_months

    if product_age > warranty_months:
        return {
            "rule_name": "Product Age vs Warranty Duration",
            "status": RULE_STATUS_FAILED,
            "result": "Product Beyond Warranty Period",
            "details": f"Product age at fault: {product_age} months. Warranty covers: {warranty_months} months.",
            "passed": False
        }

    return {
        "rule_name": "Product Age vs Warranty Duration",
        "status": RULE_STATUS_PASSED,
        "result": "Within Warranty Period",
        "details": f"Product age at fault: {product_age} months within {warranty_months}-month warranty.",
        "passed": True
    }


def run_all_warranty_rules(claim, save_results: bool = True) -> Tuple[List[Dict[str, Any]], bool, str]:
    """
    Run all deterministic warranty rules for a claim.

    Args:
        claim: Claim model instance.
        save_results: Whether to persist RuleResult records to the database.

    Returns:
        (rule_results_list, overall_passed, recommendation)
        recommendation: "Approve", "Reject", or "Manual Review"
    """
    rule_fns = [
        check_warranty_active,
        check_damage_type_covered,
        check_serial_number_match,
        check_required_documents,
        check_product_age_within_warranty
    ]

    results = []
    for fn in rule_fns:
        try:
            res = fn(claim)
            results.append(res)
        except Exception as e:
            logger.error("Rule check error in %s: %s", fn.__name__, e, exc_info=True)
            results.append({
                "rule_name": fn.__name__,
                "status": RULE_STATUS_INCONCLUSIVE,
                "result": "Rule Error",
                "details": str(e),
                "passed": False
            })

    if save_results:
        try:
            for r in results:
                _save_rule_result(
                    claim_id=claim.id,
                    rule_name=r["rule_name"],
                    status=r["status"],
                    result=r["result"],
                    details=r.get("details", "")
                )
            db.session.commit()
        except Exception as e:
            logger.error("Failed to save rule results: %s", e)
            try:
                db.session.rollback()
            except Exception:
                pass

    hard_fails = [r for r in results if r["status"] == RULE_STATUS_FAILED]
    warnings = [r for r in results if r["status"] == RULE_STATUS_WARNING]
    inconclusives = [r for r in results if r["status"] == RULE_STATUS_INCONCLUSIVE]

    if len(hard_fails) >= 2:
        recommendation = "Reject"
        overall_passed = False
    elif len(hard_fails) == 1:
        recommendation = "Manual Review"
        overall_passed = False
    elif warnings or inconclusives:
        recommendation = "Manual Review"
        overall_passed = True
    else:
        recommendation = "Approve"
        overall_passed = True

    return results, overall_passed, recommendation
