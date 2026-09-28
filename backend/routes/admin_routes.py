"""
AssureX Admin Routes Blueprint
Handles administrator dashboard, system users overview, and authorized role assignment.
"""

from flask import Blueprint, jsonify, render_template, request
from flask_login import login_required, current_user
from sqlalchemy import func, or_
from backend.extensions import db
from backend.models.user import User
from backend.models.claim import Claim
from backend.services.audit_service import log_audit_event
from backend.utils.helpers import is_api_request
from backend.utils.security import (
    ROLE_ADMIN,
    VALID_ROLES,
    admin_required,
    validate_password_strength
)
from backend.utils.validators import validate_email, validate_phone

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/status", methods=["GET"])
@login_required
@admin_required
def admin_status():
    """Check admin module status."""
    return jsonify({
        "module": "Administrator",
        "status": "active",
        "admin_user": current_user.user_uid
    }), 200


@admin_bp.route("/dashboard", methods=["GET"])
@login_required
@admin_required
def dashboard():
    """Render administrator dashboard with live system metrics and staff management."""
    users = User.query.order_by(User.created_at.desc()).all()
    total_users = len(users)
    customers_count = sum(1 for u in users if u.role == "Customer")
    service_count = sum(1 for u in users if u.role == "Service-Centre Employee")
    reviewers_count = sum(1 for u in users if u.role == "Claim Reviewer")
    admins_count = sum(1 for u in users if u.role == "Administrator")

    claims_total = Claim.query.count()
    claims_pending = Claim.query.filter(Claim.claim_status.in_(["Submitted", "Under Evaluation"])).count()
    claims_approved = Claim.query.filter_by(claim_status="Approved").count()
    claims_rejected = Claim.query.filter_by(claim_status="Rejected").count()
    claims_manual = Claim.query.filter_by(claim_status="Manual Review").count()
    recent_claims = Claim.query.order_by(Claim.created_at.desc()).limit(8).all()

    return render_template(
        "admin-dashboard.html",
        user=current_user,
        users=users,
        total_users=total_users,
        customers_count=customers_count,
        service_count=service_count,
        reviewers_count=reviewers_count,
        admins_count=admins_count,
        claims_total=claims_total,
        claims_pending=claims_pending,
        claims_approved=claims_approved,
        claims_rejected=claims_rejected,
        claims_manual=claims_manual,
        recent_claims=recent_claims
    )


@admin_bp.route("/users", methods=["GET"])
@login_required
@admin_required
def list_users():
    """List all registered system users."""
    users = User.query.order_by(User.created_at.desc()).all()
    return jsonify({
        "success": True,
        "count": len(users),
        "users": [u.to_dict() for u in users]
    }), 200


@admin_bp.route("/users", methods=["POST"])
@login_required
@admin_required
def create_privileged_user():
    """
    Authorized mechanism for administrators to create internal/privileged staff accounts:
    - Administrator
    - Claim Reviewer
    - Service-Centre Employee
    - Customer
    """
    from flask import flash, redirect, url_for

    data = request.get_json() if request.is_json else request.form
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip()
    phone = (data.get("phone") or "").strip()
    password = data.get("password") or ""
    role = (data.get("role") or "").strip()

    errors = []
    if not name or len(name) < 2:
        errors.append("Valid full name is required.")
    if not email or not validate_email(email):
        errors.append("Valid email is required.")
    elif User.query.filter(func.lower(User.email) == email.lower()).first():
        errors.append("An account with this email already exists.")

    if not role or role not in VALID_ROLES:
        errors.append(f"Invalid role. Must be one of: {', '.join(sorted(VALID_ROLES))}")

    is_strong, strength_msg = validate_password_strength(password)
    if not is_strong:
        errors.append(strength_msg)

    if phone and not validate_phone(phone):
        errors.append("Invalid phone format.")

    if errors:
        if is_api_request():
            return jsonify({"success": False, "errors": errors}), 400
        for err in errors:
            flash(err, "error")
        return redirect(url_for("admin.dashboard"))

    new_user = User(
        name=name,
        email=email.lower(),
        phone=phone if phone else None,
        role=role,
        password=password,
        is_active=True
    )
    db.session.add(new_user)
    db.session.commit()

    log_audit_event(
        action="ADMIN_CREATE_USER",
        entity_type="User",
        entity_id=new_user.user_uid,
        user_id=new_user.id,
        description=f"Admin {current_user.user_uid} created user {new_user.email} with role {role}"
    )

    if is_api_request():
        return jsonify({
            "success": True,
            "message": f"User {new_user.email} created with role {role}.",
            "user": new_user.to_dict()
        }), 201

    flash(f"User {new_user.email} ({role}) created successfully.", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/users/<int:user_id>/role", methods=["PUT", "POST"])
@login_required
@admin_required
def update_user_role(user_id: int):
    """Authorized mechanism for administrators to change a user's role."""
    target_user = db.session.get(User, user_id)
    if not target_user:
        return jsonify({"success": False, "message": "User not found."}), 404

    data = request.get_json() if request.is_json else request.form
    new_role = (data.get("role") or "").strip()

    if new_role not in VALID_ROLES:
        return jsonify({"success": False, "message": f"Invalid role. Must be one of: {', '.join(VALID_ROLES)}"}), 400

    old_role = target_user.role
    target_user.role = new_role
    db.session.commit()

    log_audit_event(
        action="ADMIN_UPDATE_ROLE",
        entity_type="User",
        entity_id=target_user.user_uid,
        description=f"Admin {current_user.user_uid} changed user role from {old_role} to {new_role}"
    )

    return jsonify({
        "success": True,
        "message": f"Role for {target_user.email} updated to {new_role}.",
        "user": target_user.to_dict()
    }), 200


@admin_bp.route("/claims", methods=["GET"])
@login_required
@admin_required
def all_claims_view():
    """Render admin claims management page with all claims."""
    status_filter = request.args.get("status")
    q = request.args.get("q", "").strip()

    query = Claim.query
    if status_filter:
        query = query.filter_by(claim_status=status_filter)
    if q:
        query = query.filter(Claim.claim_uid.ilike(f"%{q}%"))

    claims = query.order_by(Claim.created_at.desc()).all()
    status_counts = {
        "total": Claim.query.count(),
        "pending": Claim.query.filter(Claim.claim_status.in_(["Submitted", "Under Evaluation"])).count(),
        "approved": Claim.query.filter_by(claim_status="Approved").count(),
        "rejected": Claim.query.filter_by(claim_status="Rejected").count(),
        "manual": Claim.query.filter_by(claim_status="Manual Review").count(),
    }
    return render_template(
        "admin_claims.html",
        user=current_user,
        claims=claims,
        status_counts=status_counts,
        status_filter=status_filter,
        q=q
    )


@admin_bp.route("/analytics", methods=["GET"])
@login_required
@admin_required
def analytics_dashboard():
    """Render admin analytics dashboard with live system data."""
    from backend.services.analytics_service import get_full_analytics_data
    analytics = get_full_analytics_data()
    return render_template(
        "admin_analytics.html",
        user=current_user,
        analytics=analytics
    )


@admin_bp.route("/monitoring", methods=["GET"])
@login_required
@admin_required
def system_monitoring():
    """System monitoring dashboard with anomaly detection."""
    from backend.services.anomaly_service import run_all_checks
    monitoring = run_all_checks()
    return render_template("admin_monitoring.html", user=current_user, monitoring=monitoring)


@admin_bp.route("/api/monitoring", methods=["GET"])
@login_required
@admin_required
def monitoring_api():
    """JSON endpoint for live monitoring data (used by auto-refresh)."""
    from backend.services.anomaly_service import run_all_checks
    return jsonify(run_all_checks()), 200


@admin_bp.route("/policies", methods=["GET"])
@login_required
@admin_required
def warranty_policies():
    """View and manage configurable warranty policies."""
    from backend.services.warranty_policy_service import get_all_policies
    policies = get_all_policies()
    return render_template(
        "admin_policies.html",
        user=current_user,
        policies=policies
    )


@admin_bp.route("/audit", methods=["GET"])
@login_required
@admin_required
def audit_log_view():
    """View system audit trail logs."""
    from backend.models.audit_log import AuditLog
    page = request.args.get("page", 1, type=int)
    per_page = 50
    q = request.args.get("q", "").strip()

    query = AuditLog.query
    if q:
        query = query.filter(
            or_(
                AuditLog.action.ilike(f"%{q}%"),
                AuditLog.entity_id.ilike(f"%{q}%"),
                AuditLog.description.ilike(f"%{q}%")
            )
        )
    logs = query.order_by(AuditLog.timestamp.desc()).limit(per_page * page).all()
    return render_template("admin_audit.html", user=current_user, logs=logs, q=q)


@admin_bp.route("/users/<int:user_id>/deactivate", methods=["POST"])
@login_required
@admin_required
def deactivate_user(user_id: int):
    """Deactivate a user account (Admin only)."""
    target_user = db.session.get(User, user_id)
    if not target_user:
        return jsonify({"success": False, "message": "User not found."}), 404

    if target_user.id == current_user.id:
        return jsonify({"success": False, "message": "Cannot deactivate your own account."}), 400

    target_user.is_active = False
    db.session.commit()

    log_audit_event(
        action="ADMIN_DEACTIVATE_USER",
        entity_type="User",
        entity_id=target_user.user_uid,
        description=f"Admin {current_user.user_uid} deactivated user {target_user.email}"
    )

    if request.is_json:
        return jsonify({"success": True, "message": f"User {target_user.email} deactivated."}), 200

    from flask import flash, redirect, url_for
    flash(f"User {target_user.email} has been deactivated.", "success")
    return redirect(url_for("admin.dashboard"))
