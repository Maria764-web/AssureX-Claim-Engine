import json
from backend.extensions import db
from backend.utils.helpers import utc_now, generate_uid

EXTRACTION_STATUS_PENDING = 'Pending'
EXTRACTION_STATUS_PROCESSING = 'Processing'
EXTRACTION_STATUS_COMPLETED = 'Completed'
EXTRACTION_STATUS_FAILED = 'Failed'
EXTRACTION_STATUS_NOT_APPLICABLE = 'Not Applicable'
VALID_EXTRACTION_STATUSES = {EXTRACTION_STATUS_PENDING, EXTRACTION_STATUS_PROCESSING, EXTRACTION_STATUS_COMPLETED, EXTRACTION_STATUS_FAILED, EXTRACTION_STATUS_NOT_APPLICABLE}
VERIFY_STATUS_UNVERIFIED = 'Unverified'
VERIFY_STATUS_VERIFIED = 'Verified'
VERIFY_STATUS_NEEDS_CORRECTION = 'Needs Correction'
VALID_VERIFY_STATUSES = {VERIFY_STATUS_UNVERIFIED, VERIFY_STATUS_VERIFIED, VERIFY_STATUS_NEEDS_CORRECTION}

class DocumentExtraction(db.Model):
    __tablename__ = 'document_extractions'
    id = db.Column(db.Integer, primary_key=True)
    extraction_uid = db.Column(db.String(32), unique=True, nullable=False, index=True, default=lambda: generate_uid('EXT'))
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id', ondelete='CASCADE'), nullable=False, unique=True, index=True)
    claim_id = db.Column(db.Integer, db.ForeignKey('claims.id', ondelete='CASCADE'), nullable=True, index=True)
    extraction_status = db.Column(db.String(50), default=EXTRACTION_STATUS_PENDING, nullable=False, index=True)
    ocr_engine_used = db.Column(db.String(100), nullable=True)
    processing_timestamp = db.Column(db.DateTime, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    raw_text = db.Column(db.Text, nullable=True)
    extracted_fields_json = db.Column(db.Text, nullable=True)
    verified_fields_json = db.Column(db.Text, nullable=True)
    verification_status = db.Column(db.String(50), default=VERIFY_STATUS_UNVERIFIED, nullable=False, index=True)
    verified_at = db.Column(db.DateTime, nullable=True)
    verified_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now, nullable=False)
    document = db.relationship('Document', back_populates='extraction')
    claim = db.relationship('Claim', back_populates='extractions')
    verified_by = db.relationship('User', foreign_keys=[verified_by_user_id])
    def __init__(self, **kwargs):
        if 'extraction_uid' not in kwargs:
            kwargs['extraction_uid'] = generate_uid('EXT')
        super().__init__(**kwargs)
    @property
    def extracted_fields(self):
        if not self.extracted_fields_json:
            return {}
        try:
            return json.loads(self.extracted_fields_json)
        except Exception:
            return {}
    @extracted_fields.setter
    def extracted_fields(self, value):
        self.extracted_fields_json = json.dumps(value, ensure_ascii=False) if value is not None else None
    @property
    def verified_fields(self):
        if not self.verified_fields_json:
            return {}
        try:
            return json.loads(self.verified_fields_json)
        except Exception:
            return {}
    @verified_fields.setter
    def verified_fields(self, value):
        self.verified_fields_json = json.dumps(value, ensure_ascii=False) if value is not None else None
    def to_dict(self):
        return {'id': self.id, 'extraction_uid': self.extraction_uid, 'document_id': self.document_id, 'claim_id': self.claim_id, 'extraction_status': self.extraction_status, 'ocr_engine_used': self.ocr_engine_used, 'processing_timestamp': self.processing_timestamp.isoformat() if self.processing_timestamp else None, 'error_message': self.error_message, 'raw_text': self.raw_text, 'extracted_fields': self.extracted_fields, 'verified_fields': self.verified_fields, 'verification_status': self.verification_status, 'verified_at': self.verified_at.isoformat() if self.verified_at else None, 'verified_by_user_id': self.verified_by_user_id, 'created_at': self.created_at.isoformat() if self.created_at else None, 'updated_at': self.updated_at.isoformat() if self.updated_at else None}
    def __repr__(self):
        return f'<DocumentExtraction {self.extraction_uid} doc={self.document_id} status={self.extraction_status}>'
