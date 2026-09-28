"""
AssureX Model Version Model
Tracks metadata, deployment timestamps, accuracy metrics, and active versions of AI models.
"""

from datetime import datetime
from backend.extensions import db
from backend.utils.helpers import utc_now


class ModelVersion(db.Model):
    """ML / AI model release version tracking entity."""
    __tablename__ = "model_versions"

    id = db.Column(db.Integer, primary_key=True)
    model_name = db.Column(db.String(100), nullable=False, index=True)
    version = db.Column(db.String(50), nullable=False)
    framework = db.Column(db.String(50), nullable=False)  # Scikit-Learn, TensorFlow, TeachableMachine
    accuracy = db.Column(db.Float, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    deployed_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    notes = db.Column(db.Text, nullable=True)

    def to_dict(self) -> dict:
        """Serialize model version object to dictionary."""
        return {
            "id": self.id,
            "model_name": self.model_name,
            "version": self.version,
            "framework": self.framework,
            "accuracy": self.accuracy,
            "is_active": self.is_active,
            "deployed_at": self.deployed_at.isoformat() if self.deployed_at else None,
            "notes": self.notes
        }

    def __repr__(self) -> str:
        return f"<ModelVersion {self.model_name} v{self.version} ({'Active' if self.is_active else 'Inactive'})>"
