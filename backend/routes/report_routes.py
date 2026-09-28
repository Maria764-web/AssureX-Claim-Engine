"""
AssureX Report & Analytics Routes Blueprint
Restricted to Staff (Reviewers, Service Center, Administrators).
Provides claim reports, model analytics, and system overview data.
"""

import csv
import io
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

from flask import Blueprint, jsonify, render_template, request, make_response
from flask_login import login_required, current_user
from backend.extensions import db
from backend.models.claim import Claim
from backend.services.analytics_service import get_full_analytics_data, get_system_overview
from backend.services.report_service import (
    generate_claim_evaluation_report,
    generate_batch_report,
    generate_system_analytics_report,
    generate_claim_pdf
)
from backend.utils.security import (
    ROLE_ADMIN,
    ROLE_REVIEWER,
    ROLE_SERVICE_CENTER,
    role_required
)

report_bp = Blueprint("reports", __name__, url_prefix="/api/reports")


@report_bp.route("/status", methods=["GET"])
@login_required
@role_required(ROLE_REVIEWER, ROLE_ADMIN, ROLE_SERVICE_CENTER)
def report_status():
    """Check reports module status (Staff only)."""
    return jsonify({
        "module": "Reports & Analytics",
        "status": "active",
        "authorized_user": current_user.user_uid,
        "role": current_user.role
    }), 200


@report_bp.route("/analytics", methods=["GET"])
@login_required
@role_required(ROLE_REVIEWER, ROLE_ADMIN, ROLE_SERVICE_CENTER)
def get_analytics():
    """Return full analytics data for admin/reviewer dashboards."""
    data = get_full_analytics_data()
    return jsonify({"success": True, "analytics": data}), 200


@report_bp.route("/overview", methods=["GET"])
@login_required
@role_required(ROLE_REVIEWER, ROLE_ADMIN, ROLE_SERVICE_CENTER)
def get_overview():
    """Return system overview metrics."""
    overview = get_system_overview()
    return jsonify({"success": True, "overview": overview}), 200


@report_bp.route("/claims/<int:claim_id>", methods=["GET"])
@login_required
@role_required(ROLE_REVIEWER, ROLE_ADMIN, ROLE_SERVICE_CENTER)
def get_claim_report(claim_id: int):
    """Generate and return a full evaluation report for a specific claim."""
    claim = db.session.get(Claim, claim_id)
    if not claim:
        return jsonify({"success": False, "message": "Claim not found."}), 404

    report = generate_claim_evaluation_report(claim)
    return jsonify({"success": True, "report": report}), 200


@report_bp.route("/claims/batch", methods=["GET"])
@login_required
@role_required(ROLE_REVIEWER, ROLE_ADMIN)
def get_batch_report():
    """Generate a batch report for all claims (or filtered by status)."""
    status_filter = request.args.get("status")
    limit = min(500, max(1, int(request.args.get("limit", 100))))

    query = Claim.query
    if status_filter:
        query = query.filter_by(claim_status=status_filter)

    claims = query.order_by(Claim.submission_date.desc()).limit(limit).all()
    report = generate_batch_report(claims)
    return jsonify({"success": True, "report": report}), 200


@report_bp.route("/system", methods=["GET"])
@login_required
@role_required(ROLE_ADMIN)
def get_system_report():
    """Generate full system analytics report (Admin only)."""
    report = generate_system_analytics_report()
    return jsonify({"success": True, "report": report}), 200


@report_bp.route("/claims/<int:claim_id>/download", methods=["GET"])
@login_required
def download_claim_report(claim_id: int):
    """
    Download a printable HTML report for a claim.
    Customers can download their own claims; staff can download any.
    """
    from backend.utils.security import check_resource_ownership, ROLE_CUSTOMER

    claim = db.session.get(Claim, claim_id)
    if not claim:
        return jsonify({"success": False, "message": "Claim not found."}), 404

    if current_user.role == ROLE_CUSTOMER and not check_resource_ownership(claim.user_id):
        return jsonify({"success": False, "error": "Forbidden"}), 403

    report = generate_claim_evaluation_report(claim)
    html = render_template("report_print.html", claim=claim, report=report, generated_at=datetime.utcnow())
    response = make_response(html)
    response.headers["Content-Type"] = "text/html; charset=utf-8"
    response.headers["Content-Disposition"] = f'attachment; filename="AssureX_Report_{claim.claim_uid}.html"'
    return response


@report_bp.route("/claims/<int:claim_id>/download/pdf", methods=["GET"])
@login_required
def download_claim_report_pdf(claim_id: int):
    """
    Download a PDF claim evaluation report.
    Customers can download their own claims; staff can download any.
    """
    from backend.utils.security import check_resource_ownership, ROLE_CUSTOMER

    claim = db.session.get(Claim, claim_id)
    if not claim:
        return jsonify({"success": False, "message": "Claim not found."}), 404

    if current_user.role == ROLE_CUSTOMER and not check_resource_ownership(claim.user_id):
        return jsonify({"success": False, "error": "Forbidden"}), 403

    try:
        pdf_bytes = generate_claim_pdf(claim)
    except Exception as e:
        logger.error("PDF generation error for claim %s: %s", claim.claim_uid, e)
        return jsonify({"success": False, "message": "PDF generation failed.", "error": str(e)}), 500

    response = make_response(pdf_bytes)
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = (
        f'attachment; filename="AssureX_Report_{claim.claim_uid}.pdf"'
    )
    return response


@report_bp.route("/claims/export.csv", methods=["GET"])
@login_required
@role_required(ROLE_REVIEWER, ROLE_ADMIN)
def export_claims_csv():
    """Export all claims (or filtered) as a CSV file."""
    status_filter = request.args.get("status")
    limit = min(5000, max(1, int(request.args.get("limit", 1000))))

    query = Claim.query
    if status_filter:
        query = query.filter_by(claim_status=status_filter)
    claims = query.order_by(Claim.submission_date.desc()).limit(limit).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Claim UID", "Customer", "Email", "Product", "Damage Type",
        "Product Age (months)", "Fault Date", "Submission Date",
        "Claim Status", "Final Decision", "Documents", "Rules Failed",
        "AI Prediction", "AI Confidence"
    ])

    for c in claims:
        latest_pred = None
        if c.predictions:
            latest_pred = sorted(c.predictions, key=lambda p: p.id, reverse=True)[0]
        rules_failed = sum(1 for r in (c.rule_results or []) if r.rule_status == "Failed")
        writer.writerow([
            c.claim_uid,
            c.customer.name if c.customer else "",
            c.customer.email if c.customer else "",
            f"{c.product.brand} {c.product.model}" if c.product else "",
            c.damage_type or "",
            c.product_age or "",
            c.fault_date.isoformat() if c.fault_date else "",
            c.submission_date.isoformat() if c.submission_date else "",
            c.claim_status,
            c.final_decision or "",
            len(c.documents or []),
            rules_failed,
            latest_pred.predicted_class if latest_pred else "",
            f"{(latest_pred.valid_confidence or 0)*100:.1f}%" if latest_pred else ""
        ])

    csv_data = output.getvalue()
    output.close()

    response = make_response(csv_data)
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = f'attachment; filename="AssureX_Claims_{datetime.utcnow().strftime("%Y%m%d")}.csv"'
    return response


@report_bp.route("/analytics/export.csv", methods=["GET"])
@login_required
@role_required(ROLE_REVIEWER, ROLE_ADMIN)
def export_analytics_csv():
    """Export analytics summary as a CSV file."""
    from backend.services.analytics_service import (
        get_system_overview, get_claim_status_distribution,
        get_decision_distribution, get_damage_type_breakdown
    )

    output = io.StringIO()
    writer = csv.writer(output)

    # Overview section
    writer.writerow(["AssureX System Analytics Export", datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")])
    writer.writerow([])

    overview = get_system_overview()
    writer.writerow(["SYSTEM OVERVIEW"])
    writer.writerow(["Metric", "Value"])
    writer.writerow(["Total Users", overview["users"]["total"]])
    writer.writerow(["Customers", overview["users"]["customers"]])
    writer.writerow(["Staff", overview["users"]["staff"]])
    writer.writerow(["Total Products", overview["products"]])
    writer.writerow(["Total Warranties", overview["warranties"]])
    writer.writerow(["Total Claims", overview["claims"]["total"]])
    writer.writerow(["Pending Claims", overview["claims"]["pending"]])
    writer.writerow(["Approved Claims", overview["claims"]["approved"]])
    writer.writerow(["Rejected Claims", overview["claims"]["rejected"]])
    writer.writerow(["Manual Review", overview["claims"]["manual_review"]])
    writer.writerow(["Approval Rate", f"{overview['claims']['approval_rate']}%"])
    writer.writerow(["Rejection Rate", f"{overview['claims']['rejection_rate']}%"])
    writer.writerow([])

    writer.writerow(["CLAIM STATUS DISTRIBUTION"])
    writer.writerow(["Status", "Count"])
    for status, count in get_claim_status_distribution().items():
        writer.writerow([status, count])
    writer.writerow([])

    writer.writerow(["FINAL DECISION DISTRIBUTION"])
    writer.writerow(["Decision", "Count"])
    for decision, count in get_decision_distribution().items():
        writer.writerow([decision, count])
    writer.writerow([])

    writer.writerow(["DAMAGE TYPE BREAKDOWN (Top 15)"])
    writer.writerow(["Damage Type", "Claim Count"])
    for row in get_damage_type_breakdown():
        writer.writerow([row["damage_type"], row["count"]])

    csv_data = output.getvalue()
    output.close()

    response = make_response(csv_data)
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = f'attachment; filename="AssureX_Analytics_{datetime.utcnow().strftime("%Y%m%d")}.csv"'
    return response
