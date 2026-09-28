"""
AssureX Database Models Package
Exports all domain entities for SQLAlchemy schema generation and migrations.
"""

from backend.models.user import User
from backend.models.product import Product
from backend.models.warranty import (
    Warranty,
    WARRANTY_ACTIVE,
    WARRANTY_EXPIRED,
    WARRANTY_NEARING_EXPIRY,
    WARRANTY_EXTENDED
)
from backend.models.claim import (
    Claim,
    CLAIM_STATUS_DRAFT,
    CLAIM_STATUS_SUBMITTED,
    CLAIM_STATUS_UNDER_EVALUATION,
    CLAIM_STATUS_ADDITIONAL_INFO,
    CLAIM_STATUS_MANUAL_REVIEW,
    CLAIM_STATUS_APPROVED,
    CLAIM_STATUS_REJECTED,
    CLAIM_STATUS_CLOSED,
    VALID_CLAIM_STATUSES
)
from backend.models.document import (
    Document,
    DOC_TYPE_RECEIPT,
    DOC_TYPE_INVOICE,
    DOC_TYPE_WARRANTY_CARD,
    DOC_TYPE_DAMAGE_PHOTO,
    DOC_TYPE_VIDEO,
    DOC_TYPE_SERIAL_PHOTO,
    DOC_TYPE_DIAGNOSTIC_REPORT,
    DOC_TYPE_OTHER,
    VALID_DOCUMENT_TYPES
)
from backend.models.repair_history import RepairHistory
from backend.models.prediction import Prediction
from backend.models.rule_result import (
    RuleResult,
    RULE_STATUS_PASSED,
    RULE_STATUS_FAILED,
    RULE_STATUS_WARNING,
    RULE_STATUS_INCONCLUSIVE
)
from backend.models.notification import (
    Notification,
    NOTIF_TYPE_INFO,
    NOTIF_TYPE_SUCCESS,
    NOTIF_TYPE_WARNING,
    NOTIF_TYPE_ALERT
)
from backend.models.audit_log import AuditLog
from backend.models.model_version import ModelVersion
from backend.models.document_extraction import (
    DocumentExtraction,
    EXTRACTION_STATUS_PENDING,
    EXTRACTION_STATUS_PROCESSING,
    EXTRACTION_STATUS_COMPLETED,
    EXTRACTION_STATUS_FAILED,
    EXTRACTION_STATUS_NOT_APPLICABLE,
    VALID_EXTRACTION_STATUSES,
    VERIFY_STATUS_UNVERIFIED,
    VERIFY_STATUS_VERIFIED,
    VERIFY_STATUS_NEEDS_CORRECTION,
    VALID_VERIFY_STATUSES,
)

__all__ = [
    "User",
    "Product",
    "Warranty",
    "WARRANTY_ACTIVE",
    "WARRANTY_EXPIRED",
    "WARRANTY_NEARING_EXPIRY",
    "WARRANTY_EXTENDED",
    "Claim",
    "CLAIM_STATUS_DRAFT",
    "CLAIM_STATUS_SUBMITTED",
    "CLAIM_STATUS_UNDER_EVALUATION",
    "CLAIM_STATUS_ADDITIONAL_INFO",
    "CLAIM_STATUS_MANUAL_REVIEW",
    "CLAIM_STATUS_APPROVED",
    "CLAIM_STATUS_REJECTED",
    "CLAIM_STATUS_CLOSED",
    "VALID_CLAIM_STATUSES",
    "Document",
    "DOC_TYPE_RECEIPT",
    "DOC_TYPE_INVOICE",
    "DOC_TYPE_WARRANTY_CARD",
    "DOC_TYPE_DAMAGE_PHOTO",
    "DOC_TYPE_VIDEO",
    "DOC_TYPE_SERIAL_PHOTO",
    "DOC_TYPE_DIAGNOSTIC_REPORT",
    "DOC_TYPE_OTHER",
    "VALID_DOCUMENT_TYPES",
    "RepairHistory",
    "Prediction",
    "RuleResult",
    "RULE_STATUS_PASSED",
    "RULE_STATUS_FAILED",
    "RULE_STATUS_WARNING",
    "RULE_STATUS_INCONCLUSIVE",
    "Notification",
    "NOTIF_TYPE_INFO",
    "NOTIF_TYPE_SUCCESS",
    "NOTIF_TYPE_WARNING",
    "NOTIF_TYPE_ALERT",
    "AuditLog",
    "ModelVersion",
    "DocumentExtraction",
    "EXTRACTION_STATUS_PENDING",
    "EXTRACTION_STATUS_PROCESSING",
    "EXTRACTION_STATUS_COMPLETED",
    "EXTRACTION_STATUS_FAILED",
    "EXTRACTION_STATUS_NOT_APPLICABLE",
    "VALID_EXTRACTION_STATUSES",
    "VERIFY_STATUS_UNVERIFIED",
    "VERIFY_STATUS_VERIFIED",
    "VERIFY_STATUS_NEEDS_CORRECTION",
    "VALID_VERIFY_STATUSES",
]
