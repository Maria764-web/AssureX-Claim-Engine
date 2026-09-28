"""
AssureX Model Comparison Service
Compares predictions from the Python (sklearn) model and the
Teachable Machine vision model for a given claim.
"""

import logging
from typing import Dict, Any, Optional

from backend.services.python_model_service import predict_claim_decision
from backend.services.teachable_machine_service import predict_image_claim_decision

logger = logging.getLogger(__name__)

CONSISTENCY_STRONG_MATCH      = "Strong Match"
CONSISTENCY_ACCEPTABLE_MATCH  = "Acceptable Match"
CONSISTENCY_WEAK_MATCH        = "Weak Match"
CONSISTENCY_DISAGREEMENT      = "Model Disagreement"
CONSISTENCY_UNCERTAIN         = "Uncertain Result"


def compare_models_for_claim(claim, image_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Run both the Python ML model and Teachable Machine on the same claim,
    then compute an agreement score and combined recommendation.

    Args:
        claim: Claim model instance.
        image_path: Optional explicit image path for Teachable Machine.

    Returns:
        Comparison result dict with both predictions, agreement level, and recommendation.
    """
    python_result = {}
    tm_result = {}
    errors = []

    # Run Python model
    try:
        python_result = predict_claim_decision(claim)
        if not python_result.get("success"):
            errors.append(f"Python model: {python_result.get('error', 'unknown error')}")
    except Exception as e:
        errors.append(f"Python model exception: {str(e)}")
        python_result = {"success": False, "error": str(e)}

    # Run Teachable Machine model
    try:
        tm_result = predict_image_claim_decision(claim=claim, image_path=image_path)
        if not tm_result.get("success"):
            errors.append(f"Teachable Machine: {tm_result.get('error', 'unknown error')}")
    except Exception as e:
        errors.append(f"Teachable Machine exception: {str(e)}")
        tm_result = {"success": False, "error": str(e)}

    python_class = python_result.get("predicted_class") if python_result.get("success") else None
    tm_class = tm_result.get("predicted_class") if tm_result.get("success") else None
    python_conf = float(python_result.get("confidence", 0.0)) if python_result.get("success") else 0.0
    tm_conf = float(tm_result.get("confidence", 0.0)) if tm_result.get("success") else 0.0

    # Compute consistency status + confidence gap
    consistency_status, combined_confidence = _compute_consistency(
        python_result.get("success"), python_class, python_conf,
        tm_result.get("success"), tm_class, tm_conf
    )
    confidence_gap = round(abs(python_conf - tm_conf), 4)

    # Combined recommendation
    recommendation = _combined_recommendation(
        python_class, python_conf, tm_class, tm_conf, consistency_status
    )

    return {
        "python_model": {
            "success": python_result.get("success", False),
            "predicted_class": python_class,
            "confidence": python_conf,
            "valid_confidence": python_result.get("valid_confidence", 0.0),
            "invalid_confidence": python_result.get("invalid_confidence", 0.0),
            "manual_review_confidence": python_result.get("manual_review_confidence", 0.0),
            "model_name": python_result.get("model_name", "Python ML"),
            "error": python_result.get("error")
        },
        "teachable_machine": {
            "success": tm_result.get("success", False),
            "predicted_class": tm_class,
            "confidence": tm_conf,
            "valid_confidence": tm_result.get("valid_confidence", 0.0),
            "invalid_confidence": tm_result.get("invalid_confidence", 0.0),
            "manual_review_confidence": tm_result.get("manual_review_confidence", 0.0),
            "model_name": tm_result.get("model_name", "Teachable Machine"),
            "image_name": tm_result.get("image_name"),
            "error": tm_result.get("error")
        },
        "comparison": {
            "consistency_status": consistency_status,
            "confidence_gap": confidence_gap,
            "combined_confidence": round(combined_confidence, 4),
            "recommendation": recommendation,
            "models_agree": python_class == tm_class and python_class is not None,
            "both_available": python_result.get("success") and tm_result.get("success")
        },
        "errors": errors,
        "claim_uid": getattr(claim, "claim_uid", None)
    }


def _compute_consistency(
    python_ok: bool, python_class: Optional[str], python_conf: float,
    tm_ok: bool, tm_class: Optional[str], tm_conf: float
) -> tuple:
    """
    Compute SRS-defined consistency status and combined confidence.

    Status tags (SRS requirement):
      Strong Match      — same class, combined conf ≥ 0.80
      Acceptable Match  — same class, combined conf 0.60–0.79
      Weak Match        — same class, combined conf < 0.60
      Model Disagreement — different classes (both models ran successfully)
      Uncertain Result  — one or both models unavailable / failed
    """
    if not python_ok or not tm_ok:
        available_conf = python_conf if python_ok else (tm_conf if tm_ok else 0.0)
        return CONSISTENCY_UNCERTAIN, available_conf

    if not python_class or not tm_class:
        return CONSISTENCY_UNCERTAIN, (python_conf + tm_conf) / 2.0

    combined_conf = (python_conf + tm_conf) / 2.0

    if python_class != tm_class:
        return CONSISTENCY_DISAGREEMENT, combined_conf

    # Same class — differentiate by combined confidence
    if combined_conf >= 0.80:
        return CONSISTENCY_STRONG_MATCH, combined_conf
    elif combined_conf >= 0.60:
        return CONSISTENCY_ACCEPTABLE_MATCH, combined_conf
    else:
        return CONSISTENCY_WEAK_MATCH, combined_conf


def _combined_recommendation(
    python_class: Optional[str],
    python_conf: float,
    tm_class: Optional[str],
    tm_conf: float,
    consistency_status: str
) -> str:
    """Derive a combined recommendation from both model outputs."""

    if consistency_status in (CONSISTENCY_STRONG_MATCH, CONSISTENCY_ACCEPTABLE_MATCH) and python_class:
        return python_class

    if consistency_status == CONSISTENCY_WEAK_MATCH and python_class == tm_class:
        return python_class

    # Model Disagreement or Uncertain → check for strong individual signals
    if python_class == "Invalid" or tm_class == "Invalid":
        if (python_class == "Invalid" and python_conf >= 0.75) or \
           (tm_class == "Invalid" and tm_conf >= 0.75):
            return "Invalid"

    if python_class == "Valid" and tm_class == "Valid":
        return "Valid"

    return "Manual Review"
