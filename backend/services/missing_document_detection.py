"""
AssureX Missing Document Detection Service
Checks whether a claim submission includes all required supporting documents.

Required documents for a valid claim:
  1. Receipt or Invoice (proof of purchase)
  2. Damage Photo or Diagnostic Report (evidence of fault)

Optional but recommended:
  - Product Photo (showing model/serial label)
  - Repair History document
"""

import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

# Required document categories and the keywords that identify them
REQUIRED_DOCUMENT_TYPES: List[Dict[str, Any]] = [
    {
        "label": "Receipt or Invoice",
        "keywords": ["receipt", "invoice", "proof of purchase", "purchase receipt"],
        "required": True
    },
    {
        "label": "Damage Photo or Diagnostic Report",
        "keywords": ["photo", "damage", "diagnostic", "fault photo", "evidence photo"],
        "required": True
    }
]

OPTIONAL_DOCUMENT_TYPES: List[Dict[str, Any]] = [
    {
        "label": "Product Photo",
        "keywords": ["product photo", "product image", "serial label"]
    },
    {
        "label": "Repair History",
        "keywords": ["repair", "service history", "maintenance"]
    }
]


def detect_missing_documents(claim) -> Dict[str, Any]:
    """
    Analyse the documents attached to a claim and report which required
    document types are present and which are missing.

    Returns:
        - all_required_present (bool): True if every required type is found
        - missing (list[str]): labels of required document types not found
        - present (list[str]): labels of document types that are found
        - optional_present (list[str]): optional docs that were submitted
        - total_documents (int): total number of documents on the claim
        - details (str): human-readable summary
    """
    documents = getattr(claim, "documents", []) or []
    doc_types_lower = [(getattr(d, "document_type", "") or "").lower() for d in documents]

    present: List[str] = []
    missing: List[str] = []

    for doc_def in REQUIRED_DOCUMENT_TYPES:
        found = any(
            any(kw in dt for kw in doc_def["keywords"])
            for dt in doc_types_lower
        )
        if found:
            present.append(doc_def["label"])
        else:
            missing.append(doc_def["label"])

    optional_present: List[str] = []
    for doc_def in OPTIONAL_DOCUMENT_TYPES:
        found = any(
            any(kw in dt for kw in doc_def["keywords"])
            for dt in doc_types_lower
        )
        if found:
            optional_present.append(doc_def["label"])

    all_required_present = len(missing) == 0

    if all_required_present:
        details = (
            f"All required documents present ({len(documents)} total). "
            f"Found: {', '.join(present)}."
        )
        if optional_present:
            details += f" Optional also present: {', '.join(optional_present)}."
    else:
        details = f"Missing required documents: {', '.join(missing)}."
        if present:
            details += f" Present: {', '.join(present)}."

    return {
        "all_required_present": all_required_present,
        "missing": missing,
        "present": present,
        "optional_present": optional_present,
        "total_documents": len(documents),
        "details": details
    }


def run_missing_document_detection(claim) -> Dict[str, Any]:
    """
    Public entry point — wraps detect_missing_documents with error handling.
    Always returns a safe result dict even if an exception occurs.
    """
    try:
        return detect_missing_documents(claim)
    except Exception as e:
        logger.error(
            "Missing document detection error for claim %s: %s",
            getattr(claim, "claim_uid", "?"), e, exc_info=True
        )
        return {
            "all_required_present": False,
            "missing": ["Unknown — detection error"],
            "present": [],
            "optional_present": [],
            "total_documents": 0,
            "details": f"Document detection could not complete: {e}"
        }
