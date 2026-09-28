"""
AssureX Audit Service
Centralized service for logging system events, logins, registrations, and administrative changes.
"""

from typing import Optional
from flask import request
from flask_login import current_user
from backend.extensions import db
from backend.models.audit_log import AuditLog


def log_audit_event(
    action: str,
    entity_type: str,
    entity_id: Optional[str] = None,
    description: Optional[str] = None,
    user_id: Optional[int] = None,
    ip_address: Optional[str] = None
) -> Optional[AuditLog]:
    """
    Record an audit trail log entry.
    Never logs passwords, tokens, or sensitive secret credentials.

    Args:
        action: Identifier like 'AUTH_LOGIN_SUCCESS', 'USER_REGISTRATION', etc.
        entity_type: e.g. 'User', 'Claim', 'Product'
        entity_id: Identifier of target entity (e.g. user_uid, claim_uid)
        description: Non-sensitive summary text
        user_id: Performing user ID (defaults to current_user.id if logged in)
        ip_address: Client IP address (defaults to request.remote_addr if in request context)

    Returns:
        The created AuditLog record or None on failure.
    """
    try:
        # Determine user id
        if user_id is None and current_user and getattr(current_user, "is_authenticated", False):
            user_id = current_user.id

        # Determine IP
        if ip_address is None and request:
            ip_address = request.headers.get("X-Forwarded-For", request.remote_addr)
            if ip_address and "," in ip_address:
                ip_address = ip_address.split(",")[0].strip()

        log_entry = AuditLog(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            description=description,
            ip_address=ip_address
        )
        db.session.add(log_entry)
        db.session.commit()
        return log_entry
    except Exception:
        db.session.rollback()
        return None
