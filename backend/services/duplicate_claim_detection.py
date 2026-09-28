"""
AssureX Duplicate Claim Detection Service
Detects potential duplicate claims for the same product, fault type,
and time window to prevent fraudulent re-submissions.
"""

import logging
from datetime import date, timedelta
from typing import Dict, Any, List, Optional

from backend.extensions import db
from backend.models.claim import Claim, CLAIM_STATUS_REJECTED, CLAIM_STATUS_CLOSED

logger = logging.getLogger(__name__)

DUPLICATE_WINDOW_DAYS = 90
SIMILARITY_THRESHOLD = 0.75


def _normalize_text(text: str) -> str:
    return " ".join((text or "").lower().split())


def _text_similarity(a: str, b: str) -> float:
    """Simple word-overlap Jaccard similarity."""
    words_a = set(_normalize_text(a).split())
    words_b = set(_normalize_text(b).split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


def find_duplicate_claims(
    claim: Claim,
    window_days: int = DUPLICATE_WINDOW_DAYS
) -> List[Dict[str, Any]]:
    """
    Search for potential duplicate claims for the same product within a time window.

    Duplicate signals:
    - Same product_id
    - Similar fault description (Jaccard >= SIMILARITY_THRESHOLD)
    - Same or similar damage_type
    - Submitted within window_days of each other
    - Not the claim itself

    Returns list of potential duplicate claim dicts with similarity scores.
    """
    if not claim or not claim.product_id:
        return []

    cutoff_date = (claim.fault_date or date.today()) - timedelta(days=window_days)

    existing_claims = Claim.query.filter(
        Claim.product_id == claim.product_id,
        Claim.id != claim.id,
        Claim.claim_status.notin_([CLAIM_STATUS_REJECTED, CLAIM_STATUS_CLOSED]),
        Claim.fault_date >= cutoff_date
    ).all()

    duplicates = []

    for other in existing_claims:
        score = 0.0
        reasons = []

        # Fault description similarity
        desc_sim = _text_similarity(
            claim.fault_description or "",
            other.fault_description or ""
        )
        if desc_sim >= SIMILARITY_THRESHOLD:
            score += 0.5
            reasons.append(f"Fault description similarity: {desc_sim:.0%}")

        # Damage type match
        own_damage = _normalize_text(claim.damage_type or "")
        other_damage = _normalize_text(other.damage_type or "")
        if own_damage and other_damage and own_damage == other_damage:
            score += 0.3
            reasons.append("Same damage type")
        elif own_damage and other_damage and _text_similarity(own_damage, other_damage) > 0.5:
            score += 0.15
            reasons.append("Similar damage type")

        # Close submission dates
        if claim.fault_date and other.fault_date:
            day_diff = abs((claim.fault_date - other.fault_date).days)
            if day_diff <= 7:
                score += 0.2
                reasons.append(f"Fault dates within {day_diff} days")
            elif day_diff <= 30:
                score += 0.1
                reasons.append(f"Fault dates within {day_diff} days")

        if score >= 0.5:
            duplicates.append({
                "claim_uid": other.claim_uid,
                "claim_id": other.id,
                "claim_status": other.claim_status,
                "fault_date": other.fault_date.isoformat() if other.fault_date else None,
                "damage_type": other.damage_type,
                "similarity_score": round(score, 3),
                "duplicate_signals": reasons
            })

    duplicates.sort(key=lambda x: x["similarity_score"], reverse=True)
    return duplicates


def check_duplicate_and_flag(claim: Claim) -> Dict[str, Any]:
    """
    Run duplicate detection for a claim and return structured result.

    Returns:
        dict with is_duplicate, duplicates list, and recommendation.
    """
    try:
        duplicates = find_duplicate_claims(claim)
    except Exception as e:
        logger.error("Duplicate detection error for claim %s: %s", claim.claim_uid, e)
        return {
            "is_duplicate": False,
            "duplicates": [],
            "recommendation": "proceed",
            "error": str(e)
        }

    if not duplicates:
        return {
            "is_duplicate": False,
            "duplicates": [],
            "recommendation": "proceed"
        }

    high_confidence = [d for d in duplicates if d["similarity_score"] >= 0.8]

    return {
        "is_duplicate": len(high_confidence) > 0,
        "potential_duplicates": len(duplicates),
        "high_confidence_duplicates": len(high_confidence),
        "duplicates": duplicates[:5],
        "recommendation": "flag_for_review" if high_confidence else "soft_flag",
        "note": (
            f"Found {len(duplicates)} similar claim(s) for this product. "
            f"{len(high_confidence)} high-confidence duplicate(s)."
        )
    }
