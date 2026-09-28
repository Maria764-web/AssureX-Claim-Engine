"""
AssureX Notification Routes Blueprint
Provides user notification listing with strict user isolation.
"""

from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from backend.models.notification import Notification
from backend.services.notification_service import get_unread_count, mark_all_read

notification_bp = Blueprint("notifications", __name__, url_prefix="/api/notifications")


@notification_bp.route("/status", methods=["GET"])
@login_required
def notification_status():
    """Check notifications service status."""
    return jsonify({
        "module": "Notifications",
        "status": "ready",
        "user": current_user.user_uid
    }), 200


@notification_bp.route("", methods=["GET"])
@login_required
def list_notifications():
    """List notifications for current authenticated user."""
    notifications = Notification.query.filter_by(
        user_id=current_user.id
    ).order_by(Notification.created_at.desc()).all()

    return jsonify({
        "success": True,
        "count": len(notifications),
        "unread_count": get_unread_count(current_user.id),
        "notifications": [n.to_dict() for n in notifications]
    }), 200


@notification_bp.route("/unread-count", methods=["GET"])
@login_required
def unread_count():
    """Return unread notification count for badge display."""
    return jsonify({"unread_count": get_unread_count(current_user.id)}), 200


@notification_bp.route("/mark-read", methods=["POST"])
@login_required
def mark_all_as_read():
    """Mark all notifications as read for the current user."""
    updated = mark_all_read(current_user.id)
    return jsonify({"success": True, "updated": updated}), 200


@notification_bp.route("/<int:notif_id>/read", methods=["POST"])
@login_required
def mark_one_read(notif_id: int):
    """Mark a single notification as read."""
    notif = Notification.query.filter_by(id=notif_id, user_id=current_user.id).first()
    if not notif:
        return jsonify({"success": False, "message": "Notification not found."}), 404
    notif.is_read = True
    from backend.extensions import db
    db.session.commit()
    return jsonify({"success": True}), 200
