"""
AssureX Product Routes Blueprint
Handles customer product registration, product catalog listing, details view,
validation, duplicate serial detection, and IDOR ownership protections.
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
    WARRANTY_NEARING_EXPIRY
)
from backend.services.audit_service import log_audit_event
from backend.utils.helpers import is_api_request
from backend.utils.security import (
    ROLE_CUSTOMER,
    check_resource_ownership,
    customer_required
)
from backend.utils.validators import (
    validate_price,
    validate_purchase_date,
    validate_serial_number,
    validate_warranty_length
)

product_bp = Blueprint("products", __name__)


@product_bp.route("/api/products/status", methods=["GET"])
@login_required
def product_status():
    """Check products module status."""
    return jsonify({
        "module": "Products",
        "status": "ready",
        "user": current_user.user_uid
    }), 200


@product_bp.route("/api/products", methods=["GET"])
@product_bp.route("/products", methods=["GET"])
@login_required
def list_products():
    """
    List registered products.
    Customers see ONLY their own registered products (prevents cross-user IDOR).
    Staff & Administrators see all registered products.
    """
    if current_user.role == ROLE_CUSTOMER:
        products = Product.query.filter_by(
            user_id=current_user.id
        ).order_by(Product.created_at.desc()).all()
    else:
        products = Product.query.order_by(Product.created_at.desc()).all()

    if is_api_request():
        return jsonify({
            "success": True,
            "count": len(products),
            "products": [p.to_dict() for p in products]
        }), 200

    return render_template("products.html", products=products, user=current_user)


@product_bp.route("/products/register", methods=["GET"])
@login_required
@customer_required
def register_product_view():
    """Render customer product registration page."""
    return render_template("register_product.html", user=current_user)


@product_bp.route("/api/products", methods=["POST"])
@product_bp.route("/products/register", methods=["POST"])
@login_required
@customer_required
def register_product():
    """
    Register a new product under the currently authenticated Customer.
    Validates all product specifications, checks for duplicate serial registration,
    and automatically generates a unique Product UID and initial Warranty record.
    """
    if request.is_json:
        data = request.get_json() or {}
        product_name = (data.get("product_name") or "").strip()
        brand = (data.get("brand") or "").strip()
        model = (data.get("model") or "").strip()
        serial_number = (data.get("serial_number") or "").strip().upper()
        purchase_date_input = data.get("purchase_date")
        purchase_price_input = data.get("purchase_price")
        retailer = (data.get("retailer") or "").strip()
        warranty_length_input = data.get("warranty_length", 12)
    else:
        product_name = request.form.get("product_name", "").strip()
        brand = request.form.get("brand", "").strip()
        model = request.form.get("model", "").strip()
        serial_number = request.form.get("serial_number", "").strip().upper()
        purchase_date_input = request.form.get("purchase_date")
        purchase_price_input = request.form.get("purchase_price")
        retailer = request.form.get("retailer", "").strip()
        warranty_length_input = request.form.get("warranty_length", 12)

    errors = []

    # Product Name
    if not product_name:
        errors.append("Product name is required.")
    elif len(product_name) < 2 or len(product_name) > 150:
        errors.append("Product name must be between 2 and 150 characters.")

    # Brand
    if not brand:
        errors.append("Brand is required.")
    elif len(brand) < 1 or len(brand) > 100:
        errors.append("Brand must be between 1 and 100 characters.")

    # Model
    if not model:
        errors.append("Model is required.")
    elif len(model) < 1 or len(model) > 100:
        errors.append("Model must be between 1 and 100 characters.")

    # Serial Number
    if not serial_number:
        errors.append("Serial number is required.")
    elif not validate_serial_number(serial_number):
        errors.append("Serial number must be 3-60 alphanumeric characters (hyphens and underscores allowed).")

    # Purchase Date
    is_valid_date, purchase_date_obj, date_err = validate_purchase_date(purchase_date_input)
    if not is_valid_date:
        errors.append(date_err)

    # Purchase Price
    is_valid_price, purchase_price_val, price_err = validate_price(purchase_price_input)
    if not is_valid_price:
        errors.append(price_err)

    # Retailer
    if not retailer:
        errors.append("Retailer is required.")
    elif len(retailer) < 2 or len(retailer) > 150:
        errors.append("Retailer name must be between 2 and 150 characters.")

    # Warranty Length
    is_valid_wlen, warranty_length_val, wlen_err = validate_warranty_length(warranty_length_input)
    if not is_valid_wlen:
        errors.append(wlen_err)

    # Duplicate Serial Check for the same user
    if serial_number and validate_serial_number(serial_number):
        duplicate = Product.query.filter_by(
            user_id=current_user.id,
            serial_number=serial_number
        ).first()
        if duplicate:
            errors.append(f"A product with serial number '{serial_number}' is already registered under your account.")

    if errors:
        if is_api_request():
            return jsonify({
                "success": False,
                "message": "Product validation failed.",
                "errors": errors
            }), 400
        for err in errors:
            flash(err, "error")
        return render_template(
            "register_product.html",
            user=current_user,
            form_data=request.form
        ), 400

    # Derive owner strictly from current_user (Prevents user ID forgery)
    owner_user_id = current_user.id

    # Create Product
    product = Product(
        user_id=owner_user_id,
        product_name=product_name,
        brand=brand,
        model=model,
        serial_number=serial_number,
        purchase_date=purchase_date_obj,
        purchase_price=purchase_price_val,
        retailer=retailer,
        warranty_length=warranty_length_val
    )
    db.session.add(product)
    db.session.flush()  # Populate product.id

    # Calculate Warranty Expiry: purchase_date + warranty_length months
    try:
        warranty_expiry_date = purchase_date_obj + relativedelta(months=warranty_length_val)
    except Exception:
        warranty_expiry_date = purchase_date_obj + timedelta(days=int(warranty_length_val * 30.4375))

    today = date.today()
    if warranty_expiry_date < today:
        initial_status = WARRANTY_EXPIRED
    elif (warranty_expiry_date - today).days <= 30:
        initial_status = WARRANTY_NEARING_EXPIRY
    else:
        initial_status = WARRANTY_ACTIVE

    # Create Default Manufacturer Warranty
    warranty = Warranty(
        product_id=product.id,
        warranty_provider=f"{brand} Manufacturer Warranty",
        start_date=purchase_date_obj,
        expiry_date=warranty_expiry_date,
        covered_items="Manufacturer defects, electrical faults, mechanical failure under normal usage.",
        exclusions="Physical impact, unauthorized modification, liquid submersion, cosmetic wear.",
        warranty_status=initial_status
    )
    db.session.add(warranty)
    db.session.commit()

    log_audit_event(
        action="PRODUCT_REGISTERED",
        entity_type="Product",
        entity_id=product.product_uid,
        user_id=current_user.id,
        description=f"Product {product.product_uid} ({brand} {model}) registered by user {current_user.user_uid}"
    )

    if is_api_request():
        return jsonify({
            "success": True,
            "message": "Product registered successfully.",
            "product": product.to_dict(),
            "warranty": warranty.to_dict()
        }), 201

    flash(f"Product '{product.product_name}' (ID: {product.product_uid}) registered successfully!", "success")
    return redirect(url_for("products.get_product", product_id=product.id))


@product_bp.route("/api/products/<int:product_id>", methods=["GET"])
@product_bp.route("/products/<int:product_id>", methods=["GET"])
@login_required
def get_product(product_id: int):
    """
    Get detailed product information and associated warranties.
    Enforces strict IDOR ownership checks.
    """
    product = db.session.get(Product, product_id)
    if not product:
        if is_api_request():
            return jsonify({"success": False, "message": "Product not found."}), 404
        flash("Product not found.", "error")
        return redirect(url_for("products.list_products"))

    # Ownership validation
    if not check_resource_ownership(product.user_id):
        if is_api_request():
            return jsonify({
                "success": False,
                "error": "Forbidden",
                "message": "Access forbidden: You do not have permission to access this product."
            }), 403
        flash("Access forbidden: You do not have permission to access this product.", "error")
        return redirect(url_for("products.list_products"))

    if is_api_request():
        return jsonify({
            "success": True,
            "product": product.to_dict(),
            "warranties": [w.to_dict() for w in product.warranties]
        }), 200

    return render_template("product_detail.html", product=product, user=current_user)


@product_bp.route("/api/products/by-uid/<string:product_uid>", methods=["GET"])
@login_required
def get_product_by_uid(product_uid: str):
    """
    Retrieve product by public UID (e.g. PRD-XXXXXXXX) with IDOR verification.
    """
    product = Product.query.filter_by(product_uid=product_uid.strip().upper()).first()
    if not product:
        return jsonify({"success": False, "message": "Product not found."}), 404

    if not check_resource_ownership(product.user_id):
        return jsonify({
            "success": False,
            "error": "Forbidden",
            "message": "Access forbidden: You do not have permission to access this product."
        }), 403

    return jsonify({
        "success": True,
        "product": product.to_dict(),
        "warranties": [w.to_dict() for w in product.warranties]
    }), 200
