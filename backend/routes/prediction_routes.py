"""
AssureX Prediction Routes Blueprint
Provides API endpoints for inspecting and generating AI predictions using Python ML model.
"""

import time
from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from backend.extensions import db
from backend.models.claim import Claim
from backend.models.prediction import Prediction
from backend.services.python_model_service import (
    predict_claim_decision,
    save_claim_prediction,
    load_python_model_package
)
from backend.utils.security import (
    ROLE_ADMIN,
    ROLE_REVIEWER,
    ROLE_SERVICE_CENTER,
    ROLE_CUSTOMER,
    role_required,
    check_resource_ownership
)

prediction_bp = Blueprint("predictions", __name__, url_prefix="/api/predictions")


@prediction_bp.route("/status", methods=["GET"])
@login_required
@role_required(ROLE_REVIEWER, ROLE_ADMIN)
def prediction_status():
    """Check prediction service status and model metadata."""
    package, err = load_python_model_package()
    model_ready = package is not None
    return jsonify({
        "module": "Predictions",
        "status": "ready" if model_ready else "error",
        "model_loaded": model_ready,
        "model_name": package.get("model_name") if package else None,
        "test_accuracy": package.get("test_accuracy") if package else None,
        "average_confidence": package.get("average_confidence") if package else None,
        "error": err,
        "user": current_user.user_uid
    }), 200 if model_ready else 500


@prediction_bp.route("/<int:prediction_id>", methods=["GET"])
@login_required
def get_prediction(prediction_id: int):
    """Get prediction record by ID."""
    prediction = db.session.get(Prediction, prediction_id)
    if not prediction:
        return jsonify({"success": False, "message": "Prediction record not found."}), 404

    # Enforce IDOR protection
    if not check_resource_ownership(prediction.claim.user_id):
        return jsonify({
            "success": False,
            "error": "Forbidden",
            "message": "Access forbidden: You do not have permission to view this prediction."
        }), 403

    return jsonify({
        "success": True,
        "prediction": prediction.to_dict()
    }), 200


@prediction_bp.route("/claims/<int:claim_id>/predict", methods=["POST"])
@login_required
def predict_claim_by_id(claim_id: int):
    """
    Generate Python model prediction for a specific claim.
    Enforces authentication and IDOR ownership checks.
    """
    claim = db.session.get(Claim, claim_id)
    if not claim:
        return jsonify({"success": False, "message": "Claim not found."}), 404

    # IDOR ownership protection: Customers can only predict their own claims.
    if not check_resource_ownership(claim.user_id):
        return jsonify({
            "success": False,
            "error": "Forbidden",
            "message": "Access forbidden: You do not have permission to run predictions for this claim."
        }), 403

    t0 = time.perf_counter()
    pred_res = predict_claim_decision(claim)
    if not pred_res.get("success"):
        return jsonify(pred_res), 500

    prediction_record = save_claim_prediction(claim.id, pred_res)

    response_data = pred_res.copy()
    response_data["prediction"] = prediction_record.to_dict()
    response_data["processing_time_ms"] = round((time.perf_counter() - t0) * 1000)

    return jsonify(response_data), 200


@prediction_bp.route("/claims/<int:claim_id>/teachable-predict", methods=["POST"])
@login_required
def teachable_predict_claim_by_id(claim_id: int):
    """
    Generate Teachable Machine vision model prediction for a specific claim's evidence image.
    Enforces authentication and IDOR ownership checks.
    """
    from backend.services.teachable_machine_service import predict_image_claim_decision, save_teachable_prediction
    claim = db.session.get(Claim, claim_id)
    if not claim:
        return jsonify({"success": False, "message": "Claim not found."}), 404

    if not check_resource_ownership(claim.user_id):
        return jsonify({
            "success": False,
            "error": "Forbidden",
            "message": "Access forbidden: You do not have permission to run predictions for this claim."
        }), 403

    t0 = time.perf_counter()
    pred_res = predict_image_claim_decision(claim=claim)
    if not pred_res.get("success"):
        return jsonify(pred_res), 400

    prediction_record = save_teachable_prediction(claim.id, pred_res)
    response_data = pred_res.copy()
    response_data["prediction"] = prediction_record.to_dict()
    response_data["processing_time_ms"] = round((time.perf_counter() - t0) * 1000)

    return jsonify(response_data), 200
