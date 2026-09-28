"""
AssureX Warranty Routes Blueprint
Handles customer warranty listing, detailed warranty certificate view,
dynamic policy status computation, IDOR ownership enforcement, and administrator warranty extensions.
"""

from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from flask import (
    Blueprint,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for
)
from flask_login import current_user, login_required
from backend.extensions import db
from backend.models.product import Product
from backend.models.warranty import (
    Warranty,
    WARRANTY_ACTIVE,
    WARRANTY_EXPIRED,
    WARRANTY_EXTENDED,
    WARRANTY_NEARING_EXPIRY
)
from backend.services.audit_service import log_audit_event
from backend.utils.helpers import is_api_request
from backend.utils.security import (
    ROLE_ADMIN,
    ROLE_CUSTOMER,
    ROLE_REVIEWER,
    ROLE_SERVICE_CENTER,
    admin_required,
    check_resource_ownership
)

warranty_bp = Blueprint("warranties", __name__)


@warranty_bp.route("/api/warranties/status", methods=["GET"])
@login_required
def warranty_status():
    """Check warranties service status."""
    return jsonify({
        "module": "Warranties",
        "status": "ready",
        "user": current_user.user_uid,
        "role": current_user.role
    }), 200


@warranty_bp.route("/api/warranties", methods=["GET"])
@warranty_bp.route("/warranties", methods=["GET"])
@login_required
def list_warranties():
    """
    List warranties associated with products.
    - Customers strictly view only warranties of their own registered products (prevents IDOR).
    - Staff & Administrators can view all system warranties with optional filtering.
    """
    status_filter = request.args.get("status", "").strip()
    search_query = request.args.get("q", "").strip().lower()

    if current_user.role == ROLE_CUSTOMER:
        query = (
            Warranty.query.join(Product)
            .filter(Product.user_id == current_user.id)
            .order_by(Warranty.created_at.desc())
        )
    else:
        query = Warranty.query.join(Product).order_by(Warranty.created_at.desc())

    all_warranties = query.all()

    # Dynamically update status and apply in-memory filters if specified
    filtered_warranties = []
    for w in all_warranties:
        dyn_status = w.calculate_status()
        w.warranty_status = dyn_status

        if status_filter and status_filter.lower() != "all":
            if dyn_status.lower() != status_filter.lower():
                continue

        if search_query:
            prod_name = (w.product.product_name or "").lower() if w.product else ""
            serial = (w.product.serial_number or "").lower() if w.product else ""
            brand = (w.product.brand or "").lower() if w.product else ""
            w_uid = (w.warranty_uid or "").lower()
            if not (search_query in prod_name or search_query in serial or search_query in brand or search_query in w_uid):
                continue

        filtered_warranties.append(w)

    if is_api_request():
        return jsonify({
            "success": True,
            "count": len(filtered_warranties),
            "warranties": [w.to_dict() for w in filtered_warranties]
        }), 200

    return render_template(
        "warranty.html",
        warranties=filtered_warranties,
        user=current_user,
        current_status=status_filter,
        search_query=search_query
    )


@warranty_bp.route("/api/warranties/<int:warranty_id>", methods=["GET"])
@warranty_bp.route("/warranties/<int:warranty_id>", methods=["GET"])
@login_required
def get_warranty(warranty_id: int):
    """
    Get warranty certificate and policy details.
    Enforces strict IDOR ownership checks: Customers cannot access other customers' warranties.
    """
    warranty = db.session.get(Warranty, warranty_id)
    if not warranty:
        if is_api_request():
            return jsonify({"success": False, "message": "Warranty not found."}), 404
        flash("Warranty policy record not found.", "error")
        return redirect(url_for("warranties.list_warranties"))

    owner_id = warranty.product.user_id if warranty.product else None
    if owner_id and not check_resource_ownership(owner_id):
        if is_api_request():
            return jsonify({
                "success": False,
                "error": "Forbidden",
                "message": "Access forbidden: You do not have permission to access this warranty."
            }), 403
        flash("Access forbidden: You do not have permission to access this warranty.", "error")
        return redirect(url_for("warranties.list_warranties"))

    # Dynamically update status
    warranty.warranty_status = warranty.calculate_status()

    if is_api_request():
        data = warranty.to_dict()
        if warranty.product:
            data["product"] = warranty.product.to_dict()
        return jsonify({
            "success": True,
            "warranty": data
        }), 200

    return render_template(
        "warranty_detail.html",
        warranty=warranty,
        product=warranty.product,
        user=current_user
    )


@warranty_bp.route("/api/warranties/by-uid/<string:warranty_uid>", methods=["GET"])
@warranty_bp.route("/warranties/by-uid/<string:warranty_uid>", methods=["GET"])
@login_required
def get_warranty_by_uid(warranty_uid: str):
    """
    Retrieve warranty by public UID (e.g. WAR-XXXXXXXX) with IDOR protection.
    """
    warranty = Warranty.query.filter_by(warranty_uid=warranty_uid.strip().upper()).first()
    if not warranty:
        if is_api_request():
            return jsonify({"success": False, "message": "Warranty not found."}), 404
        flash("Warranty policy record not found.", "error")
        return redirect(url_for("warranties.list_warranties"))

    owner_id = warranty.product.user_id if warranty.product else None
    if owner_id and not check_resource_ownership(owner_id):
        if is_api_request():
            return jsonify({
                "success": False,
                "error": "Forbidden",
                "message": "Access forbidden: You do not have permission to access this warranty."
            }), 403
        flash("Access forbidden: You do not have permission to access this warranty.", "error")
        return redirect(url_for("warranties.list_warranties"))

    warranty.warranty_status = warranty.calculate_status()

    if is_api_request():
        data = warranty.to_dict()
        if warranty.product:
            data["product"] = warranty.product.to_dict()
        return jsonify({
            "success": True,
            "warranty": data
        }), 200

    return redirect(url_for("warranties.get_warranty", warranty_id=warranty.id))


@warranty_bp.route("/api/warranties/<int:warranty_id>/extend", methods=["POST"])
@warranty_bp.route("/warranties/<int:warranty_id>/extend", methods=["POST"])
@login_required
@admin_required
def extend_warranty(warranty_id: int):
    """
    Administrator-authorized warranty policy extension.
    Accepts extension duration (in months) and policy details, extends expiry date,
    and logs an audit event. Customers cannot directly modify warranty terms.
    """
    warranty = db.session.get(Warranty, warranty_id)
    if not warranty:
        if is_api_request():
            return jsonify({"success": False, "message": "Warranty not found."}), 404
        flash("Warranty record not found.", "error")
        return redirect(url_for("warranties.list_warranties"))

    data = request.get_json() if request.is_json else request.form
    try:
        duration_months = int(data.get("duration_months", 12))
    except (ValueError, TypeError):
        duration_months = 12

    if duration_months <= 0 or duration_months > 60:
        msg = "Extension duration must be between 1 and 60 months."
        if is_api_request():
            return jsonify({"success": False, "message": msg}), 400
        flash(msg, "error")
        return redirect(url_for("warranties.get_warranty", warranty_id=warranty.id))

    details = (data.get("details") or "").strip() or f"Extended by {duration_months} months by Administrator {current_user.user_uid}"

    # Calculate new expiry date
    old_expiry = warranty.expiry_date
    try:
        new_expiry = old_expiry + relativedelta(months=duration_months)
    except Exception:
        new_expiry = old_expiry + timedelta(days=int(duration_months * 30.4375))

    warranty.expiry_date = new_expiry
    warranty.is_extended = True
    warranty.extended_details = details
    warranty.warranty_status = warranty.calculate_status()

    db.session.commit()

    log_audit_event(
        action="WARRANTY_EXTENDED",
        entity_type="Warranty",
        entity_id=warranty.warranty_uid,
        user_id=current_user.id,
        description=f"Administrator {current_user.user_uid} extended warranty {warranty.warranty_uid} by {duration_months} months to {new_expiry.isoformat()}"
    )

    if is_api_request():
        return jsonify({
            "success": True,
            "message": f"Warranty {warranty.warranty_uid} extended by {duration_months} months.",
            "warranty": warranty.to_dict()
        }), 200

    flash(f"Warranty {warranty.warranty_uid} successfully extended to {new_expiry.strftime('%B %d, %Y')}.", "success")
    return redirect(url_for("warranties.get_warranty", warranty_id=warranty.id))
