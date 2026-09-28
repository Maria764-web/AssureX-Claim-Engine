"""
AssureX Repair History Routes Blueprint
Handles repair history endpoints with authentication and role access controls.
"""

from datetime import date

from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from backend.extensions import db
from backend.models.repair_history import RepairHistory
from backend.models.claim import Claim
from backend.models.product import Product
from backend.utils.security import (
    ROLE_SERVICE_CENTER, ROLE_REVIEWER, ROLE_ADMIN,
    check_resource_ownership, role_required
)
from backend.services.audit_service import log_audit_event

repair_bp = Blueprint("repairs", __name__, url_prefix="/api/repairs")


@repair_bp.route("/status", methods=["GET"])
@login_required
def repair_status():
    """Check repairs service status."""
    return jsonify({
        "module": "Repairs",
        "status": "ready",
        "user": current_user.user_uid
    }), 200


@repair_bp.route("/<int:repair_id>", methods=["GET"])
@login_required
def get_repair(repair_id: int):
    """
    Get repair record with IDOR checks.
    """
    repair = RepairHistory.query.get(repair_id)
    if not repair:
        return jsonify({"success": False, "message": "Repair record not found."}), 404

    owner_id = repair.product.user_id if repair.product else None
    if owner_id and not check_resource_ownership(owner_id):
        return jsonify({
            "success": False,
            "error": "Forbidden",
            "message": "Access forbidden: You do not have permission to access this repair record."
        }), 403

    return jsonify({
        "success": True,
        "repair": repair.to_dict()
    }), 200


@repair_bp.route("/claims/<int:claim_id>", methods=["GET"])
@login_required
def list_claim_repairs(claim_id: int):
    """List all repair history records for a claim."""
    claim = db.session.get(Claim, claim_id)
    if not claim:
        return jsonify({"success": False, "message": "Claim not found."}), 404

    if not check_resource_ownership(claim.user_id):
        return jsonify({"success": False, "error": "Forbidden", "message": "Access denied."}), 403

    repairs = RepairHistory.query.filter_by(claim_id=claim_id).order_by(RepairHistory.repair_date.desc()).all()
    return jsonify({
        "success": True,
        "claim_uid": claim.claim_uid,
        "count": len(repairs),
        "repairs": [r.to_dict() for r in repairs]
    }), 200


@repair_bp.route("/claims/<int:claim_id>", methods=["POST"])
@login_required
@role_required(ROLE_SERVICE_CENTER, ROLE_REVIEWER, ROLE_ADMIN)
def add_claim_repair(claim_id: int):
    """
    Add a repair history record for a claim.
    Only Service Centre Employees, Reviewers, and Admins can add repairs.
    """
    claim = db.session.get(Claim, claim_id)
    if not claim:
        return jsonify({"success": False, "message": "Claim not found."}), 404

    data = request.get_json() if request.is_json else request.form

    repair_date_str = (data.get("repair_date") or "").strip()
    repair_centre = (data.get("repair_centre") or "").strip()
    parts_replaced = (data.get("parts_replaced") or "").strip() or None
    notes = (data.get("notes") or "").strip() or None
    is_authorized = str(data.get("is_authorized_centre", "true")).lower() in ("true", "1", "yes")

    try:
        repair_cost = float(data.get("repair_cost") or 0)
    except (ValueError, TypeError):
        repair_cost = 0.0

    if not repair_date_str or not repair_centre:
        return jsonify({"success": False, "message": "repair_date and repair_centre are required."}), 400

    try:
        repair_date = date.fromisoformat(repair_date_str)
    except ValueError:
        return jsonify({"success": False, "message": "Invalid repair_date format. Use YYYY-MM-DD."}), 400

    repair = RepairHistory(
        product_id=claim.product_id,
        claim_id=claim.id,
        repair_date=repair_date,
        repair_centre=repair_centre,
        parts_replaced=parts_replaced,
        repair_cost=repair_cost,
        is_authorized_centre=is_authorized,
        notes=notes
    )
    db.session.add(repair)
    db.session.commit()

    log_audit_event(
        action="REPAIR_ADDED",
        entity_type="Claim",
        entity_id=claim.claim_uid,
        description=f"Repair record {repair.repair_uid} added for claim {claim.claim_uid} at {repair_centre}"
    )

    return jsonify({"success": True, "repair": repair.to_dict()}), 201


@repair_bp.route("/products/<int:product_id>", methods=["GET"])
@login_required
def list_product_repairs(product_id: int):
    """List all repair history records for a product."""
    product = db.session.get(Product, product_id)
    if not product:
        return jsonify({"success": False, "message": "Product not found."}), 404

    if not check_resource_ownership(product.user_id):
        return jsonify({"success": False, "error": "Forbidden", "message": "Access denied."}), 403

    repairs = RepairHistory.query.filter_by(product_id=product_id).order_by(RepairHistory.repair_date.desc()).all()
    return jsonify({
        "success": True,
        "product_id": product_id,
        "count": len(repairs),
        "repairs": [r.to_dict() for r in repairs]
    }), 200
