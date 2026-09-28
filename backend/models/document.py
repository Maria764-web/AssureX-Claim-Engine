"""
AssureX Document Model
Represents uploaded invoices, receipts, warranty cards, damage photos, and evidence.
"""

from datetime import datetime
from backend.extensions import db
from backend.utils.helpers import utc_now, generate_uid

# Document Types
DOC_TYPE_RECEIPT = "Receipt"
DOC_TYPE_INVOICE = "Invoice"
DOC_TYPE_WARRANTY_CARD = "Warranty Card"
DOC_TYPE_DAMAGE_PHOTO = "Damage Photo"
DOC_TYPE_VIDEO = "Video"
DOC_TYPE_SERIAL_PHOTO = "Serial Number Photo"
DOC_TYPE_DIAGNOSTIC_REPORT = "Diagnostic Report"
DOC_TYPE_OTHER = "Other Evidence"

VALID_DOCUMENT_TYPES = {
    DOC_TYPE_RECEIPT,
    DOC_TYPE_INVOICE,
    DOC_TYPE_WARRANTY_CARD,
    DOC_TYPE_DAMAGE_PHOTO,
    DOC_TYPE_VIDEO,
    DOC_TYPE_SERIAL_PHOTO,
    DOC_TYPE_DIAGNOSTIC_REPORT,
    DOC_TYPE_OTHER
}


class Document(db.Model):
    """File attachment and evidence record."""
    __tablename__ = "documents"

    id = db.Column(db.Integer, primary_key=True)
    document_uid = db.Column(db.String(32), unique=True, nullable=False, index=True, default=lambda: generate_uid("DOC"))
    claim_id = db.Column(db.Integer, db.ForeignKey("claims.id", ondelete="CASCADE"), nullable=True, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), nullable=True, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    document_type = db.Column(db.String(50), nullable=False, default=DOC_TYPE_RECEIPT, index=True)
    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(255), nullable=False)
    stored_path = db.Column(db.String(500), nullable=False)
    file_extension = db.Column(db.String(20), nullable=False)
    mime_type = db.Column(db.String(100), nullable=True)
    file_size = db.Column(db.Integer, nullable=False)  # in bytes
    file_hash = db.Column(db.String(64), nullable=False, index=True)  # SHA-256

    upload_timestamp = db.Column(db.DateTime, default=utc_now, nullable=False)
    ocr_status = db.Column(db.String(50), default="Pending", nullable=False)
    verification_status = db.Column(db.String(50), default="Unverified", nullable=False)

    # Relationships
    claim = db.relationship("Claim", back_populates="documents")
    product = db.relationship("Product", back_populates="documents")
    uploader = db.relationship("User", backref="uploaded_documents")
    extraction = db.relationship("DocumentExtraction", back_populates="document", uselist=False, cascade="all, delete-orphan")

    def __init__(self, **kwargs):
        if "document_uid" not in kwargs:
            kwargs["document_uid"] = generate_uid("DOC")
        super().__init__(**kwargs)

    def to_dict(self) -> dict:
        """Serialize document object to dictionary."""
        return {
            "id": self.id,
            "document_uid": self.document_uid,
            "claim_id": self.claim_id,
            "product_id": self.product_id,
            "user_id": self.user_id,
            "document_type": self.document_type,
            "original_filename": self.original_filename,
            "stored_filename": self.stored_filename,
            "stored_path": self.stored_path,
            "file_extension": self.file_extension,
            "mime_type": self.mime_type,
            "file_size": self.file_size,
            "file_hash": self.file_hash,
            "upload_timestamp": self.upload_timestamp.isoformat() if self.upload_timestamp else None,
            "ocr_status": self.ocr_status,
            "verification_status": self.verification_status
        }

    def __repr__(self) -> str:
        return f"<Document {self.document_uid} - {self.document_type} ({self.original_filename})>"
