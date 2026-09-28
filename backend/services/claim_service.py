"""
AssureX Claim Service
Business logic foundation for warranty claim creation, input validation,
product age calculation, evidence document processing, and storage.
"""

import os
import logging
from datetime import date, datetime
from typing import Optional, List, Tuple, Dict, Any
from flask import current_app
from backend.extensions import db

logger = logging.getLogger(__name__)
from backend.models import (
    User,
    Product,
    Warranty,
    Claim,
    Document,
    CLAIM_STATUS_DRAFT,
    CLAIM_STATUS_SUBMITTED,
    DOC_TYPE_RECEIPT,
    DOC_TYPE_INVOICE,
    DOC_TYPE_WARRANTY_CARD,
    DOC_TYPE_DAMAGE_PHOTO,
    DOC_TYPE_SERIAL_PHOTO,
    DOC_TYPE_DIAGNOSTIC_REPORT,
    DOC_TYPE_OTHER,
    VALID_DOCUMENT_TYPES
)
from backend.services.audit_service import log_audit_event
from backend.utils.file_handler import (
    validate_claim_file,
    save_claim_document,
    MAX_CLAIM_FILE_SIZE
)
from backend.utils.helpers import generate_uid, utc_now
from backend.utils.security import (
    ROLE_CUSTOMER,
    ROLE_SERVICE_CENTER,
    ROLE_ADMIN,
    ROLE_REVIEWER
)

# Standard damage types recognized by the claim engine
STANDARD_DAMAGE_TYPES = [
    "Screen / Display Defect",
    "Power / Battery Failure",
    "Motherboard / Circuitry Failure",
    "Speaker / Audio Malfunction",
    "Camera / Sensor Malfunction",
    "Keyboard / Button Failure",
    "Overheating / Thermal Throttling",
    "Water / Liquid Ingress",
    "Physical Impact / Casing Damage",
    "Connectivity / Network Failure",
    "Other Hardware Malfunction"
]


def calculate_product_age_months(purchase_date: date, as_of_date: Optional[date] = None) -> int:
    """
    Calculate the age of a product in whole months as of a given date (default today).
    """
    if as_of_date is None:
        as_of_date = date.today()

    if as_of_date < purchase_date:
        return 0

    months = (as_of_date.year - purchase_date.year) * 12 + (as_of_date.month - purchase_date.month)
    if as_of_date.day < purchase_date.day and months > 0:
        months -= 1
    return max(0, months)


def parse_and_validate_fault_date(
    fault_date_input: Any,
    purchase_date: date
) -> Tuple[bool, Optional[date], Optional[str]]:
    """
    Validate fault date:
    - Must be a valid date
    - Must not be in the future
    - Must not precede the product's purchase date
    """
    if not fault_date_input:
        return False, None, "Fault occurrence date is required."

    if isinstance(fault_date_input, date):
        parsed_date = fault_date_input
    elif isinstance(fault_date_input, str):
        try:
            parsed_date = datetime.strptime(fault_date_input.strip(), "%Y-%m-%d").date()
        except ValueError:
            return False, None, "Invalid fault date format. Please use YYYY-MM-DD."
    else:
        return False, None, "Invalid fault date format."

    today = date.today()
    if parsed_date > today:
        return False, None, "Fault date cannot be in the future."

    if parsed_date < purchase_date:
        return False, None, f"Fault date ({parsed_date.isoformat()}) cannot be prior to product purchase date ({purchase_date.isoformat()})."

    return True, parsed_date, None


def validate_claim_data(
    user: User,
    product: Product,
    fault_date_input: Any,
    fault_description: str,
    damage_type: str,
    purchase_reference: Optional[str] = None,
    service_history_notes: Optional[str] = None,
    claim_status: str = CLAIM_STATUS_SUBMITTED
) -> Tuple[bool, List[str], Dict[str, Any]]:
    """
    Comprehensive server-side validation for warranty claim registration.
    """
    errors: List[str] = []
    parsed_data: Dict[str, Any] = {}

    # 1. Product ownership check (IDOR protection)
    # Customers can strictly ONLY file claims on their own products.
    # Service-Centre Employees and Admins may file claims on behalf of a customer.
    if user.role == ROLE_CUSTOMER and product.user_id != user.id:
        errors.append("You do not have permission to file a claim for this product.")

    # 2. Product purchase date & fault date
    is_valid_date, parsed_fault_date, date_err = parse_and_validate_fault_date(
        fault_date_input,
        product.purchase_date
    )
    if not is_valid_date:
        errors.append(date_err)
    else:
        parsed_data["fault_date"] = parsed_fault_date
        # Compute product age in months at time of fault
        parsed_data["product_age"] = calculate_product_age_months(
            product.purchase_date,
            parsed_fault_date
        )

    # 3. Fault description validation
    clean_desc = (fault_description or "").strip()
    if not clean_desc:
        errors.append("Fault description is required.")
    elif len(clean_desc) < 10:
        errors.append("Fault description must be at least 10 characters detailing the issue.")
    elif len(clean_desc) > 3000:
        errors.append("Fault description exceeds the 3000 character limit.")
    else:
        parsed_data["fault_description"] = clean_desc

    # 4. Damage type validation
    clean_damage = (damage_type or "").strip()
    if not clean_damage:
        errors.append("Damage/fault type is required.")
    elif len(clean_damage) > 100:
        errors.append("Damage type label exceeds 100 characters.")
    else:
        parsed_data["damage_type"] = clean_damage

    # 5. Purchase reference
    clean_pref = (purchase_reference or "").strip()
    if clean_pref and len(clean_pref) > 150:
        errors.append("Purchase reference cannot exceed 150 characters.")
    parsed_data["purchase_reference"] = clean_pref if clean_pref else None

    # 6. Service history reference notes
    clean_snotes = (service_history_notes or "").strip()
    if clean_snotes and len(clean_snotes) > 2000:
        errors.append("Service history notes cannot exceed 2000 characters.")
    parsed_data["service_history_notes"] = clean_snotes if clean_snotes else None

    # 7. Status validation
    if claim_status not in (CLAIM_STATUS_DRAFT, CLAIM_STATUS_SUBMITTED):
        claim_status = CLAIM_STATUS_SUBMITTED
    parsed_data["claim_status"] = claim_status

    return (len(errors) == 0, errors, parsed_data)


def validate_required_claim_documents(
    uploaded_items: List[Tuple[Any, str]],
    is_submission: bool = True
) -> Tuple[bool, List[str]]:
    """
    Validate presence and validity of required documents at claim submission.
    For Submitted claims:
      - Receipt or Invoice is MANDATORY
      - Damage Photo / Evidence is MANDATORY
    For Draft claims:
      - Files are validated if provided, but mandatory documents are not strictly blocked.
    """
    errors: List[str] = []

    has_receipt = False
    has_damage_photo = False

    for file_storage, doc_type in uploaded_items:
        if not file_storage or not getattr(file_storage, "filename", None):
            continue

        # File integrity / security check
        is_valid_file, file_err = validate_claim_file(file_storage, MAX_CLAIM_FILE_SIZE)
        if not is_valid_file:
            errors.append(f"Document [{doc_type}]: {file_err}")
            continue

        if doc_type not in VALID_DOCUMENT_TYPES:
            errors.append(f"Invalid document type '{doc_type}'.")
            continue

        if doc_type in (DOC_TYPE_RECEIPT, DOC_TYPE_INVOICE):
            has_receipt = True
        elif doc_type == DOC_TYPE_DAMAGE_PHOTO:
            has_damage_photo = True

    if is_submission:
        if not has_receipt:
            errors.append("Proof of purchase (Receipt or Invoice) is required for claim submission.")
        if not has_damage_photo:
            errors.append("Damage or fault photo evidence is required for claim submission.")

    return (len(errors) == 0, errors)


def register_claim(
    user: User,
    product: Product,
    fault_date_input: Any,
    fault_description: str,
    damage_type: str,
    uploaded_files: List[Tuple[Any, str]],
    purchase_reference: Optional[str] = None,
    service_history_notes: Optional[str] = None,
    claim_status: str = CLAIM_STATUS_SUBMITTED,
    upload_root: Optional[str] = None
) -> Tuple[bool, List[str], Optional[Claim]]:
    """
    Orchestrate full Step 5A Claim Registration workflow:
    1. Validates claim data & product relationship
    2. Validates required documents
    3. Saves files securely in <upload_root>/claims/<claim_uid>/
    4. Creates Claim & Document database entities
    5. Records Audit Log entry
    """
    if upload_root is None:
        upload_root = current_app.config.get("UPLOAD_FOLDER", "uploads")

    # Determine submission mode
    is_submitting = (claim_status == CLAIM_STATUS_SUBMITTED)

    # 1. Validate Form Data
    is_valid_data, data_errors, clean_data = validate_claim_data(
        user=user,
        product=product,
        fault_date_input=fault_date_input,
        fault_description=fault_description,
        damage_type=damage_type,
        purchase_reference=purchase_reference,
        service_history_notes=service_history_notes,
        claim_status=claim_status
    )

    # 2. Validate Documents
    is_valid_docs, doc_errors = validate_required_claim_documents(
        uploaded_items=uploaded_files,
        is_submission=is_submitting
    )

    all_errors = data_errors + doc_errors
    if all_errors:
        return False, all_errors, None

    # 3. Locate linked warranty if one exists for product
    warranty_id = None
    if product.warranties:
        # Link to most applicable warranty (first one or active one)
        active_warranties = [w for w in product.warranties if w.is_active()]
        warranty_id = active_warranties[0].id if active_warranties else product.warranties[0].id

    # 4. Generate unique Claim UID and create Claim
    claim_uid = generate_uid("CLM")
    claim = Claim(
        claim_uid=claim_uid,
        user_id=product.user_id,  # Product owner is always the claimant
        product_id=product.id,
        warranty_id=warranty_id,
        fault_date=clean_data["fault_date"],
        fault_description=clean_data["fault_description"],
        damage_type=clean_data["damage_type"],
        product_age=clean_data["product_age"],
        purchase_reference=clean_data["purchase_reference"],
        service_history_notes=clean_data["service_history_notes"],
        claim_status=clean_data["claim_status"],
        submission_date=utc_now()
    )
    db.session.add(claim)
    db.session.flush()  # Populate claim.id

    # 5. Process and store documents securely
    created_docs = []
    for file_storage, doc_type in uploaded_files:
        if not file_storage or not getattr(file_storage, "filename", None):
            continue

        doc_uid = generate_uid("DOC")
        saved_meta = save_claim_document(
            file_storage=file_storage,
            upload_root=upload_root,
            claim_uid=claim_uid,
            doc_uid=doc_uid
        )

        doc = Document(
            document_uid=doc_uid,
            claim_id=claim.id,
            product_id=product.id,
            user_id=user.id,
            document_type=doc_type,
            original_filename=saved_meta["original_filename"],
            stored_filename=saved_meta["stored_filename"],
            stored_path=saved_meta["relative_path"],
            file_extension=saved_meta["file_extension"],
            mime_type=saved_meta["mime_type"],
            file_size=saved_meta["file_size"],
            file_hash=saved_meta["file_hash"]
        )
        db.session.add(doc)
        created_docs.append(doc)

    db.session.commit()

    # 5B: Trigger OCR automatically for each uploaded document
    # OCR failure must NEVER block or fail the claim registration.
    for doc in created_docs:
        try:
            from backend.services.document_extraction_service import process_document_ocr
            process_document_ocr(doc, upload_root)
        except Exception as ocr_err:
            logger.warning(
                "OCR auto-processing failed for document %s: %s",
                doc.document_uid, ocr_err
            )

    # 6. Log Audit Event
    log_audit_event(
        action="CLAIM_REGISTERED",
        entity_type="Claim",
        entity_id=claim.claim_uid,
        user_id=user.id,
        description=f"Claim {claim.claim_uid} ({claim.claim_status}) registered for product {product.product_uid} with {len(created_docs)} documents."
    )

    return True, [], claim


def add_document_to_claim(
    claim: Claim,
    file_storage: Any,
    document_type: str,
    user: User,
    upload_root: Optional[str] = None
) -> Tuple[bool, Optional[str], Optional[Document]]:
    """
    Attach an additional evidence document to an existing claim.
    """
    if upload_root is None:
        upload_root = current_app.config.get("UPLOAD_FOLDER", "uploads")

    # Validate file
    is_valid, err = validate_claim_file(file_storage, MAX_CLAIM_FILE_SIZE)
    if not is_valid:
        return False, err, None

    if document_type not in VALID_DOCUMENT_TYPES:
        return False, f"Invalid document type '{document_type}'.", None

    doc_uid = generate_uid("DOC")
    saved_meta = save_claim_document(
        file_storage=file_storage,
        upload_root=upload_root,
        claim_uid=claim.claim_uid,
        doc_uid=doc_uid
    )

    doc = Document(
        document_uid=doc_uid,
        claim_id=claim.id,
        product_id=claim.product_id,
        user_id=user.id,
        document_type=document_type,
        original_filename=saved_meta["original_filename"],
        stored_filename=saved_meta["stored_filename"],
        stored_path=saved_meta["relative_path"],
        file_extension=saved_meta["file_extension"],
        mime_type=saved_meta["mime_type"],
        file_size=saved_meta["file_size"],
        file_hash=saved_meta["file_hash"]
    )
    db.session.add(doc)
    db.session.commit()

    # 5B: Trigger OCR automatically for the newly added document.
    # Failure must never block the document upload success.
    try:
        from backend.services.document_extraction_service import process_document_ocr
        process_document_ocr(doc, upload_root)
    except Exception as ocr_err:
        logger.warning(
            "OCR auto-processing failed for document %s: %s",
            doc.document_uid, ocr_err
        )

    log_audit_event(
        action="CLAIM_DOCUMENT_ADDED",
        entity_type="Document",
        entity_id=doc.document_uid,
        user_id=user.id,
        description=f"Document {doc.document_uid} ({document_type}) attached to claim {claim.claim_uid}."
    )

    return True, None, doc
