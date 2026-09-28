"""
AssureX Claim Summary Service
Generates human-readable plain-text summaries of claim evaluations
for display in dashboards, notifications, and reports.
"""

from typing import Dict, Any, Optional
from backend.models.claim import Claim


def generate_claim_summary(claim: Claim) -> str:
    """
    Generate a concise plain-text summary of a claim and its evaluation state.
    """
    product = claim.product
    warranty = claim.warranty

    product_name = f"{product.brand} {product.model}" if product else "Unknown Product"
    product_serial = product.serial_number if product else "N/A"

    fault_date_str = claim.fault_date.strftime("%d %B %Y") if claim.fault_date else "Unknown"
    submission_str = claim.submission_date.strftime("%d %B %Y") if claim.submission_date else "Unknown"

    warranty_status = "No warranty linked"
    if warranty:
        warranty_status = warranty.calculate_status()

    rule_results = claim.rule_results or []
    passed = sum(1 for r in rule_results if r.rule_status == "Passed")
    failed = sum(1 for r in rule_results if r.rule_status == "Failed")

    predictions = claim.predictions or []
    ai_summary = "No AI prediction available."
    if predictions:
        latest = sorted(predictions, key=lambda p: p.id, reverse=True)[0]
        ai_summary = (
            f"AI model predicted: {latest.predicted_class} "
            f"(confidence: {latest.valid_confidence:.0%} valid / "
            f"{latest.invalid_confidence:.0%} invalid)."
        )

    decision = claim.final_decision or "Pending"

    summary_lines = [
        f"Claim Reference: {claim.claim_uid}",
        f"Product: {product_name} | Serial: {product_serial}",
        f"Fault Date: {fault_date_str} | Submitted: {submission_str}",
        f"Damage Type: {claim.damage_type or 'Not specified'}",
        f"Product Age at Claim: {claim.product_age or 'Unknown'} months",
        f"Warranty Status: {warranty_status}",
        f"Documents Submitted: {len(claim.documents or [])}",
        f"Rule Engine: {passed} passed, {failed} failed out of {len(rule_results)} rules.",
        ai_summary,
        f"Current Status: {claim.claim_status}",
        f"Final Decision: {decision}"
    ]

    return "\n".join(summary_lines)


def generate_decision_explanation(claim: Claim) -> Dict[str, Any]:
    """
    Generate a structured explanation of why a claim received its final decision.
    Useful for customer-facing decision letters.
    """
    decision = claim.final_decision or "Pending"
    status = claim.claim_status

    rule_results = claim.rule_results or []
    failed_rules = [r for r in rule_results if r.rule_status == "Failed"]
    passed_rules = [r for r in rule_results if r.rule_status == "Passed"]

    predictions = claim.predictions or []
    latest_pred = None
    if predictions:
        latest_pred = sorted(predictions, key=lambda p: p.id, reverse=True)[0]

    reasons = []
    if decision == "Approved":
        reasons.append("All required warranty conditions were satisfied.")
        reasons.append("Submitted documentation was verified successfully.")
        if latest_pred and latest_pred.predicted_class == "Valid":
            reasons.append(f"AI validation confirmed claim validity ({latest_pred.valid_confidence:.0%} confidence).")

    elif decision == "Rejected":
        for rule in failed_rules:
            reasons.append(f"{rule.rule_name}: {rule.rule_result} — {rule.details or ''}")
        if latest_pred and latest_pred.predicted_class == "Invalid":
            reasons.append(f"AI model classified claim as invalid ({latest_pred.invalid_confidence:.0%} confidence).")

    elif decision == "Manual Review":
        reasons.append("Claim requires additional human review due to mixed evaluation signals.")
        if failed_rules:
            reasons.append(f"{len(failed_rules)} rule check(s) failed; manual verification needed.")
        if latest_pred and latest_pred.predicted_class == "Manual Review":
            reasons.append("AI model flagged claim for manual review.")

    else:
        reasons.append("Claim evaluation is in progress. A decision will be communicated shortly.")

    return {
        "claim_uid": claim.claim_uid,
        "decision": decision,
        "status": status,
        "reasons": reasons,
        "passed_rules_count": len(passed_rules),
        "failed_rules_count": len(failed_rules),
        "ai_prediction": latest_pred.predicted_class if latest_pred else None,
        "ai_confidence": float(latest_pred.valid_confidence or 0) if latest_pred else None
    }
