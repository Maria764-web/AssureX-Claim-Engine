"""
AssureX Document Routes Blueprint
Handles document metadata retrieval, secure file viewing, and authorized downloading
with strict IDOR ownership checks and path traversal protection.
"""

from pathlib import Path
from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for
)
from flask_login import login_required, current_user
from backend.extensions import db
from backend.models.document import Document
from backend.utils.file_handler import is_safe_path
from backend.utils.helpers import is_api_request
from backend.utils.security import check_resource_ownership

document_bp = Blueprint("documents", __name__)


@document_bp.route("/api/documents/status", methods=["GET"])
@login_required
def document_status():
    """Check documents service status."""
    return jsonify({
        "module": "Documents",
        "status": "ready",
        "user": current_user.user_uid,
        "role": current_user.role
    }), 200


def _get_document_owner_id(doc: Document):
    """Resolve the effective owner user ID for a document."""
    if doc.user_id:
        return doc.user_id
    if doc.claim:
        return doc.claim.user_id
    if doc.product:
        return doc.product.user_id
    return None


@document_bp.route("/api/documents/<int:document_id>", methods=["GET"])
@document_bp.route("/documents/<int:document_id>", methods=["GET"])
@login_required
def get_document(document_id: int):
    """
    Get document metadata with strict IDOR ownership check on claim/product owner.
    """
    doc = db.session.get(Document, document_id)
    if not doc:
        return jsonify({"success": False, "message": "Document not found."}), 404

    owner_id = _get_document_owner_id(doc)
    if owner_id and not check_resource_ownership(owner_id):
        return jsonify({
            "success": False,
            "error": "Forbidden",
            "message": "Access forbidden: You do not have permission to access this document."
        }), 403

    return jsonify({
        "success": True,
        "document": doc.to_dict()
    }), 200


@document_bp.route("/api/documents/<int:document_id>/download", methods=["GET"])
@document_bp.route("/documents/<int:document_id>/download", methods=["GET"])
@login_required
def download_document(document_id: int):
    """
    Securely download an uploaded evidence file.
    Enforces authorization, validates path safety, and prevents directory traversal.
    """
    doc = db.session.get(Document, document_id)
    if not doc:
        if is_api_request():
            return jsonify({"success": False, "message": "Document not found."}), 404
        flash("Document not found.", "error")
        return redirect(url_for("main.customer_dashboard"))

    owner_id = _get_document_owner_id(doc)
    if owner_id and not check_resource_ownership(owner_id):
        if is_api_request():
            return jsonify({
                "success": False,
                "error": "Forbidden",
                "message": "Access forbidden: You do not have permission to download this document."
            }), 403
        flash("Access forbidden: You do not have permission to download this document.", "error")
        return redirect(url_for("main.customer_dashboard"))

    upload_root = Path(current_app.config.get("UPLOAD_FOLDER", "uploads")).resolve()
    file_path = (upload_root / doc.stored_path).resolve()

    # Prevent path traversal
    if not is_safe_path(str(upload_root), str(file_path)):
        if is_api_request():
            return jsonify({"success": False, "message": "Invalid file path."}), 400
        abort(400)

    if not file_path.exists() or not file_path.is_file():
        if is_api_request():
            return jsonify({"success": False, "message": "File does not exist on storage."}), 404
        flash("The requested file was not found on the server storage.", "error")
        if doc.claim_id:
            return redirect(url_for("claims.get_claim", claim_id=doc.claim_id))
        return redirect(url_for("main.customer_dashboard"))

    return send_file(
        str(file_path),
        as_attachment=True,
        download_name=doc.original_filename,
        mimetype=doc.mime_type
    )


@document_bp.route("/api/documents/<int:document_id>/content", methods=["GET"])
@document_bp.route("/documents/<int:document_id>/raw", methods=["GET"])
@login_required
def get_document_content(document_id: int):
    """
    Safely stream raw image or PDF binary content inline.
    Enforces authentication, IDOR ownership check, and path traversal security.
    """
    doc = db.session.get(Document, document_id)
    if not doc:
        abort(404)

    owner_id = _get_document_owner_id(doc)
    if owner_id and not check_resource_ownership(owner_id):
        abort(403)

    upload_root = Path(current_app.config.get("UPLOAD_FOLDER", "uploads")).resolve()
    file_path = (upload_root / doc.stored_path).resolve()

    if not is_safe_path(str(upload_root), str(file_path)) or not file_path.exists():
        abort(404)

    return send_file(
        str(file_path),
        as_attachment=False,
        mimetype=doc.mime_type
    )


@document_bp.route("/documents/<int:document_id>/view", methods=["GET"])
@login_required
def view_document_inline(document_id: int):
    """
    Render document viewer page with header, document metadata, and Close (x) button.
    Supports JPG, JPEG, PNG, WEBP, and PDF.
    """
    if request.args.get("raw") == "1":
        return get_document_content(document_id)

    doc = db.session.get(Document, document_id)
    if not doc:
        if is_api_request():
            return jsonify({"success": False, "message": "Document not found."}), 404
        flash("Document not found.", "error")
        return redirect(url_for("main.customer_dashboard"))

    owner_id = _get_document_owner_id(doc)
    if owner_id and not check_resource_ownership(owner_id):
        if is_api_request():
            return jsonify({
                "success": False,
                "error": "Forbidden",
                "message": "Access forbidden: You do not have permission to view this document."
            }), 403
        abort(403)

    upload_root = Path(current_app.config.get("UPLOAD_FOLDER", "uploads")).resolve()
    file_path = (upload_root / doc.stored_path).resolve()

    if not is_safe_path(str(upload_root), str(file_path)) or not file_path.exists():
        if is_api_request():
            return jsonify({"success": False, "message": "File does not exist on storage."}), 404
        flash("The requested file was not found on the server storage.", "error")
        if doc.claim_id:
            return redirect(url_for("claims.get_claim", claim_id=doc.claim_id))
        return redirect(url_for("main.customer_dashboard"))

    if is_api_request():
        return jsonify({
            "success": True,
            "document": doc.to_dict(),
            "raw_url": url_for("documents.get_document_content", document_id=doc.id),
            "download_url": url_for("documents.download_document", document_id=doc.id)
        }), 200

    # Safe fallback URL (Claim detail page preferred)
    if doc.claim_id:
        fallback_url = url_for("claims.get_claim", claim_id=doc.claim_id)
    elif doc.product_id:
        fallback_url = url_for("products.get_product", product_id=doc.product_id)
    else:
        fallback_url = url_for("main.customer_dashboard")

    ext = (doc.file_extension or "").lower()
    mime = (doc.mime_type or "").lower()
    is_pdf = ext == "pdf" or "pdf" in mime
    is_image = ext in ["png", "jpg", "jpeg", "webp"] or mime.startswith("image/")

    raw_url = url_for("documents.get_document_content", document_id=doc.id)
    download_url = url_for("documents.download_document", document_id=doc.id)

    return render_template(
        "document_view.html",
        document=doc,
        claim=doc.claim,
        product=doc.product,
        raw_url=raw_url,
        download_url=download_url,
        fallback_url=fallback_url,
        is_pdf=is_pdf,
        is_image=is_image
    )

