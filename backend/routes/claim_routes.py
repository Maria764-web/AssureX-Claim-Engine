"""
AssureX Claim Routes Blueprint
Handles warranty claim registration, listing, details view, evidence upload,
and strict IDOR ownership protections for customers and staff.
"""

from datetime import date, datetime
from flask import (
    Blueprint,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
    current_app
)
from flask_login import login_required, current_user
from backend.extensions import db
from backend.models import (
    Claim,
    Product,
    Warranty,
    Document,
    CLAIM_STATUS_DRAFT,
    CLAIM_STATUS_SUBMITTED,
    DOC_TYPE_RECEIPT,
    DOC_TYPE_INVOICE,
    DOC_TYPE_WARRANTY_CARD,
    DOC_TYPE_DAMAGE_PHOTO,
    DOC_TYPE_SERIAL_PHOTO,
    DOC_TYPE_DIAGNOSTIC_REPORT,
    DOC_TYPE_OTHER
)
from backend.services.claim_service import (
    register_claim,
    add_document_to_claim,
    STANDARD_DAMAGE_TYPES
)
from backend.services.pre_submission_check import run_pre_submission_checks
from backend.utils.helpers import is_api_request
from backend.utils.security import (
    ROLE_CUSTOMER,
    ROLE_SERVICE_CENTER,
    ROLE_ADMIN,
    ROLE_REVIEWER,
    check_resource_ownership
)

claim_bp = Blueprint("claims", __name__)


@claim_bp.route("/api/claims/status", methods=["GET"])
@login_required
def claim_status():
    """Check claims service status."""
    return jsonify({
        "module": "Claims",
        "status": "ready",
        "user": current_user.user_uid,
        "role": current_user.role
    }), 200


@claim_bp.route("/api/claims/<int:claim_id>/pre-check", methods=["GET"])
@login_required
def pre_submission_check(claim_id: int):
    """
    Run pre-submission validation checks on a Draft claim.
    Returns warnings the customer should fix before submitting.
    """
    claim = db.session.get(Claim, claim_id)
    if not claim:
        return jsonify({"success": False, "message": "Claim not found."}), 404

    if claim.claim_status != CLAIM_STATUS_DRAFT:
        return jsonify({
            "success": False,
            "message": "Pre-submission checks only apply to Draft claims."
        }), 400

    if current_user.role == ROLE_CUSTOMER and not check_resource_ownership(claim.user_id):
        return jsonify({"success": False, "error": "Forbidden"}), 403

    result = run_pre_submission_checks(claim)
    return jsonify({"success": True, **result}), 200


@claim_bp.route("/api/claims", methods=["GET"])
@claim_bp.route("/claims", methods=["GET"])
@login_required
def list_claims():
    """
    List warranty claims.
    - Customers strictly view ONLY their own claims (prevents IDOR).
    - Staff (Reviewer, Service Center, Admin) see all claims.
    """
    if current_user.role == ROLE_CUSTOMER:
        claims = Claim.query.filter_by(user_id=current_user.id).order_by(Claim.created_at.desc()).all()
    else:
        claims = Claim.query.order_by(Claim.created_at.desc()).all()

    if is_api_request():
        return jsonify({
            "success": True,
            "count": len(claims),
            "claims": [c.to_dict() for c in claims]
        }), 200

    # In Web UI, redirect to dashboard which features the claims interface
    return redirect(url_for("main.customer_dashboard"))


@claim_bp.route("/claims/create", methods=["GET"])
@login_required
def create_claim_view():
    """
    Render customer warranty claim creation page.
    Optionally accepts ?product_id=<id> query parameter for preselecting a product.
    """
    selected_product_id = request.args.get("product_id", type=int)

    if current_user.role == ROLE_CUSTOMER:
        products = Product.query.filter_by(
            user_id=current_user.id
        ).order_by(Product.created_at.desc()).all()
    else:
        # Staff can file on behalf of any customer product
        products = Product.query.order_by(Product.created_at.desc()).all()

    # Pre-selected product verification
    selected_product = None
    if selected_product_id:
        selected_product = db.session.get(Product, selected_product_id)
        if selected_product and not check_resource_ownership(selected_product.user_id):
            flash("You do not have permission to file a claim for that product.", "error")
            selected_product = None
            selected_product_id = None

    return render_template(
        "create_claim.html",
        user=current_user,
        products=products,
        selected_product=selected_product,
        selected_product_id=selected_product_id,
        damage_types=STANDARD_DAMAGE_TYPES,
        today=date.today().isoformat()
    )


@claim_bp.route("/api/claims", methods=["POST"])
@claim_bp.route("/claims/create", methods=["POST"])
@login_required
def create_claim():
    """
    Register a new warranty claim with attached evidence documents.
    Supports both multipart form data (with file uploads) and JSON API payloads.
    """
    uploaded_files = []

    if request.is_json:
        data = request.get_json() or {}
        product_id = data.get("product_id")
        fault_date_input = data.get("fault_date")
        fault_description = data.get("fault_description", "")
        damage_type = data.get("damage_type", "")
        purchase_reference = data.get("purchase_reference")
        service_history_notes = data.get("service_history_notes")
        claim_status_val = data.get("claim_status", CLAIM_STATUS_SUBMITTED)
    else:
        product_id = request.form.get("product_id", type=int)
        fault_date_input = request.form.get("fault_date")
        fault_description = request.form.get("fault_description", "")
        damage_type = request.form.get("damage_type", "")
        purchase_reference = request.form.get("purchase_reference")
        service_history_notes = request.form.get("service_history_notes")
        action = request.form.get("action", "submit")
        claim_status_val = CLAIM_STATUS_DRAFT if action == "draft" else CLAIM_STATUS_SUBMITTED

        # Collect named file inputs
        file_mapping = [
            ("receipt_file", DOC_TYPE_RECEIPT),
            ("invoice_file", DOC_TYPE_INVOICE),
            ("damage_photo_file", DOC_TYPE_DAMAGE_PHOTO),
            ("warranty_card_file", DOC_TYPE_WARRANTY_CARD),
            ("serial_photo_file", DOC_TYPE_SERIAL_PHOTO),
            ("diagnostic_report_file", DOC_TYPE_DIAGNOSTIC_REPORT),
            ("other_file", DOC_TYPE_OTHER)
        ]
        for form_key, doc_type in file_mapping:
            file_obj = request.files.get(form_key)
            if file_obj and file_obj.filename:
                uploaded_files.append((file_obj, doc_type))

        # Also support multi-file arrays
        extra_files = request.files.getlist("document_files")
        extra_types = request.form.getlist("document_types")
        for i, extra_file in enumerate(extra_files):
            if extra_file and extra_file.filename:
                dtype = extra_types[i] if i < len(extra_types) else DOC_TYPE_OTHER
                uploaded_files.append((extra_file, dtype))

    # Validate product ID
    if not product_id:
        if is_api_request():
            return jsonify({
                "success": False,
                "message": "Product selection is required.",
                "errors": ["Product ID is required."]
            }), 400
        flash("Please select a registered product.", "error")
        return redirect(url_for("claims.create_claim_view"))

    product = db.session.get(Product, int(product_id))
    if not product:
        if is_api_request():
            return jsonify({
                "success": False,
                "message": "Product not found.",
                "errors": [f"Product ID '{product_id}' does not exist."]
            }), 404
        flash("Selected product was not found.", "error")
        return redirect(url_for("claims.create_claim_view"))

    # IDOR Ownership Check
    if not check_resource_ownership(product.user_id):
        if is_api_request():
            return jsonify({
                "success": False,
                "error": "Forbidden",
                "message": "Access forbidden: You do not own this product."
            }), 403
        flash("You do not have permission to file a claim for this product.", "error")
        return redirect(url_for("claims.create_claim_view"))

    # Execute Claim Registration Service
    success, errors, claim = register_claim(
        user=current_user,
        product=product,
        fault_date_input=fault_date_input,
        fault_description=fault_description,
        damage_type=damage_type,
        uploaded_files=uploaded_files,
        purchase_reference=purchase_reference,
        service_history_notes=service_history_notes,
        claim_status=claim_status_val,
        upload_root=current_app.config.get("UPLOAD_FOLDER")
    )

    if not success:
        if is_api_request():
            return jsonify({
                "success": False,
                "message": "Claim validation failed.",
                "errors": errors
            }), 400
        for err in errors:
            flash(err, "error")
        # Reload products for re-rendering form
        if current_user.role == ROLE_CUSTOMER:
            products = Product.query.filter_by(user_id=current_user.id).order_by(Product.created_at.desc()).all()
        else:
            products = Product.query.order_by(Product.created_at.desc()).all()
        return render_template(
            "create_claim.html",
            user=current_user,
            products=products,
            selected_product=product,
            selected_product_id=product.id,
            damage_types=STANDARD_DAMAGE_TYPES,
            form_data=request.form,
            today=date.today().isoformat()
        ), 400

    # Send submission notification
    if claim.claim_status != "Draft":
        try:
            from backend.services.notification_service import notify_claim_submitted
            notify_claim_submitted(claim)
        except Exception:
            pass

    if is_api_request():
        return jsonify({
            "success": True,
            "message": "Claim registered successfully.",
            "claim": claim.to_dict(),
            "documents": [d.to_dict() for d in claim.documents]
        }), 201

    flash(f"Claim '{claim.claim_uid}' has been {claim.claim_status.lower()} successfully!", "success")
    return redirect(url_for("claims.get_claim", claim_id=claim.id))


@claim_bp.route("/api/claims/<int:claim_id>", methods=["GET"])
@claim_bp.route("/claims/<int:claim_id>", methods=["GET"])
@login_required
def get_claim(claim_id: int):
    """
    Retrieve full claim details, linked product, warranty, and uploaded documents.
    Enforces strict IDOR ownership check.
    """
    claim = db.session.get(Claim, claim_id)
    if not claim:
        if is_api_request():
            return jsonify({"success": False, "message": "Claim not found."}), 404
        flash("Claim not found.", "error")
        return redirect(url_for("main.customer_dashboard"))

    # IDOR ownership validation
    if not check_resource_ownership(claim.user_id):
        if is_api_request():
            return jsonify({
                "success": False,
                "error": "Forbidden",
                "message": "Access forbidden: You do not have permission to access this claim."
            }), 403
        flash("Access forbidden: You do not have permission to access this claim.", "error")
        return redirect(url_for("main.customer_dashboard"))

    if is_api_request():
        return jsonify({
            "success": True,
            "claim": claim.to_dict(),
            "product": claim.product.to_dict() if claim.product else None,
            "warranty": claim.warranty.to_dict() if claim.warranty else None,
            "documents": [d.to_dict() for d in claim.documents]
        }), 200

    # Group documents by document_type for UI display
    grouped_documents = {}
    for doc in claim.documents:
        grouped_documents.setdefault(doc.document_type, []).append(doc)

    return render_template(
        "claim_detail.html",
        user=current_user,
        claim=claim,
        product=claim.product,
        warranty=claim.warranty,
        documents=claim.documents,
        grouped_documents=grouped_documents
    )


@claim_bp.route("/api/claims/by-uid/<string:claim_uid>", methods=["GET"])
@login_required
def get_claim_by_uid(claim_uid: str):
    """
    Retrieve claim by public UID (e.g. CLM-XXXXXXXX) with IDOR verification.
    """
    claim = Claim.query.filter_by(claim_uid=claim_uid.strip().upper()).first()
    if not claim:
        return jsonify({"success": False, "message": "Claim not found."}), 404

    if not check_resource_ownership(claim.user_id):
        return jsonify({
            "success": False,
            "error": "Forbidden",
            "message": "Access forbidden: You do not have permission to access this claim."
        }), 403

    return jsonify({
        "success": True,
        "claim": claim.to_dict(),
        "product": claim.product.to_dict() if claim.product else None,
        "warranty": claim.warranty.to_dict() if claim.warranty else None,
        "documents": [d.to_dict() for d in claim.documents]
    }), 200


@claim_bp.route("/api/claims/<int:claim_id>/documents", methods=["POST"])
@claim_bp.route("/claims/<int:claim_id>/documents", methods=["POST"])
@login_required
def upload_claim_document(claim_id: int):
    """
    Upload an additional evidence document to an existing claim.
    """
    claim = db.session.get(Claim, claim_id)
    if not claim:
        if is_api_request():
            return jsonify({"success": False, "message": "Claim not found."}), 404
        flash("Claim not found.", "error")
        return redirect(url_for("main.customer_dashboard"))

    if not check_resource_ownership(claim.user_id):
        if is_api_request():
            return jsonify({
                "success": False,
                "error": "Forbidden",
                "message": "Access forbidden: You do not have permission to modify this claim."
            }), 403
        flash("Access forbidden: You do not have permission to modify this claim.", "error")
        return redirect(url_for("main.customer_dashboard"))

    file_obj = request.files.get("document") or request.files.get("file")
    doc_type = request.form.get("document_type", DOC_TYPE_OTHER)

    if not file_obj or not file_obj.filename:
        if is_api_request():
            return jsonify({"success": False, "message": "No file was selected for upload."}), 400
        flash("Please select a file to upload.", "error")
        return redirect(url_for("claims.get_claim", claim_id=claim.id))

    success, err, doc = add_document_to_claim(
        claim=claim,
        file_storage=file_obj,
        document_type=doc_type,
        user=current_user,
        upload_root=current_app.config.get("UPLOAD_FOLDER")
    )

    if not success:
        if is_api_request():
            return jsonify({"success": False, "message": err}), 400
        flash(err, "error")
        return redirect(url_for("claims.get_claim", claim_id=claim.id))

    if is_api_request():
        return jsonify({
            "success": True,
            "message": "Document uploaded successfully.",
            "document": doc.to_dict()
        }), 201

    flash(f"Document '{doc.original_filename}' uploaded successfully!", "success")
    return redirect(url_for("claims.get_claim", claim_id=claim.id))


@claim_bp.route("/api/claims/<int:claim_id>/predict", methods=["POST"])
@login_required
def predict_claim(claim_id: int):
    """
    Generate Python model prediction for a specific claim.
    Enforces authentication and IDOR ownership checks.
    """
    from backend.services.python_model_service import predict_claim_decision, save_claim_prediction
    claim = db.session.get(Claim, claim_id)
    if not claim:
        return jsonify({"success": False, "message": "Claim not found."}), 404

    if not check_resource_ownership(claim.user_id):
        return jsonify({
            "success": False,
            "error": "Forbidden",
            "message": "Access forbidden: You do not have permission to run predictions for this claim."
        }), 403

    pred_res = predict_claim_decision(claim)
    if not pred_res.get("success"):
        return jsonify(pred_res), 500

    prediction_record = save_claim_prediction(claim.id, pred_res)
    response_data = pred_res.copy()
    response_data["prediction"] = prediction_record.to_dict()

    return jsonify(response_data), 200


@claim_bp.route("/api/claims/<int:claim_id>/teachable-predict", methods=["POST"])
@login_required
def teachable_predict_claim(claim_id: int):
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

    pred_res = predict_image_claim_decision(claim=claim)
    if not pred_res.get("success"):
        return jsonify(pred_res), 400

    prediction_record = save_teachable_prediction(claim.id, pred_res)
    response_data = pred_res.copy()
    response_data["prediction"] = prediction_record.to_dict()

    return jsonify(response_data), 200


@claim_bp.route("/claims/<int:claim_id>/result", methods=["GET"])
@login_required
def claim_result_view(claim_id: int):
    """
    Render the claim evaluation result page showing AI prediction,
    rule engine results, and final decision.
    """
    claim = db.session.get(Claim, claim_id)
    if not claim:
        flash("Claim not found.", "error")
        return redirect(url_for("main.customer_dashboard"))

    if not check_resource_ownership(claim.user_id):
        flash("Access forbidden: You do not have permission to view this claim.", "error")
        return redirect(url_for("main.customer_dashboard"))

    try:
        from backend.services.claim_summary_service import generate_decision_explanation
        explanation = generate_decision_explanation(claim)
    except Exception:
        explanation = None

    return render_template(
        "claim_result.html",
        user=current_user,
        claim=claim,
        explanation=explanation
    )


@claim_bp.route("/api/claims/<int:claim_id>/evaluate", methods=["POST"])
@login_required
def evaluate_claim_api(claim_id: int):
    """
    Trigger full AI + rule engine evaluation for a claim via API.
    Returns final decision and evaluation details.
    """
    from backend.services.final_decision import run_full_claim_evaluation

    claim = db.session.get(Claim, claim_id)
    if not claim:
        return jsonify({"success": False, "message": "Claim not found."}), 404

    if not check_resource_ownership(claim.user_id):
        return jsonify({
            "success": False,
            "error": "Forbidden",
            "message": "Access forbidden."
        }), 403

    result = run_full_claim_evaluation(claim, reviewer_id=current_user.id)
    return jsonify(result), 200 if result.get("success") else 500


@claim_bp.route("/api/claims/<int:claim_id>/plain-summary", methods=["GET"])
@login_required
def claim_plain_summary(claim_id: int):
    """
    Generate a plain-language summary and decision explanation for a claim.
    Useful for customer-facing display after evaluation.
    """
    from backend.services.claim_summary_service import generate_claim_summary, generate_decision_explanation

    claim = db.session.get(Claim, claim_id)
    if not claim:
        return jsonify({"success": False, "message": "Claim not found."}), 404

    if not check_resource_ownership(claim.user_id):
        return jsonify({"success": False, "error": "Forbidden"}), 403

    return jsonify({
        "success": True,
        "claim_uid": claim.claim_uid,
        "plain_summary": generate_claim_summary(claim),
        "decision_explanation": generate_decision_explanation(claim)
    }), 200


@claim_bp.route("/api/claims/<int:claim_id>/preflight", methods=["POST"])
@login_required
def claim_preflight(claim_id: int):
    """
    Pre-submission validation assistant — returns warnings and readiness score
    for a claim before the customer finalises submission.
    """
    claim = db.session.get(Claim, claim_id)
    if not claim:
        return jsonify({"success": False, "message": "Claim not found."}), 404

    if not check_resource_ownership(claim.user_id):
        return jsonify({"success": False, "error": "Forbidden"}), 403

    warnings = []
    suggestions = []
    score = 100

    # Check warranty status
    if claim.warranty:
        try:
            ws = claim.warranty.calculate_status()
            if ws in ("Expired", "Voided"):
                warnings.append({"level": "error", "msg": f"Warranty is {ws}. Claims on expired warranties are auto-rejected."})
                score -= 40
        except Exception:
            pass
    else:
        warnings.append({"level": "warning", "msg": "No warranty linked to this claim. Coverage cannot be confirmed."})
        score -= 20

    # Check documents
    docs = claim.documents or []
    doc_types_lower = [(getattr(d, "document_type", "") or "").lower() for d in docs]
    has_receipt = any("receipt" in dt or "invoice" in dt for dt in doc_types_lower)
    has_photo = any("photo" in dt or "image" in dt or "damage" in dt for dt in doc_types_lower)

    if not has_receipt:
        warnings.append({"level": "error", "msg": "No purchase receipt/invoice uploaded. This is required and claims without it are typically rejected."})
        score -= 30
    if not has_photo:
        warnings.append({"level": "warning", "msg": "No damage/fault photo uploaded. Photos significantly improve claim approval chances."})
        score -= 15

    # Check description length
    desc = (claim.fault_description or "").strip()
    if len(desc) < 20:
        warnings.append({"level": "warning", "msg": "Fault description is very short. A detailed description improves evaluation accuracy."})
        score -= 10
        suggestions.append("Describe what happened, when it started, and what symptoms you observed.")

    # Check fault date vs warranty period
    if claim.fault_date and claim.warranty:
        try:
            if hasattr(claim.warranty, "end_date") and claim.warranty.end_date:
                from datetime import date
                if claim.fault_date > claim.warranty.end_date:
                    warnings.append({"level": "error", "msg": f"Fault date ({claim.fault_date}) is after warranty expiry ({claim.warranty.end_date}). Claim will be rejected."})
                    score -= 40
        except Exception:
            pass

    if not warnings:
        suggestions.append("Your claim looks well-prepared for submission.")

    score = max(0, score)
    if score >= 80:
        readiness = "Good"
    elif score >= 50:
        readiness = "Fair"
    else:
        readiness = "Needs Attention"

    return jsonify({
        "success": True,
        "score": score,
        "readiness": readiness,
        "warnings": warnings,
        "suggestions": suggestions
    }), 200

