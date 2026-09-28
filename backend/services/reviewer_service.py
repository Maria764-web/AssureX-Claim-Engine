"""
AssureX Reviewer Service
Manual claim review workflow: approve, reject, request additional info,
and escalate claims with full audit trail.
"""

import logging
from typing import Dict, Any, Optional, List

from backend.extensions import db
from backend.models.claim import (
    Claim,
    CLAIM_STATUS_APPROVED,
    CLAIM_STATUS_REJECTED,
    CLAIM_STATUS_MANUAL_REVIEW,
    CLAIM_STATUS_ADDITIONAL_INFO,
    CLAIM_STATUS_UNDER_EVALUATION,
    CLAIM_STATUS_SUBMITTED,
    CLAIM_STATUS_CLOSED
)
from backend.models.notification import Notification
from backend.services.audit_service import log_audit_event
from backend.utils.helpers import utc_now

logger = logging.getLogger(__name__)

REVIEW_ACTION_APPROVE = "approve"
REVIEW_ACTION_REJECT = "reject"
REVIEW_ACTION_REQUEST_INFO = "request_info"
REVIEW_ACTION_ESCALATE = "escalate"

VALID_REVIEW_ACTIONS = {
    REVIEW_ACTION_APPROVE,
    REVIEW_ACTION_REJECT,
    REVIEW_ACTION_REQUEST_INFO,
    REVIEW_ACTION_ESCALATE
}


def get_review_queue(
    status_filter: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
) -> List[Claim]:
    """
    Fetch claims that need manual reviewer attention.
    Default: claims in Manual Review or Under Evaluation or Submitted status.
    """
    reviewable_statuses = [
        CLAIM_STATUS_MANUAL_REVIEW,
        CLAIM_STATUS_UNDER_EVALUATION,
        CLAIM_STATUS_SUBMITTED
    ]

    if status_filter and status_filter in reviewable_statuses:
        query = Claim.query.filter_by(claim_status=status_filter)
    else:
        query = Claim.query.filter(Claim.claim_status.in_(reviewable_statuses))

    return query.order_by(Claim.submission_date.asc()).offset(offset).limit(limit).all()


def get_claim_review_summary(claim: Claim) -> Dict[str, Any]:
    """
    Build a comprehensive review summary for a claim including rule results,
    predictions, documents, and product/warranty details.
    """
    rule_results = [rr.to_dict() for rr in (claim.rule_results or [])]
    predictions = [p.to_dict() for p in (claim.predictions or [])]
    documents = [d.to_dict() for d in (claim.documents or [])]

    product = claim.product
    warranty = claim.warranty

    product_info = product.to_dict() if product else {}
    warranty_info = warranty.to_dict() if warranty else {}

    latest_prediction = None
    if predictions:
        latest_prediction = sorted(predictions, key=lambda p: p.get("id", 0), reverse=True)[0]

    pass_count = sum(1 for r in rule_results if r.get("rule_status") == "Passed")
    fail_count = sum(1 for r in rule_results if r.get("rule_status") == "Failed")
    warn_count = sum(1 for r in rule_results if r.get("rule_status") == "Warning")

    return {
        "claim": claim.to_dict(),
        "product": product_info,
        "warranty": warranty_info,
        "rule_results": rule_results,
        "rule_summary": {
            "total": len(rule_results),
            "passed": pass_count,
            "failed": fail_count,
            "warnings": warn_count
        },
        "predictions": predictions,
        "latest_prediction": latest_prediction,
        "documents": documents,
        "documents_count": len(documents)
    }


def apply_reviewer_decision(
    claim: Claim,
    action: str,
    reviewer_id: int,
    reviewer_notes: Optional[str] = None
) -> Dict[str, Any]:
    """
    Apply a manual reviewer decision to a claim.

    Args:
        claim: Claim model instance.
        action: One of 'approve', 'reject', 'request_info', 'escalate'.
        reviewer_id: User ID of the reviewer.
        reviewer_notes: Optional reviewer justification notes.

    Returns:
        Result dict with success flag and updated claim data.
    """
    if action not in VALID_REVIEW_ACTIONS:
        return {
            "success": False,
            "error": f"Invalid action '{action}'. Must be one of: {', '.join(VALID_REVIEW_ACTIONS)}"
        }

    if claim.claim_status == CLAIM_STATUS_CLOSED:
        return {
            "success": False,
            "error": "Cannot modify a closed claim."
        }

    old_status = claim.claim_status
    notes_snippet = (reviewer_notes or "")[:500]

    if action == REVIEW_ACTION_APPROVE:
        claim.claim_status = CLAIM_STATUS_APPROVED
        claim.final_decision = "Approved"
        notification_msg = f"Your claim {claim.claim_uid} has been approved by our review team."
        audit_action = "REVIEWER_APPROVED"

    elif action == REVIEW_ACTION_REJECT:
        claim.claim_status = CLAIM_STATUS_REJECTED
        claim.final_decision = "Rejected"
        notification_msg = (
            f"Your claim {claim.claim_uid} has been rejected. "
            f"Reason: {notes_snippet or 'See claim details.'}"
        )
        audit_action = "REVIEWER_REJECTED"

    elif action == REVIEW_ACTION_REQUEST_INFO:
        claim.claim_status = CLAIM_STATUS_ADDITIONAL_INFO
        claim.final_decision = None
        notification_msg = (
            f"Additional information is required for your claim {claim.claim_uid}. "
            f"{notes_snippet or 'Please check your claim for details.'}"
        )
        audit_action = "REVIEWER_REQUESTED_INFO"

    elif action == REVIEW_ACTION_ESCALATE:
        claim.claim_status = CLAIM_STATUS_MANUAL_REVIEW
        claim.final_decision = "Manual Review"
        notification_msg = f"Your claim {claim.claim_uid} has been escalated for further review."
        audit_action = "REVIEWER_ESCALATED"

    if notes_snippet:
        claim.reviewer_notes = notes_snippet
    claim.updated_at = utc_now()

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error("Failed to apply reviewer decision for %s: %s", claim.claim_uid, e)
        return {"success": False, "error": str(e)}

    # Send notification to claim owner
    try:
        notif = Notification(
            user_id=claim.user_id,
            title=f"Claim Update: {claim.claim_uid}",
            message=notification_msg,
            notification_type="Info"
        )
        db.session.add(notif)
        db.session.commit()
    except Exception as e:
        logger.warning("Notification creation failed for claim %s: %s", claim.claim_uid, e)

    log_audit_event(
        action=audit_action,
        entity_type="Claim",
        entity_id=claim.claim_uid,
        user_id=reviewer_id,
        description=(
            f"Reviewer action '{action}' on claim {claim.claim_uid}. "
            f"Status: {old_status} → {claim.claim_status}. "
            f"Notes: {notes_snippet[:150] or 'None'}"
        )
    )

    return {
        "success": True,
        "action": action,
        "old_status": old_status,
        "new_status": claim.claim_status,
        "final_decision": claim.final_decision,
        "claim": claim.to_dict()
    }


def get_reviewer_stats(reviewer_id: Optional[int] = None) -> Dict[str, Any]:
    """Get review queue statistics."""
    from sqlalchemy import func

    total_submitted = Claim.query.filter_by(claim_status=CLAIM_STATUS_SUBMITTED).count()
    total_manual_review = Claim.query.filter_by(claim_status=CLAIM_STATUS_MANUAL_REVIEW).count()
    total_under_eval = Claim.query.filter_by(claim_status=CLAIM_STATUS_UNDER_EVALUATION).count()
    total_approved = Claim.query.filter_by(claim_status=CLAIM_STATUS_APPROVED).count()
    total_rejected = Claim.query.filter_by(claim_status=CLAIM_STATUS_REJECTED).count()
    total_additional_info = Claim.query.filter_by(claim_status=CLAIM_STATUS_ADDITIONAL_INFO).count()

    pending_review = total_submitted + total_manual_review + total_under_eval

    return {
        "pending_review": pending_review,
        "submitted": total_submitted,
        "manual_review": total_manual_review,
        "under_evaluation": total_under_eval,
        "approved": total_approved,
        "rejected": total_rejected,
        "additional_info_required": total_additional_info,
        "total_decided": total_approved + total_rejected
    }
