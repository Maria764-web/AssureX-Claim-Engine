"""
AssureX User Model
Supports four primary roles: Customer, Service-Centre Employee, Claim Reviewer, Administrator.
"""

from datetime import datetime
from flask_login import UserMixin
from backend.extensions import db
from backend.utils.helpers import utc_now, generate_uid
from backend.utils.security import hash_password, verify_password, ROLE_CUSTOMER


class User(UserMixin, db.Model):
    """User account entity for all system roles."""
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    user_uid = db.Column(db.String(32), unique=True, nullable=False, index=True, default=lambda: generate_uid("USR"))
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), nullable=False, default=ROLE_CUSTOMER, index=True)
    phone = db.Column(db.String(30), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    products = db.relationship("Product", back_populates="customer", cascade="all, delete-orphan", lazy="select")
    claims = db.relationship("Claim", back_populates="customer", cascade="all, delete-orphan", lazy="select")
    notifications = db.relationship("Notification", back_populates="user", cascade="all, delete-orphan", lazy="select")
    audit_logs = db.relationship("AuditLog", back_populates="user", lazy="select")

    def __init__(self, **kwargs):
        if "password" in kwargs:
            password = kwargs.pop("password")
            self.set_password(password)
        if "user_uid" not in kwargs:
            kwargs["user_uid"] = generate_uid("USR")
        super().__init__(**kwargs)

    def set_password(self, password: str) -> None:
        """Securely hash and set the user password."""
        self.password_hash = hash_password(password)

    def check_password(self, password: str) -> bool:
        """Verify the password against the stored hash."""
        return verify_password(self.password_hash, password)

    # Flask-Login property overrides
    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_anonymous(self) -> bool:
        return False

    def get_id(self) -> str:
        return str(self.id)

    def to_dict(self, include_sensitive: bool = False) -> dict:
        """Serialize user object to dictionary."""
        data = {
            "id": self.id,
            "user_uid": self.user_uid,
            "name": self.name,
            "email": self.email,
            "role": self.role,
            "phone": self.phone,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }
        if include_sensitive:
            data["password_hash"] = self.password_hash
        return data

    def __repr__(self) -> str:
        return f"<User {self.user_uid} - {self.email} ({self.role})>"
