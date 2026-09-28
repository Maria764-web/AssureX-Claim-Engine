"""
AssureX Security & Access Control Module
Handles password hashing, role constants, permission decorators, and ownership checks.
"""

from functools import wraps
from typing import Callable, Iterable, Union, Optional
from werkzeug.security import generate_password_hash, check_password_hash
from flask import abort, jsonify, redirect, request, url_for, flash
from flask_login import current_user

# Official System Roles (Exact 4 Mandatory Roles)
ROLE_CUSTOMER = "Customer"
ROLE_SERVICE_CENTER = "Service-Centre Employee"
ROLE_REVIEWER = "Claim Reviewer"
ROLE_ADMIN = "Administrator"

VALID_ROLES = {
    ROLE_CUSTOMER,
    ROLE_SERVICE_CENTER,
    ROLE_REVIEWER,
    ROLE_ADMIN
}


def hash_password(password: str) -> str:
    """Generate a secure cryptographic password hash using scrypt."""
    if not password:
        raise ValueError("Password cannot be empty")
    return generate_password_hash(password, method="scrypt")


def verify_password(password_hash: str, password: str) -> bool:
    """Verify a plain password against the stored password hash."""
    if not password_hash or not password:
        return False
    return check_password_hash(password_hash, password)


def is_valid_role(role: str) -> bool:
    """Validate if role is one of the 4 defined AssureX system roles."""
    return role in VALID_ROLES


def validate_password_strength(password: str) -> tuple[bool, Optional[str]]:
    """
    Validate password complexity:
    - Minimum 8 characters
    - At least one letter
    - At least one digit
    """
    if not password or len(password) < 8:
        return False, "Password must be at least 8 characters long."
    has_letter = any(c.isalpha() for c in password)
    has_digit = any(c.isdigit() for c in password)
    if not (has_letter and has_digit):
        return False, "Password must contain both letters and at least one number."
    return True, None


def is_api_request() -> bool:
    """Check if the current request is an API/JSON request."""
    return (
        request.is_json
        or request.path.startswith("/api/")
        or request.accept_mimetypes.best == "application/json"
    )


def role_required(*allowed_roles: Union[str, Iterable[str]]) -> Callable:
    """
    Centralized RBAC decorator to restrict access to specific roles.
    Admins always have access unless explicitly configured.
    Handles both JSON API requests (returns 401/403 JSON) and Web UI (redirects / flash).
    """
    flat_roles = set()
    for item in allowed_roles:
        if isinstance(item, (list, tuple, set)):
            flat_roles.update(item)
        else:
            flat_roles.add(item)

    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                if is_api_request():
                    return jsonify({
                        "success": False,
                        "error": "Unauthorized",
                        "message": "Authentication required."
                    }), 401
                flash("Please log in to access this page.", "warning")
                return redirect(url_for("auth.login_view", next=request.url))

            if current_user.role not in flat_roles and current_user.role != ROLE_ADMIN:
                if is_api_request():
                    return jsonify({
                        "success": False,
                        "error": "Forbidden",
                        "message": "Access forbidden: insufficient role permissions."
                    }), 403
                abort(403)

            return f(*args, **kwargs)
        return decorated_function
    return decorator


def customer_required(f: Callable) -> Callable:
    """Decorator to restrict access strictly to Customers (and Admins)."""
    return role_required(ROLE_CUSTOMER)(f)


def service_center_required(f: Callable) -> Callable:
    """Decorator to restrict access to Service-Centre Employees (and Admins)."""
    return role_required(ROLE_SERVICE_CENTER)(f)


def reviewer_required(f: Callable) -> Callable:
    """Decorator to restrict access to Claim Reviewers (and Admins)."""
    return role_required(ROLE_REVIEWER)(f)


def admin_required(f: Callable) -> Callable:
    """Decorator to restrict access strictly to Administrators."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                if is_api_request():
                    return jsonify({
                        "success": False,
                        "error": "Unauthorized",
                        "message": "Authentication required."
                    }), 401
                flash("Administrator authentication required.", "warning")
                return redirect(url_for("auth.login_view", next=request.url))

            if current_user.role != ROLE_ADMIN:
                if is_api_request():
                    return jsonify({
                        "success": False,
                        "error": "Forbidden",
                        "message": "Access forbidden: administrator privileges required."
                    }), 403
                abort(403)

            return func(*args, **kwargs)
        return decorated_function
    return decorator(f)


def check_resource_ownership(owner_user_id: int, user: Optional[object] = None) -> bool:
    """
    Verify whether the target resource belongs to the current user or user has privileged access.
    Admins, Reviewers, and Service Center employees have authorized access within their workflows.
    Customers CANNOT access other customers' resources.
    """
    active_user = user or current_user
    if not active_user or not active_user.is_authenticated:
        return False

    # Admins, Reviewers, and Service Center staff have authorized cross-customer view access
    if active_user.role in {ROLE_ADMIN, ROLE_REVIEWER, ROLE_SERVICE_CENTER}:
        return True

    # Customers can strictly access ONLY their own resources
    return active_user.id == owner_user_id
