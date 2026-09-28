"""
AssureX Claim Model
Represents warranty claims with status lifecycle, fault details, and validation relationships.
"""

from datetime import datetime
from backend.extensions import db
from backend.utils.helpers import utc_now, generate_uid

# Claim Status Constants
CLAIM_STATUS_DRAFT = "Draft"
CLAIM_STATUS_SUBMITTED = "Submitted"
CLAIM_STATUS_UNDER_EVALUATION = "Under Evaluation"
CLAIM_STATUS_ADDITIONAL_INFO = "Additional Info Required"
CLAIM_STATUS_MANUAL_REVIEW = "Manual Review"
CLAIM_STATUS_APPROVED = "Approved"
CLAIM_STATUS_REJECTED = "Rejected"
CLAIM_STATUS_CLOSED = "Closed"

VALID_CLAIM_STATUSES = {
    CLAIM_STATUS_DRAFT,
    CLAIM_STATUS_SUBMITTED,
    CLAIM_STATUS_UNDER_EVALUATION,
    CLAIM_STATUS_ADDITIONAL_INFO,
    CLAIM_STATUS_MANUAL_REVIEW,
    CLAIM_STATUS_APPROVED,
    CLAIM_STATUS_REJECTED,
    CLAIM_STATUS_CLOSED
}


class Claim(db.Model):
    """Warranty claim submission and evaluation entity."""
    __tablename__ = "claims"

    id = db.Column(db.Integer, primary_key=True)
    claim_uid = db.Column(db.String(32), unique=True, nullable=False, index=True, default=lambda: generate_uid("CLM"))
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    warranty_id = db.Column(db.Integer, db.ForeignKey("warranties.id", ondelete="SET NULL"), nullable=True, index=True)

    fault_date = db.Column(db.Date, nullable=False)
    fault_description = db.Column(db.Text, nullable=False)
    damage_type = db.Column(db.String(100), nullable=True)
    product_age = db.Column(db.Integer, nullable=True)  # Product age in months at time of claim
    purchase_reference = db.Column(db.String(150), nullable=True)  # Invoice / purchase info reference
    service_history_notes = db.Column(db.Text, nullable=True)  # Claim-level service / repair history reference
    submission_date = db.Column(db.DateTime, default=utc_now, nullable=False)

    claim_status = db.Column(db.String(50), default=CLAIM_STATUS_SUBMITTED, nullable=False, index=True)
    final_decision = db.Column(db.String(50), nullable=True, index=True)  # Approved, Rejected, Manual Review
    decision_reasoning = db.Column(db.Text, nullable=True)  # Human-readable explanation of the decision
    reviewer_notes = db.Column(db.Text, nullable=True)  # Notes added by manual reviewer
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    customer = db.relationship("User", back_populates="claims")
    product = db.relationship("Product", back_populates="claims")
    warranty = db.relationship("Warranty", back_populates="claims")

    documents = db.relationship("Document", back_populates="claim", cascade="all, delete-orphan", lazy="select")
    repair_histories = db.relationship("RepairHistory", back_populates="claim", lazy="select")
    predictions = db.relationship("Prediction", back_populates="claim", cascade="all, delete-orphan", lazy="select")
    rule_results = db.relationship("RuleResult", back_populates="claim", cascade="all, delete-orphan", lazy="select")
    extractions = db.relationship("DocumentExtraction", back_populates="claim", cascade="all, delete-orphan", lazy="select")

    def __init__(self, **kwargs):
        if "claim_uid" not in kwargs:
            kwargs["claim_uid"] = generate_uid("CLM")
        super().__init__(**kwargs)

    def to_dict(self) -> dict:
        """Serialize claim object to dictionary."""
        data = {
            "id": self.id,
            "claim_uid": self.claim_uid,
            "user_id": self.user_id,
            "product_id": self.product_id,
            "warranty_id": self.warranty_id,
            "fault_date": self.fault_date.isoformat() if self.fault_date else None,
            "fault_description": self.fault_description,
            "damage_type": self.damage_type,
            "product_age": self.product_age,
            "purchase_reference": self.purchase_reference,
            "service_history_notes": self.service_history_notes,
            "submission_date": self.submission_date.isoformat() if self.submission_date else None,
            "claim_status": self.claim_status,
            "final_decision": self.final_decision,
            "decision_reasoning": self.decision_reasoning,
            "reviewer_notes": self.reviewer_notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "documents_count": len(self.documents) if self.documents else 0
        }
        if self.product:
            data["product_name"] = self.product.product_name
            data["product_brand"] = self.product.brand
            data["product_model"] = self.product.model
            data["product_serial"] = self.product.serial_number
        if self.warranty:
            data["warranty_uid"] = self.warranty.warranty_uid
            data["warranty_status"] = self.warranty.calculate_status()
        return data

    def __repr__(self) -> str:
        return f"<Claim {self.claim_uid} - Status: {self.claim_status}>"
