"""
AssureX Service Center Routes Blueprint
Handles authorized service-centre portal, technician repairs, and diagnostics.
"""

from flask import Blueprint, jsonify, render_template
from flask_login import login_required, current_user
from backend.models.claim import Claim
from backend.extensions import db
from backend.utils.security import service_center_required

service_center_bp = Blueprint("service_center", __name__, url_prefix="/service-center")


@service_center_bp.route("/status", methods=["GET"])
@login_required
@service_center_required
def service_center_status():
    """Check service center module status."""
    return jsonify({
        "module": "Service Center",
        "status": "active",
        "technician_uid": current_user.user_uid
    }), 200


@service_center_bp.route("/dashboard", methods=["GET"])
@login_required
@service_center_required
def dashboard():
    """Render service center dashboard with approved claims and repair stats."""
    approved_claims = Claim.query.filter_by(claim_status="Approved").order_by(Claim.created_at.desc()).all()
    under_repair = Claim.query.filter_by(claim_status="Under Repair").count()
    completed_repairs = Claim.query.filter_by(claim_status="Repair Completed").count()
    total_approved = len(approved_claims)

    return render_template(
        "service_dashboard.html",
        user=current_user,
        approved_claims=approved_claims,
        under_repair=under_repair,
        completed_repairs=completed_repairs,
        total_approved=total_approved
    )
