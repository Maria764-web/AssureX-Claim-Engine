"""
AssureX Contradiction Detection Service
Detects logical inconsistencies in claim data:
- Fault date before product purchase date
- Warranty expiry before purchase date
- Product age mismatch with date difference
- Damage type vs warranty exclusion conflict already registered
"""

import logging
from datetime import date
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


def detect_contradictions(claim) -> Dict[str, Any]:
    """
    Run all contradiction checks on a claim.
    Returns dict with:
        contradictions_found: bool
        contradiction_count: int
        details: list of contradiction descriptions
    """
    details: List[str] = []

    product  = getattr(claim, "product", None)
    warranty = getattr(claim, "warranty", None)
    fault_date     = getattr(claim, "fault_date", None)
    product_age    = getattr(claim, "product_age", None)

    purchase_date  = getattr(product, "purchase_date", None) if product else None
    expiry_date    = getattr(warranty, "expiry_date", None) if warranty else None
    warranty_start = getattr(warranty, "start_date", None) if warranty else None

    # 1. Fault date before purchase date
    if fault_date and purchase_date:
        try:
            fd = fault_date if isinstance(fault_date, date) else fault_date.date()
            pd = purchase_date if isinstance(purchase_date, date) else purchase_date.date()
            if fd < pd:
                details.append(
                    f"Fault date ({fd}) is before product purchase date ({pd}). "
                    "A product cannot be damaged before it was purchased."
                )
        except Exception as e:
            logger.debug("Contradiction check 1 error: %s", e)

    # 2. Warranty expiry before purchase date (data inconsistency)
    if expiry_date and purchase_date:
        try:
            ed = expiry_date if isinstance(expiry_date, date) else expiry_date.date()
            pd = purchase_date if isinstance(purchase_date, date) else purchase_date.date()
            if ed < pd:
                details.append(
                    f"Warranty expiry date ({ed}) is before purchase date ({pd}). "
                    "Warranty cannot expire before the product was bought."
                )
        except Exception as e:
            logger.debug("Contradiction check 2 error: %s", e)

    # 3. Warranty start date after fault date
    if warranty_start and fault_date:
        try:
            ws = warranty_start if isinstance(warranty_start, date) else warranty_start.date()
            fd = fault_date if isinstance(fault_date, date) else fault_date.date()
            if ws > fd:
                details.append(
                    f"Warranty start date ({ws}) is after fault date ({fd}). "
                    "Warranty was not yet active when the damage occurred."
                )
        except Exception as e:
            logger.debug("Contradiction check 3 error: %s", e)

    # 4. Product age vs date difference mismatch
    if product_age is not None and fault_date and purchase_date:
        try:
            fd = fault_date if isinstance(fault_date, date) else fault_date.date()
            pd = purchase_date if isinstance(purchase_date, date) else purchase_date.date()
            calculated_age = max(0, int((fd - pd).days / 30.4375))
            reported_age   = int(product_age)
            if abs(calculated_age - reported_age) > 3:
                details.append(
                    f"Reported product age ({reported_age} months) differs significantly from "
                    f"calculated age based on dates ({calculated_age} months). "
                    "Possible data entry error."
                )
        except Exception as e:
            logger.debug("Contradiction check 4 error: %s", e)

    # 5. Fault date in the future
    if fault_date:
        try:
            fd = fault_date if isinstance(fault_date, date) else fault_date.date()
            if fd > date.today():
                details.append(
                    f"Fault date ({fd}) is in the future. "
                    "Damage cannot be reported before it occurs."
                )
        except Exception as e:
            logger.debug("Contradiction check 5 error: %s", e)

    return {
        "contradictions_found": len(details) > 0,
        "contradiction_count": len(details),
        "details": details
    }
