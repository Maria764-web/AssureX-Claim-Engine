from flask import Blueprint, jsonify, redirect, render_template, send_from_directory, url_for
from pathlib import Path
from flask_login import login_required, current_user
from sqlalchemy import text
from backend.extensions import db
from backend.models.claim import Claim
from backend.models.product import Product
from backend.models.warranty import (
    Warranty,
    WARRANTY_ACTIVE,
    WARRANTY_EXPIRED,
    WARRANTY_NEARING_EXPIRY
)
from backend.routes.auth_routes import get_role_dashboard_url
from backend.utils.helpers import is_api_request
from backend.utils.security import customer_required

main_bp = Blueprint("main", __name__)


@main_bp.route("/", methods=["GET"])
def index():
    """
    Root website entry point.
    - If user is already authenticated: redirects directly to role-specific dashboard.
    - If unauthenticated visitor: renders user-facing AssureX landing page.
    """
    if current_user.is_authenticated:
        return redirect(get_role_dashboard_url(current_user.role))

    return render_template("index.html")



@main_bp.route("/health", methods=["GET"])
def health_check():
    """
    Health check endpoint.
    Verifies that Flask application is active and SQLite database connection is responsive.
    """
    db_status = "unknown"
    is_healthy = True

    try:
        db.session.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception:
        is_healthy = False
        db_status = "disconnected"

    status_code = 200 if is_healthy else 503
    return jsonify({
        "status": "healthy" if is_healthy else "unhealthy",
        "database": db_status,
        "service": "AssureX Claim Engine",
        "environment": "active"
    }), status_code


@main_bp.route("/dashboard", methods=["GET"])
@login_required
@customer_required
def customer_dashboard():
    """
    Customer portal dashboard with real-time database-driven data.
    Computes summary cards for total products, warranty statuses, and warranty claims.
    """
    products = Product.query.filter_by(
        user_id=current_user.id
    ).order_by(Product.created_at.desc()).all()

    total_products = len(products)
    active_warranties = 0
    nearing_warranties = 0
    expired_warranties = 0

    for product in products:
        for warranty in product.warranties:
            status = warranty.calculate_status()
            if status in (WARRANTY_ACTIVE, "Extended"):
                active_warranties += 1
            elif status == WARRANTY_NEARING_EXPIRY:
                nearing_warranties += 1
            elif status == WARRANTY_EXPIRED:
                expired_warranties += 1

    recent_products = products[:5]

    # Query customer's warranty claims
    claims = Claim.query.filter_by(
        user_id=current_user.id
    ).order_by(Claim.created_at.desc()).all()

    total_claims = len(claims)
    submitted_claims = sum(1 for c in claims if c.claim_status == "Submitted")
    draft_claims = sum(1 for c in claims if c.claim_status == "Draft")

    return render_template(
        "dashboard.html",
        user=current_user,
        products=products,
        recent_products=recent_products,
        total_products=total_products,
        active_warranties=active_warranties,
        nearing_warranties=nearing_warranties,
        expired_warranties=expired_warranties,
        claims=claims,
        total_claims=total_claims,
        submitted_claims=submitted_claims,
        draft_claims=draft_claims
    )


@main_bp.route("/claim-cards/<filename>", methods=["GET"])
@login_required
def serve_claim_card(filename: str):
    """Serve generated Claim Summary Card images."""
    cards_dir = Path(__file__).resolve().parent.parent.parent / "claim_summary_cards"
    return send_from_directory(str(cards_dir), filename)


@main_bp.route("/profile", methods=["GET"])
@login_required
def profile_redirect():
    """Redirect to authenticated user profile page."""
    from flask import redirect, url_for
    return redirect(url_for("auth.profile_view"))


