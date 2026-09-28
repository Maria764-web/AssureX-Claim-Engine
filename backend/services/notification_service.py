"""
AssureX Notification Service
Creates and manages in-app notifications for claim events, warranty alerts,
and system messages.
"""

import logging
from typing import Optional

from backend.extensions import db
from backend.models.notification import (
    Notification,
    NOTIF_TYPE_INFO,
    NOTIF_TYPE_SUCCESS,
    NOTIF_TYPE_WARNING,
    NOTIF_TYPE_ALERT
)

logger = logging.getLogger(__name__)


def create_notification(
    user_id: int,
    title: str,
    message: str,
    notification_type: str = NOTIF_TYPE_INFO
) -> Optional[Notification]:
    """Create and persist a notification for a user."""
    try:
        notif = Notification(
            user_id=user_id,
            title=title,
            message=message,
            notification_type=notification_type
        )
        db.session.add(notif)
        db.session.commit()
        return notif
    except Exception as e:
        logger.error("Failed to create notification for user %s: %s", user_id, e)
        db.session.rollback()
        return None


def notify_claim_submitted(claim) -> None:
    """Notify the customer that their claim was received."""
    try:
        create_notification(
            user_id=claim.user_id,
            title="Claim Submitted",
            message=f"Your warranty claim {claim.claim_uid} has been submitted successfully and is under review.",
            notification_type=NOTIF_TYPE_SUCCESS
        )
    except Exception as e:
        logger.warning("notify_claim_submitted error: %s", e)


def notify_claim_decision(claim) -> None:
    """Notify the customer when a final decision is made on their claim."""
    try:
        decision = claim.final_decision or claim.claim_status
        if decision == "Approved":
            title = "Claim Approved"
            message = f"Your claim {claim.claim_uid} has been evaluated as Likely Valid and approved."
            ntype = NOTIF_TYPE_SUCCESS
        elif decision == "Rejected":
            title = "Claim Decision: Not Approved"
            message = f"Your claim {claim.claim_uid} has been evaluated as Likely Invalid. Please contact support if you have questions."
            ntype = NOTIF_TYPE_ALERT
        elif decision == "Manual Review":
            title = "Claim Under Manual Review"
            message = f"Your claim {claim.claim_uid} requires additional review by our team. You will be notified of the outcome."
            ntype = NOTIF_TYPE_WARNING
        else:
            title = "Claim Status Updated"
            message = f"Your claim {claim.claim_uid} status has been updated to: {claim.claim_status}."
            ntype = NOTIF_TYPE_INFO

        create_notification(
            user_id=claim.user_id,
            title=title,
            message=message,
            notification_type=ntype
        )
    except Exception as e:
        logger.warning("notify_claim_decision error: %s", e)


def notify_manual_review_assigned(claim) -> None:
    """Notify all Claim Reviewers that a claim needs manual review."""
    try:
        from backend.models.user import User
        reviewers = User.query.filter_by(role="Claim Reviewer", is_active=True).all()
        for reviewer in reviewers:
            create_notification(
                user_id=reviewer.id,
                title="Manual Review Required",
                message=f"Claim {claim.claim_uid} (damage: {claim.damage_type or 'N/A'}) has been flagged for manual review.",
                notification_type=NOTIF_TYPE_WARNING
            )
    except Exception as e:
        logger.warning("notify_manual_review_assigned error: %s", e)


def notify_claim_approved_service(claim) -> None:
    """Notify all Service-Centre Employees that an approved claim is ready for repair."""
    try:
        from backend.models.user import User
        staff = User.query.filter_by(role="Service-Centre Employee", is_active=True).all()
        for emp in staff:
            create_notification(
                user_id=emp.id,
                title="New Repair Assignment Available",
                message=f"Claim {claim.claim_uid} has been approved and is ready for service centre attention.",
                notification_type=NOTIF_TYPE_INFO
            )
    except Exception as e:
        logger.warning("notify_claim_approved_service error: %s", e)


def notify_warranty_expiry(user, warranty, days_remaining: int) -> None:
    """Send a warranty expiry alert to the user."""
    try:
        if days_remaining <= 0:
            title = "Warranty Expired"
            message = f"Your warranty (ID: {warranty.warranty_uid}) for {getattr(warranty.product, 'product_name', 'your product') if warranty.product else 'your product'} has expired."
            ntype = NOTIF_TYPE_ALERT
        else:
            title = f"Warranty Expiring in {days_remaining} Days"
            message = f"Your warranty (ID: {warranty.warranty_uid}) for {getattr(warranty.product, 'product_name', 'your product') if warranty.product else 'your product'} expires in {days_remaining} days."
            ntype = NOTIF_TYPE_WARNING

        create_notification(
            user_id=user.id,
            title=title,
            message=message,
            notification_type=ntype
        )
    except Exception as e:
        logger.warning("notify_warranty_expiry error: %s", e)


def notify_reviewer_decision(claim, reviewer_name: str, notes: str = "") -> None:
    """Notify the customer when a reviewer manually overrides the decision."""
    try:
        decision = claim.final_decision or claim.claim_status
        message = f"A reviewer has made a decision on your claim {claim.claim_uid}: {decision}."
        if notes:
            message += f" Reviewer note: {notes[:200]}"

        ntype = NOTIF_TYPE_SUCCESS if decision == "Approved" else (
            NOTIF_TYPE_ALERT if decision == "Rejected" else NOTIF_TYPE_INFO
        )

        create_notification(
            user_id=claim.user_id,
            title="Reviewer Decision Issued",
            message=message,
            notification_type=ntype
        )
    except Exception as e:
        logger.warning("notify_reviewer_decision error: %s", e)


def get_unread_count(user_id: int) -> int:
    """Return the count of unread notifications for a user."""
    try:
        return Notification.query.filter_by(user_id=user_id, is_read=False).count()
    except Exception:
        return 0


def mark_all_read(user_id: int) -> int:
    """Mark all notifications as read for a user. Returns count updated."""
    try:
        updated = Notification.query.filter_by(user_id=user_id, is_read=False).update({"is_read": True})
        db.session.commit()
        return updated
    except Exception as e:
        logger.error("mark_all_read error for user %s: %s", user_id, e)
        db.session.rollback()
        return 0
