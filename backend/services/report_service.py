"""
AssureX Report Service
Generates structured claim evaluation reports for reviewers, admins,
and customers. Reports include claim summary, rule results, AI predictions,
and final decision with reasoning.
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional, List

from backend.models.claim import Claim
from backend.models.prediction import Prediction
from backend.models.rule_result import RuleResult
from backend.services.analytics_service import get_full_analytics_data

logger = logging.getLogger(__name__)


def generate_claim_evaluation_report(claim: Claim) -> Dict[str, Any]:
    """
    Generate a full evaluation report for a single claim.
    Includes claim details, product/warranty info, rule results,
    AI predictions, and the final decision.
    """
    product = claim.product
    warranty = claim.warranty
    documents = claim.documents or []
    rule_results = claim.rule_results or []
    predictions = claim.predictions or []
    extractions = claim.extractions or []

    # Latest AI prediction
    latest_prediction = None
    if predictions:
        latest_prediction = sorted(predictions, key=lambda p: p.id, reverse=True)[0]

    # Rule results summary
    passed_rules = [r for r in rule_results if r.rule_status == "Passed"]
    failed_rules = [r for r in rule_results if r.rule_status == "Failed"]
    warning_rules = [r for r in rule_results if r.rule_status == "Warning"]

    # Document list
    doc_list = []
    for doc in documents:
        doc_list.append({
            "uid": doc.document_uid,
            "type": doc.document_type,
            "filename": doc.original_filename,
            "uploaded_at": doc.upload_timestamp.isoformat() if doc.upload_timestamp else None
        })

    # OCR extraction summary
    extraction_summary = []
    for ext in extractions:
        extraction_summary.append({
            "document_uid": ext.document_uid if hasattr(ext, "document_uid") else None,
            "extraction_status": getattr(ext, "extraction_status", None),
            "verification_status": getattr(ext, "verification_status", None)
        })

    report = {
        "report_type": "Claim Evaluation Report",
        "generated_at": datetime.utcnow().isoformat(),
        "claim": {
            "uid": claim.claim_uid,
            "status": claim.claim_status,
            "final_decision": claim.final_decision,
            "fault_date": claim.fault_date.isoformat() if claim.fault_date else None,
            "damage_type": claim.damage_type,
            "product_age_months": claim.product_age,
            "fault_description": claim.fault_description,
            "submission_date": claim.submission_date.isoformat() if claim.submission_date else None,
            "purchase_reference": claim.purchase_reference
        },
        "product": product.to_dict() if product else None,
        "warranty": warranty.to_dict() if warranty else None,
        "documents": {
            "count": len(documents),
            "list": doc_list
        },
        "rule_engine": {
            "total_rules": len(rule_results),
            "passed": len(passed_rules),
            "failed": len(failed_rules),
            "warnings": len(warning_rules),
            "results": [r.to_dict() for r in rule_results]
        },
        "ai_prediction": {
            "total_predictions": len(predictions),
            "latest": latest_prediction.to_dict() if latest_prediction else None,
            "all_predictions": [p.to_dict() for p in predictions]
        },
        "ocr_extractions": extraction_summary,
        "recommendation": _derive_report_recommendation(claim, failed_rules, latest_prediction)
    }

    return report


def _derive_report_recommendation(claim, failed_rules, latest_prediction) -> str:
    """Derive a human-readable recommendation line for the report."""
    decision = claim.final_decision

    if decision == "Approved":
        return "Claim passes all evaluation criteria and is recommended for approval."
    elif decision == "Rejected":
        reasons = [r.rule_result for r in failed_rules if r.rule_result]
        if reasons:
            return f"Claim rejected due to: {'; '.join(reasons[:3])}."
        return "Claim does not meet warranty coverage requirements."
    elif decision == "Manual Review":
        return "Claim requires manual reviewer attention due to mixed or inconclusive evaluation signals."
    else:
        return "Claim evaluation pending. Run the full evaluation pipeline to determine decision."


def generate_batch_report(claims: List[Claim]) -> Dict[str, Any]:
    """
    Generate a summary batch report for multiple claims.
    Used for admin/reviewer overview exports.
    """
    rows = []
    for claim in claims:
        latest_pred = None
        if claim.predictions:
            latest_pred = sorted(claim.predictions, key=lambda p: p.id, reverse=True)[0]

        rows.append({
            "claim_uid": claim.claim_uid,
            "status": claim.claim_status,
            "final_decision": claim.final_decision,
            "damage_type": claim.damage_type,
            "product_age_months": claim.product_age,
            "fault_date": claim.fault_date.isoformat() if claim.fault_date else None,
            "submission_date": claim.submission_date.isoformat() if claim.submission_date else None,
            "documents_count": len(claim.documents or []),
            "rules_failed": sum(1 for r in (claim.rule_results or []) if r.rule_status == "Failed"),
            "ai_prediction": latest_pred.predicted_class if latest_pred else None,
            "ai_confidence": latest_pred.valid_confidence if latest_pred else None
        })

    approved = sum(1 for r in rows if r["final_decision"] == "Approved")
    rejected = sum(1 for r in rows if r["final_decision"] == "Rejected")
    manual = sum(1 for r in rows if r["final_decision"] == "Manual Review")

    return {
        "report_type": "Batch Claims Report",
        "generated_at": datetime.utcnow().isoformat(),
        "total_claims": len(rows),
        "summary": {
            "approved": approved,
            "rejected": rejected,
            "manual_review": manual,
            "pending": len(rows) - approved - rejected - manual
        },
        "claims": rows
    }


def generate_system_analytics_report() -> Dict[str, Any]:
    """Generate a full system analytics report."""
    analytics = get_full_analytics_data()
    analytics["report_type"] = "System Analytics Report"
    analytics["generated_at"] = datetime.utcnow().isoformat()
    return analytics


# ---------------------------------------------------------------------------
# PDF Report Generator
# ---------------------------------------------------------------------------

def generate_claim_pdf(claim: Claim) -> bytes:
    """
    Generate a downloadable PDF claim evaluation report using fpdf2.
    Returns the PDF as raw bytes ready for Flask's make_response().
    """
    from fpdf import FPDF

    report = generate_claim_evaluation_report(claim)

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # ── Header bar ──────────────────────────────────────────────────────────
    pdf.set_fill_color(30, 30, 46)          # dark background
    pdf.rect(0, 0, 210, 22, style="F")
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(139, 92, 246)        # purple
    pdf.set_xy(10, 5)
    pdf.cell(0, 12, "AssureX  Claim Evaluation Report", ln=True)

    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(180, 180, 200)
    pdf.set_xy(10, 15)
    pdf.cell(0, 5, f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}", ln=True)
    pdf.ln(6)

    # ── Helper closures ──────────────────────────────────────────────────────
    def section_title(text: str) -> None:
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(139, 92, 246)
        pdf.cell(0, 7, text, ln=True)
        pdf.set_draw_color(139, 92, 246)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(2)
        pdf.set_text_color(30, 30, 30)

    def row(label: str, value: str) -> None:
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(80, 80, 100)
        pdf.cell(55, 6, label + ":", ln=False)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(30, 30, 30)
        pdf.cell(0, 6, str(value or "—"), ln=True)

    # ── Claim Details ────────────────────────────────────────────────────────
    section_title("Claim Details")
    c = report.get("claim", {})
    row("Claim UID",       c.get("uid", ""))
    row("Status",          c.get("status", ""))
    row("Final Decision",  c.get("final_decision", "Pending"))
    row("Damage Type",     c.get("damage_type", ""))
    row("Fault Date",      c.get("fault_date", ""))
    row("Submission Date", c.get("submission_date", ""))
    row("Product Age",     f"{c.get('product_age_months', '')} months")
    pdf.ln(3)

    # ── Product & Warranty ───────────────────────────────────────────────────
    section_title("Product & Warranty")
    p = report.get("product") or {}
    w = report.get("warranty") or {}
    row("Brand / Model",   f"{p.get('brand', '')} {p.get('model', '')}")
    row("Serial Number",   p.get("serial_number", ""))
    row("Category",        p.get("category", ""))
    row("Warranty Status", w.get("warranty_status", ""))
    row("Expiry Date",     w.get("expiry_date", ""))
    pdf.ln(3)

    # ── Rule Engine Results ──────────────────────────────────────────────────
    section_title("Warranty Rule Engine")
    re_data = report.get("rule_engine", {})
    row("Rules Run",    str(re_data.get("total_rules", 0)))
    row("Passed",       str(re_data.get("passed", 0)))
    row("Failed",       str(re_data.get("failed", 0)))
    row("Warnings",     str(re_data.get("warnings", 0)))
    pdf.ln(1)

    for r in re_data.get("results", []):
        status_sym = "✓" if r.get("rule_status") == "Passed" else ("✗" if r.get("rule_status") == "Failed" else "!")
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(60, 60, 80)
        pdf.cell(6, 5, status_sym, ln=False)
        pdf.cell(60, 5, r.get("rule_name", ""), ln=False)
        pdf.set_text_color(100, 100, 120)
        detail = str(r.get("details", ""))[:80]
        pdf.cell(0, 5, detail, ln=True)
    pdf.ln(3)

    # ── AI Prediction ────────────────────────────────────────────────────────
    section_title("AI Model Prediction")
    ai = report.get("ai_prediction", {})
    latest = ai.get("latest") or {}
    if latest:
        row("Predicted Class",  latest.get("predicted_class", ""))
        row("Confidence",       f"{float(latest.get('confidence', 0)) * 100:.1f}%")
        row("Valid Confidence", f"{float(latest.get('valid_confidence', 0)) * 100:.1f}%")
        row("Invalid Conf.",    f"{float(latest.get('invalid_confidence', 0)) * 100:.1f}%")
        row("Manual Rev. Conf.",f"{float(latest.get('manual_review_confidence', 0)) * 100:.1f}%")
    else:
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(120, 120, 140)
        pdf.cell(0, 6, "No AI prediction available for this claim.", ln=True)
    pdf.ln(3)

    # ── Documents ────────────────────────────────────────────────────────────
    section_title("Submitted Documents")
    docs = report.get("documents", {})
    row("Total Documents", str(docs.get("count", 0)))
    for doc in docs.get("list", []):
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(60, 60, 80)
        pdf.cell(6, 5, "-", ln=False)
        pdf.cell(50, 5, doc.get("type", ""), ln=False)
        pdf.set_text_color(100, 100, 120)
        pdf.cell(0, 5, doc.get("filename", ""), ln=True)
    pdf.ln(3)

    # ── Final Recommendation ─────────────────────────────────────────────────
    section_title("Final Recommendation")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(30, 30, 30)
    recommendation = report.get("recommendation", "")
    pdf.multi_cell(0, 6, recommendation)
    pdf.ln(3)

    # ── Decision Reasoning ───────────────────────────────────────────────────
    reasoning = getattr(claim, "decision_reasoning", "") or ""
    if reasoning:
        section_title("Decision Reasoning")
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(60, 60, 80)
        pdf.multi_cell(0, 5, reasoning[:800])
        pdf.ln(3)

    # ── Footer ───────────────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "I", 7)
    pdf.set_text_color(160, 160, 180)
    pdf.cell(0, 5, "AssureX Claim Engine  —  Auto-generated report  —  For official use only", ln=True, align="C")

    return bytes(pdf.output())
