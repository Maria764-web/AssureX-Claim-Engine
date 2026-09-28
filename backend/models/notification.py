"""
AssureX Notification Model
Stores system notifications, claim updates, and status alerts for users.
"""

from datetime import datetime
from backend.extensions import db
from backend.utils.helpers import utc_now, generate_uid

# Notification Types
NOTIF_TYPE_INFO = "Info"
NOTIF_TYPE_SUCCESS = "Success"
NOTIF_TYPE_WARNING = "Warning"
NOTIF_TYPE_ALERT = "Alert"


class Notification(db.Model):
    """User notification and alert message entity."""
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    notification_uid = db.Column(db.String(32), unique=True, nullable=False, index=True, default=lambda: generate_uid("NOT"))
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    title = db.Column(db.String(150), nullable=False)
    message = db.Column(db.Text, nullable=False)
    notification_type = db.Column(db.String(50), default=NOTIF_TYPE_INFO, nullable=False)
    is_read = db.Column(db.Boolean, default=False, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    # Relationships
    user = db.relationship("User", back_populates="notifications")

    def __init__(self, **kwargs):
        if "notification_uid" not in kwargs:
            kwargs["notification_uid"] = generate_uid("NOT")
        super().__init__(**kwargs)

    def to_dict(self) -> dict:
        """Serialize notification object to dictionary."""
        return {
            "id": self.id,
            "notification_uid": self.notification_uid,
            "user_id": self.user_id,
            "title": self.title,
            "message": self.message,
            "notification_type": self.notification_type,
            "is_read": self.is_read,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

    def __repr__(self) -> str:
        return f"<Notification {self.notification_uid} - User {self.user_id}: {self.title}>"
