"""
AssureX Warranty Model
Manages product warranty policies, coverage periods, covered faults, and exclusions.
"""

from datetime import date, datetime, timedelta
from backend.extensions import db
from backend.utils.helpers import utc_now, generate_uid

# Warranty Status Constants
WARRANTY_ACTIVE = "Active"
WARRANTY_EXPIRED = "Expired"
WARRANTY_NEARING_EXPIRY = "Nearing Expiry"
WARRANTY_EXTENDED = "Extended"


class Warranty(db.Model):
    """Product warranty policy and status tracking entity."""
    __tablename__ = "warranties"

    id = db.Column(db.Integer, primary_key=True)
    warranty_uid = db.Column(db.String(32), unique=True, nullable=False, index=True, default=lambda: generate_uid("WAR"))
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    warranty_provider = db.Column(db.String(150), nullable=False, default="Manufacturer")
    start_date = db.Column(db.Date, nullable=False)
    expiry_date = db.Column(db.Date, nullable=False)
    covered_items = db.Column(db.Text, nullable=True)  # JSON or text description of covered components/faults
    exclusions = db.Column(db.Text, nullable=True)     # JSON or text description of excluded damage types
    warranty_status = db.Column(db.String(50), default=WARRANTY_ACTIVE, nullable=False, index=True)
    is_extended = db.Column(db.Boolean, default=False, nullable=False)
    extended_details = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    product = db.relationship("Product", back_populates="warranties")
    claims = db.relationship("Claim", back_populates="warranty", lazy="select")

    def __init__(self, **kwargs):
        if "warranty_uid" not in kwargs:
            kwargs["warranty_uid"] = generate_uid("WAR")
        # Pop warranty_duration if passed as a transient kwarg
        kwargs.pop("warranty_duration", None)
        super().__init__(**kwargs)

    @property
    def warranty_duration(self) -> int:
        """Duration in months from start_date to expiry_date, or from related product."""
        if self.product and self.product.warranty_length:
            return self.product.warranty_length
        if self.start_date and self.expiry_date:
            return (self.expiry_date.year - self.start_date.year) * 12 + (self.expiry_date.month - self.start_date.month)
        return 12

    def calculate_status(self, as_of_date: date = None) -> str:
        """
        Dynamically calculate warranty status:
        Active, Expired, Nearing Expiry (within 30 days), Extended.
        """
        if as_of_date is None:
            as_of_date = date.today()

        if self.expiry_date < as_of_date:
            return WARRANTY_EXPIRED

        if self.is_extended:
            return WARRANTY_EXTENDED

        days_remaining = (self.expiry_date - as_of_date).days
        if 0 <= days_remaining <= 30:
            return WARRANTY_NEARING_EXPIRY

        return WARRANTY_ACTIVE

    def is_active(self, as_of_date: date = None) -> bool:
        """Return True if warranty status is Active, Nearing Expiry, or Extended as of the specified date."""
        return self.calculate_status(as_of_date) in [WARRANTY_ACTIVE, WARRANTY_NEARING_EXPIRY, WARRANTY_EXTENDED]

    def to_dict(self) -> dict:
        """Serialize warranty object to dictionary."""
        dynamic_status = self.calculate_status()
        return {
            "id": self.id,
            "warranty_uid": self.warranty_uid,
            "product_id": self.product_id,
            "warranty_provider": self.warranty_provider,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "expiry_date": self.expiry_date.isoformat() if self.expiry_date else None,
            "warranty_duration": self.warranty_duration,
            "covered_items": self.covered_items,
            "exclusions": self.exclusions,
            "warranty_status": dynamic_status,
            "status": dynamic_status,
            "is_extended": self.is_extended,
            "extended_details": self.extended_details,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }

    def __repr__(self) -> str:
        return f"<Warranty {self.warranty_uid} - Product {self.product_id} ({self.warranty_status})>"
