"""
AssureX Claim Reviewer Routes Blueprint
Full reviewer workflow: queue management, claim evaluation, approve/reject/escalate,
model comparison, and manual review decision forms.
"""

from flask import Blueprint, jsonify, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from backend.extensions import db
from backend.models.claim import Claim, CLAIM_STATUS_MANUAL_REVIEW
from backend.services.reviewer_service import (
    get_review_queue,
    get_claim_review_summary,
    apply_reviewer_decision,
    get_reviewer_stats,
    VALID_REVIEW_ACTIONS
)
from backend.services.final_decision import run_full_claim_evaluation
from backend.services.model_comparison import compare_models_for_claim
from backend.services.duplicate_claim_detection import check_duplicate_and_flag
from backend.utils.helpers import is_api_request
from backend.utils.security import (
    ROLE_ADMIN,
    ROLE_REVIEWER,
    reviewer_required,
    role_required
)

reviewer_bp = Blueprint("reviewer", __name__, url_prefix="/reviewer")


@reviewer_bp.route("/status", methods=["GET"])
@login_required
@reviewer_required
def reviewer_status():
    """Check reviewer service status."""
    stats = get_reviewer_stats()
    return jsonify({
        "module": "Claim Reviewer",
        "status": "active",
        "reviewer_uid": current_user.user_uid,
        "queue_stats": stats
    }), 200


@reviewer_bp.route("/dashboard", methods=["GET"])
@login_required
@reviewer_required
def dashboard():
    """Render reviewer dashboard with queue and statistics."""
    stats = get_reviewer_stats()
    queue = get_review_queue(limit=20)
    return render_template(
        "reviewer_dashboard.html",
        user=current_user,
        stats=stats,
        queue=queue
    )


@reviewer_bp.route("/claims", methods=["GET"])
@login_required
@reviewer_required
def get_review_queue_view():
    """
    Get claims available for reviewer inspection.
    Supports ?status= filter and pagination via ?page= and ?per_page=.
    """
    status_filter = request.args.get("status")
    page = max(1, int(request.args.get("page", 1)))
    per_page = min(50, max(5, int(request.args.get("per_page", 20))))
    offset = (page - 1) * per_page

    claims = get_review_queue(
        status_filter=status_filter,
        limit=per_page,
        offset=offset
    )

    if is_api_request():
        return jsonify({
            "success": True,
            "count": len(claims),
            "page": page,
            "per_page": per_page,
            "claims": [c.to_dict() for c in claims]
        }), 200

    return render_template(
        "reviewer_dashboard.html",
        user=current_user,
        claims=claims,
        stats=get_reviewer_stats()
    )


@reviewer_bp.route("/claims/<int:claim_id>", methods=["GET"])
@login_required
@reviewer_required
def get_claim_for_review(claim_id: int):
    """Get comprehensive review summary for a specific claim."""
    claim = db.session.get(Claim, claim_id)
    if not claim:
        if is_api_request():
            return jsonify({"success": False, "message": "Claim not found."}), 404
        flash("Claim not found.", "error")
        return redirect(url_for("reviewer.dashboard"))

    summary = get_claim_review_summary(claim)

    if is_api_request():
        return jsonify({"success": True, **summary}), 200

    return render_template(
        "review_claim.html",
        user=current_user,
        claim=claim,
        summary=summary
    )


@reviewer_bp.route("/claims/<int:claim_id>/evaluate", methods=["POST"])
@login_required
@reviewer_required
def evaluate_claim(claim_id: int):
    """
    Run full automated evaluation (rules + AI) for a claim.
    Updates claim status and persists results.
    """
    claim = db.session.get(Claim, claim_id)
    if not claim:
        return jsonify({"success": False, "message": "Claim not found."}), 404

    result = run_full_claim_evaluation(claim, reviewer_id=current_user.id)

    if is_api_request():
        return jsonify(result), 200 if result.get("success") else 500

    if result.get("success"):
        flash(
            f"Evaluation complete: {result.get('final_decision', 'Unknown')}. "
            f"{result.get('reasoning', '')[:200]}",
            "success"
        )
    else:
        flash(f"Evaluation failed: {result.get('error', 'Unknown error')}", "error")

    return redirect(url_for("reviewer.get_claim_for_review", claim_id=claim_id))


@reviewer_bp.route("/claims/<int:claim_id>/decide", methods=["POST"])
@login_required
@reviewer_required
def apply_decision(claim_id: int):
    """
    Apply a manual reviewer decision: approve, reject, request_info, or escalate.
    Accepts JSON or form data.
    """
    claim = db.session.get(Claim, claim_id)
    if not claim:
        if is_api_request():
            return jsonify({"success": False, "message": "Claim not found."}), 404
        flash("Claim not found.", "error")
        return redirect(url_for("reviewer.dashboard"))

    data = request.get_json() if request.is_json else request.form
    action = (data.get("action") or "").strip().lower()
    reviewer_notes = (data.get("notes") or data.get("reviewer_notes") or "").strip()

    if not action or action not in VALID_REVIEW_ACTIONS:
        msg = f"Invalid action. Must be one of: {', '.join(VALID_REVIEW_ACTIONS)}"
        if is_api_request():
            return jsonify({"success": False, "message": msg}), 400
        flash(msg, "error")
        return redirect(url_for("reviewer.get_claim_for_review", claim_id=claim_id))

    result = apply_reviewer_decision(
        claim=claim,
        action=action,
        reviewer_id=current_user.id,
        reviewer_notes=reviewer_notes
    )

    if result.get("success"):
        # Notify customer of reviewer's manual decision
        try:
            from backend.services.notification_service import notify_reviewer_decision
            notify_reviewer_decision(claim, reviewer_name=current_user.name, notes=reviewer_notes)
        except Exception:
            pass

    if is_api_request():
        return jsonify(result), 200 if result.get("success") else 400

    if result.get("success"):
        action_labels = {
            "approve": "approved",
            "reject": "rejected",
            "request_info": "flagged for additional information",
            "escalate": "escalated for further review"
        }
        flash(f"Claim {claim.claim_uid} has been {action_labels.get(action, action)}.", "success")
    else:
        flash(f"Decision failed: {result.get('error', 'Unknown error')}", "error")

    return redirect(url_for("reviewer.get_claim_for_review", claim_id=claim_id))


@reviewer_bp.route("/claims/<int:claim_id>/compare-models", methods=["GET", "POST"])
@login_required
@reviewer_required
def compare_models(claim_id: int):
    """Run and display side-by-side comparison of Python model vs Teachable Machine."""
    claim = db.session.get(Claim, claim_id)
    if not claim:
        return jsonify({"success": False, "message": "Claim not found."}), 404

    comparison = compare_models_for_claim(claim)

    if is_api_request():
        return jsonify({"success": True, "comparison": comparison}), 200

    return render_template(
        "review_claim.html",
        user=current_user,
        claim=claim,
        comparison=comparison,
        summary=get_claim_review_summary(claim)
    )


@reviewer_bp.route("/claims/<int:claim_id>/duplicates", methods=["GET"])
@login_required
@reviewer_required
def check_duplicates(claim_id: int):
    """Check for potential duplicate claims."""
    claim = db.session.get(Claim, claim_id)
    if not claim:
        return jsonify({"success": False, "message": "Claim not found."}), 404

    dup_result = check_duplicate_and_flag(claim)
    return jsonify({"success": True, **dup_result}), 200


@reviewer_bp.route("/stats", methods=["GET"])
@login_required
@reviewer_required
def stats():
    """Get reviewer queue statistics."""
    return jsonify(get_reviewer_stats()), 200


@reviewer_bp.route("/claims/<int:claim_id>/manual-review", methods=["GET"])
@login_required
@reviewer_required
def manual_review_form(claim_id: int):
    """Render the manual review form for a specific claim."""
    claim = db.session.get(Claim, claim_id)
    if not claim:
        flash("Claim not found.", "error")
        return redirect(url_for("reviewer.dashboard"))

    summary = get_claim_review_summary(claim)
    return render_template(
        "manual_review.html",
        user=current_user,
        claim=claim,
        summary=summary
    )
