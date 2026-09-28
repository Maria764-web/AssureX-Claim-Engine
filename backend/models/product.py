"""
AssureX Product Model
Stores customer registered products, serial numbers, purchase details, and relationships.
"""

from datetime import datetime
from backend.extensions import db
from backend.utils.helpers import utc_now, generate_uid


class Product(db.Model):
    """Customer product registration entity."""
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    product_uid = db.Column(db.String(32), unique=True, nullable=False, index=True, default=lambda: generate_uid("PRD"))
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    product_name = db.Column(db.String(150), nullable=False)
    brand = db.Column(db.String(100), nullable=False)
    model = db.Column(db.String(100), nullable=False)
    serial_number = db.Column(db.String(100), nullable=False, index=True)
    purchase_date = db.Column(db.Date, nullable=False)
    purchase_price = db.Column(db.Float, nullable=True)
    retailer = db.Column(db.String(150), nullable=True)
    warranty_length = db.Column(db.Integer, default=12, nullable=False)  # in months
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    customer = db.relationship("User", back_populates="products")
    warranties = db.relationship("Warranty", back_populates="product", cascade="all, delete-orphan", lazy="select")
    claims = db.relationship("Claim", back_populates="product", cascade="all, delete-orphan", lazy="select")
    repair_histories = db.relationship("RepairHistory", back_populates="product", cascade="all, delete-orphan", lazy="select")
    documents = db.relationship("Document", back_populates="product", lazy="select")

    def __init__(self, **kwargs):
        if "product_uid" not in kwargs:
            kwargs["product_uid"] = generate_uid("PRD")
        super().__init__(**kwargs)

    def to_dict(self) -> dict:
        """Serialize product object to dictionary."""
        return {
            "id": self.id,
            "product_uid": self.product_uid,
            "user_id": self.user_id,
            "product_name": self.product_name,
            "brand": self.brand,
            "model": self.model,
            "serial_number": self.serial_number,
            "purchase_date": self.purchase_date.isoformat() if self.purchase_date else None,
            "purchase_price": self.purchase_price,
            "retailer": self.retailer,
            "warranty_length": self.warranty_length,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }

    def __repr__(self) -> str:
        return f"<Product {self.product_uid} - {self.brand} {self.model} ({self.serial_number})>"
