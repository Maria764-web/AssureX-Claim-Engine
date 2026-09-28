"""
AssureX Serial Number Verification Service
Cross-checks the serial number extracted via OCR from submitted documents
against the serial number registered on the product record.
"""

import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# Verification result constants
SERIAL_MATCH       = "Serial Match"
SERIAL_MISMATCH    = "Serial Mismatch"
SERIAL_NOT_FOUND   = "Serial Not Extracted"
SERIAL_NO_OCR      = "No OCR Data"
SERIAL_NO_PRODUCT  = "No Product Record"


def verify_serial_number(claim) -> Dict[str, Any]:
    """
    Verify that the serial number extracted from OCR documents matches
    the serial number on the registered product.

    Returns a dict with keys:
        - verified (bool): True if match confirmed or inconclusive (no OCR data)
        - status (str): one of SERIAL_* constants above
        - matched_serial (str|None): the extracted serial that matched, if any
        - product_serial (str|None): the registered product serial
        - details (str): human-readable explanation
    """
    product = getattr(claim, "product", None)
    extractions = getattr(claim, "extractions", []) or []

    if not product:
        return {
            "verified": False,
            "status": SERIAL_NO_PRODUCT,
            "matched_serial": None,
            "product_serial": None,
            "details": "Cannot verify serial number: no product record linked to claim."
        }

    prod_sn = (getattr(product, "serial_number", "") or "").strip().lower()

    if not extractions:
        return {
            "verified": True,   # no OCR → inconclusive, not a hard failure
            "status": SERIAL_NO_OCR,
            "matched_serial": None,
            "product_serial": product.serial_number,
            "details": "No OCR document extractions available. Serial number verification skipped."
        }

    extracted_sns: List[str] = []
    for ext in extractions:
        vf = getattr(ext, "verified_fields", {}) or {}
        ef = getattr(ext, "extracted_fields", {}) or {}
        sn = vf.get("serial_number") or ef.get("serial_number")
        if sn:
            extracted_sns.append(str(sn).strip().lower())

    if not extracted_sns:
        return {
            "verified": True,   # OCR ran but serial field was not found — not a hard failure
            "status": SERIAL_NOT_FOUND,
            "matched_serial": None,
            "product_serial": product.serial_number,
            "details": "Serial number field was not found in OCR extraction results."
        }

    for sn in extracted_sns:
        if sn == prod_sn:
            return {
                "verified": True,
                "status": SERIAL_MATCH,
                "matched_serial": product.serial_number,
                "product_serial": product.serial_number,
                "details": (
                    f"Extracted serial number matches registered product "
                    f"({product.serial_number})."
                )
            }

    return {
        "verified": False,
        "status": SERIAL_MISMATCH,
        "matched_serial": None,
        "product_serial": product.serial_number,
        "details": (
            f"Extracted serial(s) {extracted_sns} do not match "
            f"registered product serial ({product.serial_number})."
        )
    }


def run_serial_verification(claim) -> Dict[str, Any]:
    """
    Public entry point — wraps verify_serial_number with error handling.
    Always returns a safe result dict even if an exception occurs.
    """
    try:
        return verify_serial_number(claim)
    except Exception as e:
        logger.error(
            "Serial verification error for claim %s: %s",
            getattr(claim, "claim_uid", "?"), e, exc_info=True
        )
        return {
            "verified": False,
            "status": "Verification Error",
            "matched_serial": None,
            "product_serial": None,
            "details": f"Serial verification could not complete: {e}"
        }
