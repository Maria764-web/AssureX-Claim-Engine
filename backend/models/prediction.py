"""
AssureX Prediction Model
Stores AI model inferences from Python ML and Google Teachable Machine models.
"""

from datetime import datetime
from backend.extensions import db
from backend.utils.helpers import utc_now, generate_uid


class Prediction(db.Model):
    """AI classification and confidence output entity."""
    __tablename__ = "predictions"

    id = db.Column(db.Integer, primary_key=True)
    prediction_uid = db.Column(db.String(32), unique=True, nullable=False, index=True, default=lambda: generate_uid("PRD-AI"))
    claim_id = db.Column(db.Integer, db.ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, index=True)

    model_name = db.Column(db.String(100), nullable=False)  # 'Python ML Model' or 'Google Teachable Machine Model'
    model_version = db.Column(db.String(50), default="1.0.0", nullable=False)
    predicted_class = db.Column(db.String(50), nullable=False)  # 'Valid', 'Invalid', 'Manual Review'
    valid_confidence = db.Column(db.Float, default=0.0, nullable=False)
    invalid_confidence = db.Column(db.Float, default=0.0, nullable=False)
    manual_review_confidence = db.Column(db.Float, default=0.0, nullable=False)
    top_prediction = db.Column(db.String(50), nullable=False)
    prediction_timestamp = db.Column(db.DateTime, default=utc_now, nullable=False)
    raw_metadata = db.Column(db.Text, nullable=True)  # JSON serialized metadata or feature contributions

    # Relationships
    claim = db.relationship("Claim", back_populates="predictions")

    def __init__(self, **kwargs):
        if "prediction_uid" not in kwargs:
            kwargs["prediction_uid"] = generate_uid("PRD-AI")
        super().__init__(**kwargs)

    def to_dict(self) -> dict:
        """Serialize prediction object to dictionary."""
        return {
            "id": self.id,
            "prediction_uid": self.prediction_uid,
            "claim_id": self.claim_id,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "predicted_class": self.predicted_class,
            "valid_confidence": self.valid_confidence,
            "invalid_confidence": self.invalid_confidence,
            "manual_review_confidence": self.manual_review_confidence,
            "top_prediction": self.top_prediction,
            "prediction_timestamp": self.prediction_timestamp.isoformat() if self.prediction_timestamp else None,
            "raw_metadata": self.raw_metadata
        }

    def __repr__(self) -> str:
        return f"<Prediction {self.prediction_uid} - {self.model_name}: {self.predicted_class} ({self.top_prediction})>"
