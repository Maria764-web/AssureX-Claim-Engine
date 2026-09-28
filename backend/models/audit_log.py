"""
AssureX Audit Log Model
Maintains tamper-evident audit trails for user actions, decisions, and security events.
"""

from datetime import datetime
from backend.extensions import db
from backend.utils.helpers import utc_now, generate_uid


class AuditLog(db.Model):
    """Audit log entry for all critical system activities."""
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    log_uid = db.Column(db.String(32), unique=True, nullable=False, index=True, default=lambda: generate_uid("AUD"))
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    action = db.Column(db.String(100), nullable=False, index=True)  # e.g. CLAIM_SUBMITTED, CLAIM_APPROVED, USER_LOGIN
    entity_type = db.Column(db.String(50), nullable=False, index=True)  # e.g. Claim, User, Product, Warranty
    entity_id = db.Column(db.String(50), nullable=True, index=True)  # Public UID or ID of target entity
    description = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    timestamp = db.Column(db.DateTime, default=utc_now, nullable=False, index=True)

    # Relationships
    user = db.relationship("User", back_populates="audit_logs")

    def __init__(self, **kwargs):
        if "log_uid" not in kwargs:
            kwargs["log_uid"] = generate_uid("AUD")
        super().__init__(**kwargs)

    def to_dict(self) -> dict:
        """Serialize audit log object to dictionary."""
        return {
            "id": self.id,
            "log_uid": self.log_uid,
            "user_id": self.user_id,
            "action": self.action,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "description": self.description,
            "ip_address": self.ip_address,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None
        }

    def __repr__(self) -> str:
        return f"<AuditLog {self.log_uid} - {self.action} on {self.entity_type}:{self.entity_id}>"
