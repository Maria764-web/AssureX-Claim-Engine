"""
AssureX Rule Result Model
Records deterministic validation rules evaluated on claims (e.g. warranty status, serial match, missing docs).
"""

from datetime import datetime
from backend.extensions import db
from backend.utils.helpers import utc_now, generate_uid

# Rule Status Constants
RULE_STATUS_PASSED = "Passed"
RULE_STATUS_FAILED = "Failed"
RULE_STATUS_WARNING = "Warning"
RULE_STATUS_INCONCLUSIVE = "Inconclusive"


class RuleResult(db.Model):
    """Deterministic validation rule evaluation result."""
    __tablename__ = "rule_results"

    id = db.Column(db.Integer, primary_key=True)
    rule_uid = db.Column(db.String(32), unique=True, nullable=False, index=True, default=lambda: generate_uid("RUL"))
    claim_id = db.Column(db.Integer, db.ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, index=True)

    rule_name = db.Column(db.String(100), nullable=False)
    rule_status = db.Column(db.String(50), default=RULE_STATUS_PASSED, nullable=False)
    rule_result = db.Column(db.String(255), nullable=True)
    details = db.Column(db.Text, nullable=True)
    checked_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    # Relationships
    claim = db.relationship("Claim", back_populates="rule_results")

    def __init__(self, **kwargs):
        if "rule_uid" not in kwargs:
            kwargs["rule_uid"] = generate_uid("RUL")
        super().__init__(**kwargs)

    def to_dict(self) -> dict:
        """Serialize rule result object to dictionary."""
        return {
            "id": self.id,
            "rule_uid": self.rule_uid,
            "claim_id": self.claim_id,
            "rule_name": self.rule_name,
            "rule_status": self.rule_status,
            "rule_result": self.rule_result,
            "details": self.details,
            "checked_at": self.checked_at.isoformat() if self.checked_at else None
        }

    def __repr__(self) -> str:
        return f"<RuleResult {self.rule_uid} - {self.rule_name}: {self.rule_status}>"
