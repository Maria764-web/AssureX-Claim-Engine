"""
AssureX Authentication Routes Module
Handles user registration, login, logout, session state, and profile management.
"""

from urllib.parse import urlparse
from flask import (
    Blueprint,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for
)
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import func
from backend.extensions import db, csrf
from backend.models.user import User
from backend.services.audit_service import log_audit_event
from backend.utils.helpers import is_api_request
from backend.utils.security import (
    ROLE_ADMIN,
    ROLE_CUSTOMER,
    ROLE_REVIEWER,
    ROLE_SERVICE_CENTER,
    VALID_ROLES,
    validate_password_strength
)
from backend.utils.validators import validate_email, validate_phone

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


def get_role_dashboard_url(role: str) -> str:
    """Return the primary dashboard URL for a given system role."""
    mapping = {
        ROLE_CUSTOMER: url_for("main.customer_dashboard"),
        ROLE_SERVICE_CENTER: url_for("service_center.dashboard"),
        ROLE_REVIEWER: url_for("reviewer.dashboard"),
        ROLE_ADMIN: url_for("admin.dashboard")
    }
    return mapping.get(role, url_for("main.customer_dashboard"))


def is_safe_url(target: str) -> bool:
    """Ensure redirect URL belongs to local application to prevent open redirects."""
    if not target:
        return False
    ref_url = urlparse(request.host_url)
    test_url = urlparse(target)
    return test_url.scheme in ("http", "https") and ref_url.netloc == test_url.netloc or not test_url.netloc


@auth_bp.route("/status", methods=["GET"])
def auth_status():
    """Health status check for auth blueprint."""
    return jsonify({
        "module": "Authentication",
        "status": "ready",
        "authenticated": current_user.is_authenticated if current_user else False,
        "role": current_user.role if current_user and current_user.is_authenticated else None
    }), 200


@auth_bp.route("/login", methods=["GET"])
def login_view():
    """Render login page or redirect if already authenticated."""
    if current_user.is_authenticated:
        return redirect(get_role_dashboard_url(current_user.role))
    return render_template("login.html")


@auth_bp.route("/login", methods=["POST"])
def login():
    """
    Authenticate user with email and password.
    Supports both standard HTML form submission and AJAX/JSON API calls.
    Automatically detects user role from the database account and redirects to role dashboard.
    """
    if current_user.is_authenticated:
        dest_url = get_role_dashboard_url(current_user.role)
        if is_api_request():
            return jsonify({
                "success": True,
                "message": "Already authenticated",
                "redirect_url": dest_url,
                "user": current_user.to_dict()
            }), 200
        return redirect(dest_url)

    # Extract credentials from JSON or Form
    if request.is_json:
        data = request.get_json() or {}
        email = data.get("email", "").strip()
        password = data.get("password", "")
        remember = bool(data.get("remember", False))
    else:
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        remember = bool(request.form.get("remember"))

    if not email or not password:
        msg = "Please provide both email and password."
        if is_api_request():
            return jsonify({"success": False, "message": msg}), 400
        flash(msg, "error")
        return render_template("login.html", email=email), 400

    # Query user case-insensitively
    user = User.query.filter(func.lower(User.email) == email.lower()).first()

    # Check credentials and active status
    if not user or not user.is_active or not user.check_password(password):
        # Audit failed login attempt (do NOT reveal whether email exists)
        log_audit_event(
            action="AUTH_LOGIN_FAILED",
            entity_type="User",
            entity_id=email,
            description="Failed login attempt with invalid credentials"
        )
        generic_error = "Invalid email or password."
        if is_api_request():
            return jsonify({"success": False, "message": generic_error}), 401
        flash(generic_error, "error")
        return render_template("login.html", email=email), 401

    # Successful login
    login_user(user, remember=remember)

    log_audit_event(
        action="AUTH_LOGIN_SUCCESS",
        entity_type="User",
        entity_id=user.user_uid,
        user_id=user.id,
        description=f"Successful login for user {user.user_uid} ({user.role})"
    )

    # Determine destination URL from database role
    dest_url = get_role_dashboard_url(user.role)
    next_page = request.args.get("next") or request.form.get("next")
    if next_page and is_safe_url(next_page):
        dest_url = next_page

    if is_api_request():
        return jsonify({
            "success": True,
            "message": "Login successful.",
            "redirect_url": dest_url,
            "user": user.to_dict()
        }), 200

    flash(f"Welcome back, {user.name}!", "success")
    return redirect(dest_url)


@auth_bp.route("/register", methods=["GET"])
def register_view():
    """Render registration page or redirect if already authenticated non-admin."""
    if current_user.is_authenticated and current_user.role != ROLE_ADMIN:
        return redirect(get_role_dashboard_url(current_user.role))
    return render_template("register.html")


@auth_bp.route("/register", methods=["POST"])
def register():
    """
    Register a new user account.
    CRITICAL SECURITY RULE:
    - Public (unauthenticated) registration strictly creates 'Customer' accounts only.
    - Privileged staff/admin roles (Service-Centre Employee, Claim Reviewer, Administrator)
      can ONLY be created by an authenticated Administrator.
    - Any attempt by a public unauthenticated user to register with a privileged role is rejected with 403 Forbidden.
    """
    if request.is_json:
        data = request.get_json() or {}
        name = data.get("name", "").strip()
        email = data.get("email", "").strip()
        phone = data.get("phone", "").strip()
        password = data.get("password", "")
        confirm_password = data.get("confirm_password", data.get("password_confirm", ""))
        requested_role = (data.get("role") or "").strip() or ROLE_CUSTOMER
    else:
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", request.form.get("password_confirm", ""))
        requested_role = (request.form.get("role") or "").strip() or ROLE_CUSTOMER

    errors = []

    # Validate role
    if requested_role not in VALID_ROLES:
        errors.append(f"Invalid role selected. Must be one of: {', '.join(sorted(VALID_ROLES))}")

    # RBAC check: Privileged roles require active Administrator session
    is_admin = current_user.is_authenticated and current_user.role == ROLE_ADMIN
    if requested_role in (ROLE_SERVICE_CENTER, ROLE_REVIEWER, ROLE_ADMIN) and not is_admin:
        unauthorized_msg = "Staff and Administrator accounts can only be created by an authorized Administrator."
        if is_api_request():
            return jsonify({
                "success": False,
                "error": "Forbidden",
                "message": unauthorized_msg,
                "errors": [unauthorized_msg]
            }), 403
        flash(unauthorized_msg, "error")
        return render_template(
            "register.html",
            name=name,
            email=email,
            phone=phone,
            selected_role=ROLE_CUSTOMER
        ), 403

    # Required fields
    if not name:
        errors.append("Full name is required.")
    elif len(name) < 2 or len(name) > 120:
        errors.append("Name must be between 2 and 120 characters.")

    if not email:
        errors.append("Email address is required.")
    elif not validate_email(email):
        errors.append("Please enter a valid email address.")

    # Duplicate email check
    if email and validate_email(email):
        existing_user = User.query.filter(func.lower(User.email) == email.lower()).first()
        if existing_user:
            errors.append("An account with this email address already exists.")

    # Phone validation (if provided)
    if phone and not validate_phone(phone):
        errors.append("Please enter a valid phone number.")

    # Password match
    if not password:
        errors.append("Password is required.")
    elif password != confirm_password:
        errors.append("Passwords do not match.")
    else:
        # Password strength validation
        is_strong, strength_msg = validate_password_strength(password)
        if not is_strong:
            errors.append(strength_msg)

    if errors:
        if is_api_request():
            return jsonify({
                "success": False,
                "message": "Registration validation failed.",
                "errors": errors
            }), 400
        for err in errors:
            flash(err, "error")
        return render_template(
            "register.html",
            name=name,
            email=email,
            phone=phone,
            selected_role=requested_role
        ), 400

    # Create new User with authorized role
    new_user = User(
        name=name,
        email=email.lower(),
        phone=phone if phone else None,
        role=requested_role,
        password=password,
        is_active=True
    )
    db.session.add(new_user)
    db.session.commit()

    log_audit_event(
        action="USER_REGISTRATION",
        entity_type="User",
        entity_id=new_user.user_uid,
        user_id=new_user.id,
        description=f"User registered with role {requested_role}: {new_user.email}"
    )

    if is_api_request():
        return jsonify({
            "success": True,
            "message": f"Account for {new_user.email} created with role {new_user.role}.",
            "user": new_user.to_dict()
        }), 201

    if is_admin:
        flash(f"Account for {new_user.name} ({new_user.role}) created successfully.", "success")
        return redirect(url_for("admin.dashboard"))

    flash("Registration successful! Please log in with your credentials.", "success")
    return redirect(url_for("auth.login_view"))


@auth_bp.route("/logout", methods=["GET", "POST"])
def logout():
    """Log out the current authenticated user and clear session."""
    if current_user.is_authenticated:
        log_audit_event(
            action="AUTH_LOGOUT",
            entity_type="User",
            entity_id=current_user.user_uid,
            user_id=current_user.id,
            description="User logged out"
        )
        logout_user()

    if is_api_request():
        return jsonify({
            "success": True,
            "message": "Successfully logged out."
        }), 200

    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login_view"))


@auth_bp.route("/me", methods=["GET"])
@login_required
def get_current_user_profile():
    """Return sanitized profile data of the logged-in user."""
    return jsonify({
        "success": True,
        "user": current_user.to_dict()
    }), 200


@auth_bp.route("/profile", methods=["GET"])
@login_required
def profile_view():
    """Render user profile management page."""
    return render_template("profile.html", user=current_user)


@auth_bp.route("/profile", methods=["PUT", "POST"])
@login_required
def update_profile():
    """
    Update logged-in user profile details (Name & Phone).
    CRITICAL SECURITY RULE: Role, user_uid, email, and is_active CANNOT be altered here.
    """
    if request.is_json:
        data = request.get_json() or {}
        name = data.get("name")
        phone = data.get("phone")
    else:
        name = request.form.get("name")
        phone = request.form.get("phone")

    errors = []
    if name is not None:
        name = name.strip()
        if len(name) < 2 or len(name) > 120:
            errors.append("Name must be between 2 and 120 characters.")
        else:
            current_user.name = name

    if phone is not None:
        phone = phone.strip()
        if phone and not validate_phone(phone):
            errors.append("Please enter a valid phone number.")
        else:
            current_user.phone = phone if phone else None

    if errors:
        if is_api_request():
            return jsonify({"success": False, "errors": errors}), 400
        for err in errors:
            flash(err, "error")
        return redirect(url_for("auth.profile_view"))

    db.session.commit()

    log_audit_event(
        action="USER_PROFILE_UPDATED",
        entity_type="User",
        entity_id=current_user.user_uid,
        description=f"User updated personal profile details"
    )

    if is_api_request():
        return jsonify({
            "success": True,
            "message": "Profile updated successfully.",
            "user": current_user.to_dict()
        }), 200

    flash("Profile updated successfully.", "success")
    return redirect(url_for("auth.profile_view"))

