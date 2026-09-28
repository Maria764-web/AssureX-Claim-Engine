"""
AssureX Preprocessing Service
Extracts and transforms claim attributes into structured feature dictionaries for AI model input.
"""

import re
from typing import Dict, Any
import pandas as pd


def extract_features_from_claim(claim) -> Dict[str, Any]:
    """
    Extract raw feature dictionary from a Claim model instance.
    Includes product details, warranty status, documents, and historical records.
    Explicitly excludes Claim_ID.
    """
    product = getattr(claim, "product", None)
    warranty = getattr(claim, "warranty", None)

    # 1. Product Category
    product_category = "Unknown"
    if product:
        if hasattr(product, "category") and product.category:
            product_category = str(product.category)
        elif hasattr(product, "product_name") and product.product_name:
            product_category = str(product.product_name)

    # 2. Product Age Months
    product_age = 0
    if getattr(claim, "product_age", None) is not None:
        product_age = int(claim.product_age)
    elif product and getattr(product, "purchase_date", None) and getattr(claim, "fault_date", None):
        delta_days = (claim.fault_date - product.purchase_date).days
        product_age = max(0, int(delta_days / 30.4375))

    # 3. Warranty Duration Months
    warranty_duration = 0
    if warranty and getattr(warranty, "duration_months", None):
        warranty_duration = int(warranty.duration_months)
    elif product and getattr(product, "warranty_duration", None):
        warranty_duration = int(product.warranty_duration)

    # 4. Warranty Status
    warranty_status = "Unknown"
    if warranty:
        try:
            warranty_status = warranty.calculate_status()
        except Exception:
            warranty_status = getattr(warranty, "warranty_status", "Unknown")

    # 5. Document availability
    receipt_available = "No"
    warranty_card_available = "No"
    damage_photo_available = "No"
    missing_document = "No"

    documents = getattr(claim, "documents", []) or []
    doc_types = [getattr(doc, "document_type", "") for doc in documents]

    for dt in doc_types:
        dt_lower = (dt or "").lower()
        if "receipt" in dt_lower or "invoice" in dt_lower:
            receipt_available = "Yes"
        if "warranty" in dt_lower or "card" in dt_lower:
            warranty_card_available = "Yes"
        if "photo" in dt_lower or "image" in dt_lower or "diagnostic" in dt_lower or "damage" in dt_lower:
            damage_photo_available = "Yes"

    if receipt_available == "No":
        missing_document = "Yes"

    # 6. Serial Number Status
    serial_status = "Unknown"
    extractions = getattr(claim, "extractions", []) or []
    extracted_serials = []
    for ext in extractions:
        vf = getattr(ext, "verified_fields", {}) or {}
        ef = getattr(ext, "extracted_fields", {}) or {}
        sn = vf.get("serial_number") or ef.get("serial_number")
        if sn:
            extracted_serials.append(str(sn).strip().lower())

    if product and getattr(product, "serial_number", None):
        prod_sn = str(product.serial_number).strip().lower()
        if extracted_serials:
            if any(sn == prod_sn for sn in extracted_serials):
                serial_status = "Match"
            else:
                serial_status = "Mismatch"
        else:
            serial_status = "Match"
    elif extracted_serials:
        serial_status = "Match"

    # 7. Damage Covered & Contradiction
    damage_covered = "Yes"
    contradiction_detected = "No"

    rule_results = getattr(claim, "rule_results", []) or []
    for rr in rule_results:
        if hasattr(rr, "passed") and not rr.passed:
            damage_covered = "No"

    # Use dedicated contradiction detection service
    try:
        from backend.services.contradiction_detection import detect_contradictions
        contra_result = detect_contradictions(claim)
        if contra_result.get("contradictions_found"):
            contradiction_detected = "Yes"
    except Exception:
        pass

    # 8. Document Quality Score
    document_quality = 0.8
    if extractions:
        statuses = [getattr(e, "verification_status", None) for e in extractions]
        if "VERIFIED" in statuses or "Confirmed" in statuses:
            document_quality = 0.95
        elif "PENDING" in statuses:
            document_quality = 0.75
    elif len(documents) > 0:
        document_quality = 0.85
    else:
        document_quality = 0.50

    # 9. Damage Severity Score
    damage_severity = 3.0
    dtype = (getattr(claim, "damage_type", "") or "").lower()
    fdesc = (getattr(claim, "fault_description", "") or "").lower()
    if "total" in dtype or "broken" in dtype or "crack" in fdesc or "water" in fdesc:
        damage_severity = 4.5
    elif "minor" in dtype or "scratch" in fdesc or "light" in fdesc:
        damage_severity = 1.5

    # 10. Previous Repair Count
    repair_histories = getattr(claim, "repair_histories", []) or []
    previous_repairs = len(repair_histories)

    # 11. Claim Amount
    claim_amount = 0.0
    if extractions:
        for ext in extractions:
            vf = getattr(ext, "verified_fields", {}) or {}
            ef = getattr(ext, "extracted_fields", {}) or {}
            price_str = vf.get("purchase_price") or ef.get("purchase_price")
            if price_str:
                try:
                    clean = re.sub(r"[^\d.]", "", str(price_str))
                    if clean:
                        claim_amount = float(clean)
                        break
                except ValueError:
                    pass
    if claim_amount == 0.0 and product and getattr(product, "purchase_price", None):
        try:
            claim_amount = float(product.purchase_price)
        except (ValueError, TypeError):
            claim_amount = 0.0

    return {
        "Product_Category": product_category,
        "Product_Age_Months": product_age,
        "Warranty_Duration_Months": warranty_duration,
        "Warranty_Status": warranty_status,
        "Receipt_Available": receipt_available,
        "Warranty_Card_Available": warranty_card_available,
        "Damage_Photo_Available": damage_photo_available,
        "Serial_Number_Status": serial_status,
        "Damage_Covered": damage_covered,
        "Contradiction_Detected": contradiction_detected,
        "Missing_Document": missing_document,
        "Document_Quality_Score": document_quality,
        "Damage_Severity_Score": damage_severity,
        "Previous_Repair_Count": previous_repairs,
        "Claim_Amount": claim_amount
    }


def prepare_feature_matrix(raw_data: Dict[str, Any], feature_columns: list) -> pd.DataFrame:
    """
    Construct a pandas DataFrame, apply get_dummies categorical encoding,
    and align columns strictly with feature_columns.
    - Missing expected columns are assigned 0.
    - Unexpected extra columns are ignored.
    - Column order matches feature_columns exactly.
    - Claim_ID is never used as a prediction feature.
    """
    clean_data = {k: v for k, v in raw_data.items() if k != "Claim_ID"}
    df = pd.DataFrame([clean_data])
    df_encoded = pd.get_dummies(df)
    df_aligned = df_encoded.reindex(columns=feature_columns, fill_value=0)
    return df_aligned
