"""
AssureX Analytics Service
Provides system-wide statistics for admin and reviewer dashboards:
claim volumes, AI model accuracy, decision distribution, and trends.
"""

import logging
from datetime import date, timedelta
from typing import Dict, Any, List

from sqlalchemy import func

from backend.extensions import db
from backend.models.claim import Claim
from backend.models.prediction import Prediction
from backend.models.user import User
from backend.models.product import Product
from backend.models.warranty import Warranty

logger = logging.getLogger(__name__)


def get_claim_status_distribution() -> Dict[str, int]:
    """Count of claims per status."""
    rows = db.session.query(
        Claim.claim_status, func.count(Claim.id)
    ).group_by(Claim.claim_status).all()
    return {status: count for status, count in rows}


def get_decision_distribution() -> Dict[str, int]:
    """Count of claims per final decision."""
    rows = db.session.query(
        Claim.final_decision, func.count(Claim.id)
    ).filter(Claim.final_decision.isnot(None)).group_by(Claim.final_decision).all()
    return {decision: count for decision, count in rows}


def get_claims_over_time(days: int = 30) -> List[Dict[str, Any]]:
    """Claim submissions grouped by day for the last N days."""
    cutoff = date.today() - timedelta(days=days)

    rows = db.session.query(
        func.date(Claim.submission_date).label("day"),
        func.count(Claim.id).label("count")
    ).filter(
        Claim.submission_date >= cutoff
    ).group_by(func.date(Claim.submission_date)).order_by("day").all()

    return [{"date": str(row.day), "count": row.count} for row in rows]


def get_model_prediction_summary() -> Dict[str, Any]:
    """Summarize AI model predictions across all models."""
    rows = db.session.query(
        Prediction.model_name,
        Prediction.predicted_class,
        func.count(Prediction.id).label("count"),
        func.avg(Prediction.valid_confidence).label("avg_valid_conf"),
        func.avg(Prediction.invalid_confidence).label("avg_invalid_conf")
    ).group_by(Prediction.model_name, Prediction.predicted_class).all()

    summary = {}
    for row in rows:
        model = row.model_name or "Unknown"
        if model not in summary:
            summary[model] = {"predictions": {}, "total": 0}
        summary[model]["predictions"][row.predicted_class or "Unknown"] = {
            "count": row.count,
            "avg_valid_conf": round(float(row.avg_valid_conf or 0), 4),
            "avg_invalid_conf": round(float(row.avg_invalid_conf or 0), 4)
        }
        summary[model]["total"] += row.count

    return summary


def get_system_overview() -> Dict[str, Any]:
    """High-level system counts for dashboard."""
    total_users = User.query.count()
    total_customers = User.query.filter_by(role="Customer").count()
    total_products = Product.query.count()
    total_warranties = Warranty.query.count()
    total_claims = Claim.query.count()
    total_predictions = Prediction.query.count()

    approved = Claim.query.filter_by(final_decision="Approved").count()
    rejected = Claim.query.filter_by(final_decision="Rejected").count()
    manual_review = Claim.query.filter_by(claim_status="Manual Review").count()
    pending = Claim.query.filter(
        Claim.claim_status.in_(["Submitted", "Under Evaluation"])
    ).count()

    approval_rate = round(approved / total_claims * 100, 1) if total_claims > 0 else 0.0
    rejection_rate = round(rejected / total_claims * 100, 1) if total_claims > 0 else 0.0

    return {
        "users": {
            "total": total_users,
            "customers": total_customers,
            "staff": total_users - total_customers
        },
        "products": total_products,
        "warranties": total_warranties,
        "claims": {
            "total": total_claims,
            "pending": pending,
            "approved": approved,
            "rejected": rejected,
            "manual_review": manual_review,
            "approval_rate": approval_rate,
            "rejection_rate": rejection_rate
        },
        "predictions": total_predictions
    }


def get_recent_claims(limit: int = 10) -> List[Dict[str, Any]]:
    """Return the most recently submitted claims."""
    claims = Claim.query.order_by(Claim.submission_date.desc()).limit(limit).all()
    return [c.to_dict() for c in claims]


def get_damage_type_breakdown() -> List[Dict[str, Any]]:
    """Count of claims per damage type."""
    rows = db.session.query(
        Claim.damage_type,
        func.count(Claim.id).label("count")
    ).filter(
        Claim.damage_type.isnot(None)
    ).group_by(Claim.damage_type).order_by(func.count(Claim.id).desc()).limit(15).all()

    return [{"damage_type": row.damage_type, "count": row.count} for row in rows]


def get_full_analytics_data() -> Dict[str, Any]:
    """Aggregate all analytics data for admin dashboard."""
    try:
        return {
            "overview": get_system_overview(),
            "status_distribution": get_claim_status_distribution(),
            "decision_distribution": get_decision_distribution(),
            "claims_over_time": get_claims_over_time(30),
            "model_predictions": get_model_prediction_summary(),
            "recent_claims": get_recent_claims(10),
            "damage_type_breakdown": get_damage_type_breakdown()
        }
    except Exception as e:
        logger.error("Analytics data fetch error: %s", e, exc_info=True)
        return {"error": str(e)}
