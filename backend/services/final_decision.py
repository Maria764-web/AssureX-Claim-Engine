"""
AssureX Final Decision Service
Aggregates warranty rule results and AI model predictions into a single
authoritative claim decision and updates the claim status in the database.
"""

import logging
import time
from typing import Dict, Any, Optional, Tuple

from backend.extensions import db
from backend.models.claim import (
    Claim,
    CLAIM_STATUS_APPROVED,
    CLAIM_STATUS_REJECTED,
    CLAIM_STATUS_MANUAL_REVIEW,
    CLAIM_STATUS_UNDER_EVALUATION
)
from backend.services.warranty_rules import run_all_warranty_rules
from backend.services.python_model_service import predict_claim_decision, save_claim_prediction
from backend.services.contradiction_detection import detect_contradictions
from backend.services.audit_service import log_audit_event
from backend.utils.helpers import utc_now

logger = logging.getLogger(__name__)

DECISION_APPROVED = "Approved"
DECISION_REJECTED = "Rejected"
DECISION_MANUAL_REVIEW = "Manual Review"

# SRS display labels (shown to users in UI)
DISPLAY_LABEL = {
    DECISION_APPROVED:      "Likely Valid",
    DECISION_REJECTED:      "Likely Invalid",
    DECISION_MANUAL_REVIEW: "Manual Review Required",
}

CONFIDENCE_HIGH = 0.80
CONFIDENCE_LOW = 0.55


def _map_rule_recommendation_to_decision(recommendation: str) -> str:
    mapping = {
        "Approve": DECISION_APPROVED,
        "Reject": DECISION_REJECTED,
        "Manual Review": DECISION_MANUAL_REVIEW
    }
    return mapping.get(recommendation, DECISION_MANUAL_REVIEW)


def _resolve_ai_decision(prediction: Dict[str, Any]) -> Tuple[str, float]:
    """Extract AI decision and confidence from python model prediction result."""
    if not prediction.get("success"):
        return DECISION_MANUAL_REVIEW, 0.0

    predicted_class = prediction.get("predicted_class", "")
    confidence = float(prediction.get("confidence", 0.0))

    if predicted_class == "Valid":
        return DECISION_APPROVED, confidence
    elif predicted_class == "Invalid":
        return DECISION_REJECTED, confidence
    else:
        return DECISION_MANUAL_REVIEW, confidence


def compute_final_decision(
    claim: Claim,
    run_rules: bool = True,
    run_ai: bool = True
) -> Dict[str, Any]:
    """
    Compute the final claim decision by combining rule engine and AI model results.

    Decision logic:
    - Both rule engine AND AI agree → use that decision
    - Rule engine says Reject + AI says Reject → Reject
    - Rule engine says Approve + AI confidence >= HIGH → Approve
    - Rule engine says Manual Review OR AI confidence < LOW → Manual Review
    - Any disagreement with moderate confidence → Manual Review

    Returns:
        dict with final_decision, confidence_score, rule_results, ai_prediction, reasoning
    """
    rule_results = []
    rule_recommendation = DECISION_MANUAL_REVIEW
    ai_prediction = {}
    ai_decision = DECISION_MANUAL_REVIEW
    ai_confidence = 0.0
    reasoning_parts = []
    contradiction_result = {}

    # Step 1: Run warranty rules
    if run_rules:
        try:
            raw_rules, rules_passed, rule_rec = run_all_warranty_rules(claim, save_results=True)
            rule_results = raw_rules
            rule_recommendation = _map_rule_recommendation_to_decision(rule_rec)
            reasoning_parts.append(f"Rule engine recommendation: {rule_recommendation} ({len([r for r in raw_rules if r['status']=='Failed'])} hard fails).")
        except Exception as e:
            logger.error("Rule engine error for claim %s: %s", claim.claim_uid, e)
            rule_recommendation = DECISION_MANUAL_REVIEW
            reasoning_parts.append(f"Rule engine error: {str(e)[:120]}")

    # Step 1b: Contradiction detection
    try:
        contradiction_result = detect_contradictions(claim)
        if contradiction_result.get("contradictions_found"):
            count = contradiction_result.get("contradiction_count", 0)
            reasoning_parts.append(f"Contradiction check: {count} logical inconsistency(ies) detected — escalating to Manual Review.")
            rule_recommendation = DECISION_MANUAL_REVIEW
    except Exception as e:
        logger.warning("Contradiction detection error for claim %s: %s", claim.claim_uid, e)

    # Step 2: Run AI prediction
    if run_ai:
        try:
            ai_prediction = predict_claim_decision(claim)
            if ai_prediction.get("success"):
                ai_decision, ai_confidence = _resolve_ai_decision(ai_prediction)
                save_claim_prediction(claim.id, ai_prediction)
                reasoning_parts.append(
                    f"AI model: {ai_prediction.get('predicted_class')} ({ai_confidence:.0%} confidence)."
                )
            else:
                reasoning_parts.append("AI model unavailable; decision based on rules only.")
        except Exception as e:
            logger.error("AI prediction error for claim %s: %s", claim.claim_uid, e)
            reasoning_parts.append(f"AI model error: {str(e)[:120]}")

    # Step 3: Aggregate final decision
    final_decision = _aggregate_decision(
        rule_recommendation=rule_recommendation,
        ai_decision=ai_decision,
        ai_confidence=ai_confidence,
        has_ai=bool(ai_prediction.get("success")),
        reasoning_parts=reasoning_parts
    )

    reasoning = " ".join(reasoning_parts)

    return {
        "final_decision": final_decision,
        "display_label": DISPLAY_LABEL.get(final_decision, final_decision),
        "rule_recommendation": rule_recommendation,
        "ai_decision": ai_decision,
        "ai_confidence": round(ai_confidence, 4),
        "rule_results": rule_results,
        "ai_prediction": ai_prediction,
        "contradiction_result": contradiction_result,
        "reasoning": reasoning,
        "claim_uid": claim.claim_uid
    }


def _aggregate_decision(
    rule_recommendation: str,
    ai_decision: str,
    ai_confidence: float,
    has_ai: bool,
    reasoning_parts: list
) -> str:
    """Combine rule and AI outcomes into one authoritative decision."""

    if not has_ai:
        reasoning_parts.append("Final decision based on rules only (AI unavailable).")
        return rule_recommendation

    # Both agree
    if rule_recommendation == ai_decision:
        reasoning_parts.append(f"Rules and AI agree: {rule_recommendation}.")
        return rule_recommendation

    # Hard reject from rules overrides AI
    if rule_recommendation == DECISION_REJECTED:
        reasoning_parts.append("Rules hard-reject overrides AI approval.")
        return DECISION_REJECTED

    # AI rejects with high confidence, rules were not conclusive
    if ai_decision == DECISION_REJECTED and ai_confidence >= CONFIDENCE_HIGH:
        if rule_recommendation != DECISION_APPROVED:
            reasoning_parts.append("AI rejects with high confidence, escalating.")
            return DECISION_REJECTED

    # AI approves with high confidence and rules approve
    if ai_decision == DECISION_APPROVED and ai_confidence >= CONFIDENCE_HIGH and rule_recommendation == DECISION_APPROVED:
        reasoning_parts.append("Both sources approve with high confidence.")
        return DECISION_APPROVED

    # Low AI confidence → always manual review
    if ai_confidence < CONFIDENCE_LOW:
        reasoning_parts.append(f"AI confidence low ({ai_confidence:.0%}); escalating to manual review.")
        return DECISION_MANUAL_REVIEW

    # Any remaining disagreement → manual review
    reasoning_parts.append("Disagreement between rule engine and AI; escalating to manual review.")
    return DECISION_MANUAL_REVIEW


def apply_final_decision_to_claim(
    claim: Claim,
    decision_result: Dict[str, Any],
    reviewer_id: Optional[int] = None
) -> Claim:
    """
    Persist the final decision on the claim and update its status.

    Args:
        claim: Claim model instance.
        decision_result: Output from compute_final_decision().
        reviewer_id: Optional user ID of the reviewer triggering this (for audit).

    Returns:
        Updated Claim instance.
    """
    final_decision = decision_result.get("final_decision", DECISION_MANUAL_REVIEW)

    status_map = {
        DECISION_APPROVED: CLAIM_STATUS_APPROVED,
        DECISION_REJECTED: CLAIM_STATUS_REJECTED,
        DECISION_MANUAL_REVIEW: CLAIM_STATUS_MANUAL_REVIEW
    }

    new_status = status_map.get(final_decision, CLAIM_STATUS_MANUAL_REVIEW)

    claim.final_decision = final_decision
    claim.claim_status = new_status
    claim.decision_reasoning = decision_result.get("reasoning", "")[:1000]
    claim.updated_at = utc_now()

    try:
        db.session.commit()
    except Exception as e:
        logger.error("Failed to save final decision for claim %s: %s", claim.claim_uid, e)
        db.session.rollback()
        raise

    log_audit_event(
        action="FINAL_DECISION_APPLIED",
        entity_type="Claim",
        entity_id=claim.claim_uid,
        user_id=reviewer_id,
        description=(
            f"Final decision '{final_decision}' applied to claim {claim.claim_uid}. "
            f"Status → {new_status}. {decision_result.get('reasoning', '')[:200]}"
        )
    )

    # Notify customer of decision and notify reviewers if manual review needed
    try:
        from backend.services.notification_service import notify_claim_decision, notify_manual_review_assigned, notify_claim_approved_service
        notify_claim_decision(claim)
        if final_decision == DECISION_MANUAL_REVIEW:
            notify_manual_review_assigned(claim)
        elif final_decision == DECISION_APPROVED:
            notify_claim_approved_service(claim)
    except Exception:
        pass

    return claim


def run_full_claim_evaluation(claim: Claim, reviewer_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Full pipeline: run rules + AI + apply decision.

    Returns complete evaluation result including updated claim and processing_time_ms.
    """
    t_start = time.perf_counter()

    claim.claim_status = CLAIM_STATUS_UNDER_EVALUATION
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()

    decision_result = compute_final_decision(claim, run_rules=True, run_ai=True)

    try:
        updated_claim = apply_final_decision_to_claim(claim, decision_result, reviewer_id)
        decision_result["claim"] = updated_claim.to_dict()
        decision_result["success"] = True
    except Exception as e:
        decision_result["success"] = False
        decision_result["error"] = str(e)

    elapsed_ms = round((time.perf_counter() - t_start) * 1000)
    decision_result["processing_time_ms"] = elapsed_ms
    logger.info("Full evaluation for claim %s completed in %d ms", claim.claim_uid, elapsed_ms)

    return decision_result
