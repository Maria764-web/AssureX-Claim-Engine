"""
AssureX Repair History Model
Tracks previous maintenance, component replacements, and authorized service center records.
"""

from datetime import datetime
from backend.extensions import db
from backend.utils.helpers import utc_now, generate_uid


class RepairHistory(db.Model):
    """Historical maintenance and repair record for products and claims."""
    __tablename__ = "repair_histories"

    id = db.Column(db.Integer, primary_key=True)
    repair_uid = db.Column(db.String(32), unique=True, nullable=False, index=True, default=lambda: generate_uid("RPR"))
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    claim_id = db.Column(db.Integer, db.ForeignKey("claims.id", ondelete="SET NULL"), nullable=True, index=True)

    repair_date = db.Column(db.Date, nullable=False)
    repair_centre = db.Column(db.String(150), nullable=False)
    parts_replaced = db.Column(db.Text, nullable=True)
    repair_cost = db.Column(db.Float, default=0.0, nullable=False)
    is_authorized_centre = db.Column(db.Boolean, default=True, nullable=False)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    # Relationships
    product = db.relationship("Product", back_populates="repair_histories")
    claim = db.relationship("Claim", back_populates="repair_histories")

    def __init__(self, **kwargs):
        if "repair_uid" not in kwargs:
            kwargs["repair_uid"] = generate_uid("RPR")
        super().__init__(**kwargs)

    def to_dict(self) -> dict:
        """Serialize repair history object to dictionary."""
        return {
            "id": self.id,
            "repair_uid": self.repair_uid,
            "product_id": self.product_id,
            "claim_id": self.claim_id,
            "repair_date": self.repair_date.isoformat() if self.repair_date else None,
            "repair_centre": self.repair_centre,
            "parts_replaced": self.parts_replaced,
            "repair_cost": self.repair_cost,
            "is_authorized_centre": self.is_authorized_centre,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

    def __repr__(self) -> str:
        return f"<RepairHistory {self.repair_uid} - Product {self.product_id} at {self.repair_centre}>"
