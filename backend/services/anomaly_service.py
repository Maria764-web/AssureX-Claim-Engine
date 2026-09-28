"""
AssureX Anomaly Detection & System Monitoring Service
Detects unusual patterns in claim volumes, decisions, and model behaviour
to alert administrators of potential issues.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List

from sqlalchemy import func

from backend.extensions import db
from backend.models.claim import Claim
from backend.models.prediction import Prediction
from backend.models.user import User
from datetime import timezone as _tz

from backend.utils.helpers import utc_now as _utc_now


def _now():
    """Return naive UTC datetime for DB comparisons (SQLite stores naive)."""
    return datetime.utcnow()

logger = logging.getLogger(__name__)

# Thresholds
MANUAL_REVIEW_RATE_THRESHOLD = 0.50   # >50% manual review in last 24h
REJECTION_RATE_THRESHOLD = 0.70       # >70% rejections in last 24h
CLAIM_SPIKE_MULTIPLIER = 3.0          # 3× average daily volume
LOW_CONFIDENCE_THRESHOLD = 0.60       # avg AI confidence below 60%
DUPLICATE_CLUSTER_LIMIT = 5           # >5 claims on same product in 24h


def _claims_in_window(hours: int = 24):
    """Return claims submitted in the last N hours."""
    cutoff = _now() - timedelta(hours=hours)
    return Claim.query.filter(Claim.submission_date >= cutoff).all()


def check_manual_review_rate() -> Dict[str, Any]:
    """Alert if manual review rate in last 24h exceeds threshold."""
    recent = _claims_in_window(24)
    total = len(recent)
    if total == 0:
        return {"name": "Manual Review Rate", "status": "ok", "detail": "No claims in last 24h."}

    manual = sum(1 for c in recent if c.claim_status == "Manual Review" or c.final_decision == "Manual Review")
    rate = manual / total

    if rate > MANUAL_REVIEW_RATE_THRESHOLD:
        return {
            "name": "Manual Review Rate",
            "status": "alert",
            "level": "warning",
            "detail": f"{manual}/{total} claims ({rate:.0%}) escalated to manual review in last 24h — above {MANUAL_REVIEW_RATE_THRESHOLD:.0%} threshold.",
            "value": f"{rate:.0%}"
        }
    return {"name": "Manual Review Rate", "status": "ok", "detail": f"{rate:.0%} ({manual}/{total} claims).", "value": f"{rate:.0%}"}


def check_rejection_rate() -> Dict[str, Any]:
    """Alert if rejection rate in last 24h exceeds threshold."""
    recent = _claims_in_window(24)
    decided = [c for c in recent if c.final_decision in ("Approved", "Rejected")]
    if not decided:
        return {"name": "Rejection Rate", "status": "ok", "detail": "No decided claims in last 24h."}

    rejected = sum(1 for c in decided if c.final_decision == "Rejected")
    rate = rejected / len(decided)

    if rate > REJECTION_RATE_THRESHOLD:
        return {
            "name": "Rejection Rate",
            "status": "alert",
            "level": "warning",
            "detail": f"{rejected}/{len(decided)} decided claims ({rate:.0%}) rejected in last 24h — above {REJECTION_RATE_THRESHOLD:.0%} threshold.",
            "value": f"{rate:.0%}"
        }
    return {"name": "Rejection Rate", "status": "ok", "detail": f"{rate:.0%} rejection rate ({rejected}/{len(decided)}).", "value": f"{rate:.0%}"}


def check_claim_spike() -> Dict[str, Any]:
    """Alert if today's claim volume is a spike vs 7-day average."""
    try:
        today_cutoff = _now() - timedelta(hours=24)
        today_count = Claim.query.filter(Claim.submission_date >= today_cutoff).count()

        week_cutoff = _now() - timedelta(days=7)
        week_count = Claim.query.filter(
            Claim.submission_date >= week_cutoff,
            Claim.submission_date < today_cutoff
        ).count()

        daily_avg = week_count / 6 if week_count > 0 else 0

        if daily_avg > 0 and today_count >= CLAIM_SPIKE_MULTIPLIER * daily_avg:
            return {
                "name": "Claim Volume Spike",
                "status": "alert",
                "level": "info",
                "detail": f"{today_count} claims in last 24h vs 6-day average of {daily_avg:.1f} — {today_count/daily_avg:.1f}× spike detected.",
                "value": f"{today_count} today"
            }
        return {"name": "Claim Volume Spike", "status": "ok", "detail": f"{today_count} claims in last 24h (avg {daily_avg:.1f}/day).", "value": str(today_count)}
    except Exception as e:
        logger.error("check_claim_spike error: %s", e)
        return {"name": "Claim Volume Spike", "status": "unknown", "detail": str(e)}


def check_ai_confidence() -> Dict[str, Any]:
    """Alert if average AI confidence across recent predictions is low."""
    try:
        cutoff = _now() - timedelta(hours=24)
        recent_preds = Prediction.query.filter(Prediction.prediction_timestamp >= cutoff).all()
        if not recent_preds:
            return {"name": "AI Confidence", "status": "ok", "detail": "No predictions in last 24h."}

        avg_conf = sum(
            max(p.valid_confidence or 0, p.invalid_confidence or 0, p.manual_review_confidence or 0)
            for p in recent_preds
        ) / len(recent_preds)

        if avg_conf < LOW_CONFIDENCE_THRESHOLD:
            return {
                "name": "AI Confidence",
                "status": "alert",
                "level": "warning",
                "detail": f"Average AI confidence is {avg_conf:.0%} across {len(recent_preds)} predictions — below {LOW_CONFIDENCE_THRESHOLD:.0%} threshold. Model may need retraining.",
                "value": f"{avg_conf:.0%}"
            }
        return {"name": "AI Confidence", "status": "ok", "detail": f"Avg confidence {avg_conf:.0%} across {len(recent_preds)} recent predictions.", "value": f"{avg_conf:.0%}"}
    except Exception as e:
        logger.error("check_ai_confidence error: %s", e)
        return {"name": "AI Confidence", "status": "unknown", "detail": str(e)}


def check_duplicate_clusters() -> Dict[str, Any]:
    """Alert if multiple claims are filed for the same product in 24h (potential fraud)."""
    try:
        cutoff = _now() - timedelta(hours=24)
        rows = db.session.query(
            Claim.product_id, func.count(Claim.id).label("cnt")
        ).filter(
            Claim.submission_date >= cutoff
        ).group_by(Claim.product_id).having(func.count(Claim.id) >= DUPLICATE_CLUSTER_LIMIT).all()

        if rows:
            clusters = [{"product_id": r.product_id, "count": r.cnt} for r in rows]
            return {
                "name": "Duplicate Claim Clusters",
                "status": "alert",
                "level": "critical",
                "detail": f"{len(clusters)} product(s) have {DUPLICATE_CLUSTER_LIMIT}+ claims in last 24h — possible fraud/abuse.",
                "clusters": clusters,
                "value": f"{len(clusters)} cluster(s)"
            }
        return {"name": "Duplicate Claim Clusters", "status": "ok", "detail": "No unusual claim clusters detected.", "value": "None"}
    except Exception as e:
        logger.error("check_duplicate_clusters error: %s", e)
        return {"name": "Duplicate Claim Clusters", "status": "unknown", "detail": str(e)}


def check_model_availability() -> Dict[str, Any]:
    """Check if the Python ML model can be loaded."""
    try:
        from backend.services.python_model_service import load_python_model_package
        package, err = load_python_model_package()
        if package:
            accuracy = package.get("test_accuracy", 0)
            return {
                "name": "Python ML Model",
                "status": "ok",
                "detail": f"Model loaded. Test accuracy: {accuracy:.2%}",
                "value": f"{accuracy:.2%}"
            }
        return {
            "name": "Python ML Model",
            "status": "alert",
            "level": "critical",
            "detail": f"Python ML model failed to load: {err}",
            "value": "Unavailable"
        }
    except Exception as e:
        return {"name": "Python ML Model", "status": "alert", "level": "critical", "detail": str(e), "value": "Error"}


def check_stale_claims() -> Dict[str, Any]:
    """Alert if claims have been sitting in Manual Review for more than 48h without resolution."""
    try:
        cutoff = _now() - timedelta(hours=48)
        stale = Claim.query.filter(
            Claim.claim_status == "Manual Review",
            Claim.updated_at <= cutoff
        ).count()

        if stale > 0:
            return {
                "name": "Stale Manual Reviews",
                "status": "alert",
                "level": "warning",
                "detail": f"{stale} claim(s) have been in Manual Review for more than 48 hours without action.",
                "value": str(stale)
            }
        return {"name": "Stale Manual Reviews", "status": "ok", "detail": "All manual review claims are being processed in time.", "value": "0"}
    except Exception as e:
        return {"name": "Stale Manual Reviews", "status": "unknown", "detail": str(e)}


def run_all_checks() -> Dict[str, Any]:
    """Run all anomaly checks and return a consolidated report."""
    checks = []
    alert_count = 0

    for fn in [
        check_model_availability,
        check_manual_review_rate,
        check_rejection_rate,
        check_claim_spike,
        check_ai_confidence,
        check_duplicate_clusters,
        check_stale_claims,
    ]:
        try:
            result = fn()
            checks.append(result)
            if result.get("status") == "alert":
                alert_count += 1
        except Exception as e:
            checks.append({"name": fn.__name__, "status": "unknown", "detail": str(e)})

    overall = "healthy"
    if alert_count >= 3:
        overall = "critical"
    elif alert_count >= 1:
        overall = "warning"

    return {
        "overall": overall,
        "alert_count": alert_count,
        "checks": checks,
        "generated_at": _now().isoformat()
    }
