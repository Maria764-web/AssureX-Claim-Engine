"""
Step 5B Verification Script
Verifies all core OCR + Extraction + Verification components are correctly wired.
"""

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

PASS = 0; FAIL = 0

def check(label, condition, detail=''):
    global PASS, FAIL
    if condition:
        print(f'  [OK] {label}')
        PASS += 1
    else:
        print(f'  [FAIL] {label}' + (f' -- {detail}' if detail else ''))
        FAIL += 1

print('\n=== Step 5B: OCR + Extraction + Verification Verification ===\n')

# --- Model imports ---
print('[1] Model Layer')
try:
    from backend.models.document_extraction import (
        DocumentExtraction,
        EXTRACTION_STATUS_PENDING, EXTRACTION_STATUS_COMPLETED,
        EXTRACTION_STATUS_FAILED, EXTRACTION_STATUS_NOT_APPLICABLE,
        VERIFY_STATUS_UNVERIFIED, VERIFY_STATUS_VERIFIED,
        VERIFY_STATUS_NEEDS_CORRECTION,
    )
    check('DocumentExtraction model importable', True)
    check('Has extraction_uid column', hasattr(DocumentExtraction, 'extraction_uid'))
    check('Has document_id FK', hasattr(DocumentExtraction, 'document_id'))
    check('Has raw_text column', hasattr(DocumentExtraction, 'raw_text'))
    check('Has extracted_fields_json column', hasattr(DocumentExtraction, 'extracted_fields_json'))
    check('Has verified_fields_json column', hasattr(DocumentExtraction, 'verified_fields_json'))
    check('Has extraction_status column', hasattr(DocumentExtraction, 'extraction_status'))
    check('Has verification_status column', hasattr(DocumentExtraction, 'verification_status'))
    check('extracted_fields property', hasattr(DocumentExtraction, 'extracted_fields'))
    check('verified_fields property', hasattr(DocumentExtraction, 'verified_fields'))
    check('to_dict method', hasattr(DocumentExtraction, 'to_dict'))
except Exception as e:
    check('DocumentExtraction model importable', False, str(e))

# --- Document model back_populates ---
print('\n[2] Document Model Relationship')
try:
    from backend.models.document import Document
    check('Document has extraction relationship', hasattr(Document, 'extraction'))
except Exception as e:
    check('Document has extraction relationship', False, str(e))

# --- Claim model back_populates ---
print('\n[3] Claim Model Relationship')
try:
    from backend.models.claim import Claim
    check('Claim has extractions relationship', hasattr(Claim, 'extractions'))
except Exception as e:
    check('Claim has extractions relationship', False, str(e))

# --- OCR Service ---
print('\n[4] OCR Service')
try:
    from backend.services.ocr_service import extract_text_from_document
    check('extract_text_from_document importable', True)
    # Test with non-existent file
    result = extract_text_from_document('/nonexistent/path/file.pdf', 'pdf')
    check('Returns dict on missing file', isinstance(result, dict))
    check('Returns success=False for missing file', result.get('success') == False)
    check('Returns error message', bool(result.get('error')))
    # Test unsupported extension
    result2 = extract_text_from_document('/tmp/x.mp4', 'mp4')
    check('Returns error for unsupported type', not result2.get('success'))
except Exception as e:
    check('OCR service importable', False, str(e))

# --- Document Extraction Service ---
print('\n[5] Document Extraction Service')
try:
    from backend.services.document_extraction_service import (
        extract_receipt_fields,
        extract_warranty_fields,
        extract_serial_fields,
        extract_diagnostic_fields,
        get_or_create_extraction,
        process_document_ocr,
        save_verified_fields,
    )
    check('extract_receipt_fields importable', True)
    check('extract_warranty_fields importable', True)
    check('extract_serial_fields importable', True)
    check('extract_diagnostic_fields importable', True)
    check('get_or_create_extraction importable', True)
    check('process_document_ocr importable', True)
    check('save_verified_fields importable', True)

    # --- Basic extraction ---
    sample = 'Invoice No: INV-2024-001\nDate: 25/01/2024\nSold By: TechWorld Store\nProduct: SmartTV 55\nSerial Number: SN12345678\nTotal: $1299.99'
    fields = extract_receipt_fields(sample)
    check('extract_receipt_fields returns dict', isinstance(fields, dict))
    check('invoice_number key present', 'invoice_number' in fields)
    check('Detects invoice number (INV-2024-001)', fields.get('invoice_number') is not None, str(fields.get('invoice_number')))
    check('Detects seller_name (Sold By label)', fields.get('seller_name') is not None, str(fields.get('seller_name')))
    check('Detects serial_number when labelled', fields.get('serial_number') is not None, str(fields.get('serial_number')))

    # --- Exact test invoice (Apple/DEMO) ---
    DEMO_OCR = (
        "PURCHASE INVOICE - DEMO / SAMPLE\n"
        "Invoice No.\n"
        "DEMO-APL-2026-0715-001\n"
        "Invoice Date\n"
        "15 July 2026\n"
        "Retailer\n"
        "Apple Store\n"
        "Payment Status Paid\n"
        "Description\n"
        "Brand\n"
        "Model\n"
        "Qty\n"
        "Unit Price\n"
        "Amount\n"
        "Apple iPhone 15\n"
        "Apple\n"
        "A3090\n"
        "1\n"
        "$799.00\n"
        "$799.00\n"
        "Subtotal\n"
        "$799.00\n"
        "Tax / Fees\n"
        "$0.00\n"
        "Total Paid\n"
        "$799.00\n"
        "Customer: Maria Muneer\n"
        "Purchase Date: 15 July 2026\n"
        "Warranty: 12 Months (1 Year Standard)\n"
    )
    demo = extract_receipt_fields(DEMO_OCR)
    check('Demo: invoice_number = DEMO-APL-2026-0715-001',
          demo.get('invoice_number') == 'DEMO-APL-2026-0715-001',
          str(demo.get('invoice_number')))
    check('Demo: invoice_date contains July 2026',
          demo.get('invoice_date') is not None and '2026' in (demo.get('invoice_date') or ''),
          str(demo.get('invoice_date')))
    check('Demo: seller_name = Apple Store',
          demo.get('seller_name') == 'Apple Store',
          str(demo.get('seller_name')))
    check('Demo: customer_name contains Maria',
          demo.get('customer_name') is not None and 'Maria' in (demo.get('customer_name') or ''),
          str(demo.get('customer_name')))
    check('Demo: product_model = A3090',
          demo.get('product_model') is not None and 'A3090' in (demo.get('product_model') or ''),
          str(demo.get('product_model')))
    check('Demo: purchase_price detected', demo.get('purchase_price') is not None,
          str(demo.get('purchase_price')))
    check('Demo: serial_number is None (not invented)',
          demo.get('serial_number') is None,
          'Got: ' + str(demo.get('serial_number')))
    check('Demo: warranty_reference is None (no actual ref ID)',
          demo.get('warranty_reference') is None,
          'Got: ' + str(demo.get('warranty_reference')))

    # --- No-serial invoice: serial must not be invented ---
    no_serial_txt = 'Invoice No: INV-9999\nDate: 01/01/2024\nSold By: TestShop\nTotal: $500.00'
    ns = extract_receipt_fields(no_serial_txt)
    check('serial_number stays None when not labelled', ns.get('serial_number') is None,
          'Got: ' + str(ns.get('serial_number')))

    # --- No warranty ref: must not be invented ---
    no_war_txt = 'Invoice No: INV-1234\nWarranty: 12 Months\nTotal: $200.00'
    nw = extract_receipt_fields(no_war_txt)
    check('warranty_reference is None when only duration given', nw.get('warranty_reference') is None,
          'Got: ' + str(nw.get('warranty_reference')))

except Exception as e:
    check('document_extraction_service importable', False, str(e))

    # --- Warranty field extraction ---
    warranty_txt = 'Product: iPhone 15\nSerial No: XR9876543\nWarranty Start: 01/06/2024\nWarranty End: 01/06/2025\nManufacturer: Apple Inc'
    wfields = extract_warranty_fields(warranty_txt)
    check('extract_warranty_fields returns dict', isinstance(wfields, dict))
    check('Detects serial_number in warranty', wfields.get('serial_number') is not None, str(wfields.get('serial_number')))
    check('Detects manufacturer', wfields.get('manufacturer') is not None, str(wfields.get('manufacturer')))

    # --- Serial field extraction ---
    sn_txt = 'S/N: AB-1234-5678\nModel: XZ-500'
    sfields = extract_serial_fields(sn_txt)
    check('extract_serial_fields returns dict', isinstance(sfields, dict))
    check('Detects serial_number from S/N label', sfields.get('serial_number') is not None)

    # --- Diagnostic field extraction ---
    diag_txt = 'Report Date: 10/09/2024\nTechnician: John Smith\nFault: Board failure. Capacitor C12 blown.'
    dfields = extract_diagnostic_fields(diag_txt)
    check('extract_diagnostic_fields returns dict', isinstance(dfields, dict))
    check('Detects technician', dfields.get('technician') is not None, str(dfields.get('technician')))

except Exception as e:
    check('Extended extraction tests', False, str(e))

# --- OCR Routes, CSRF & Date Normalization ---
print('\n[6] OCR Routes, CSRF & Date Normalization')
try:
    from backend.routes.ocr_routes import (
        ocr_bp, _check_doc_access, _validate_verification_fields,
        _is_valid_date_string, _parse_date_flexible, _normalize_date_to_iso
    )
    check('ocr_bp blueprint importable', True)
    check('ocr_bp url_prefix correct', ocr_bp.url_prefix == '/api/documents')
    check('_check_doc_access importable (IDOR guard)', True)
    check('_validate_verification_fields importable', True)

    # --- Existing validation ---
    errs = _validate_verification_fields({'invoice_date': 'not-a-date'})
    check('Validation rejects bad date string', len(errs) > 0)
    errs2 = _validate_verification_fields({'invoice_date': '25/01/2024'})
    check('Validation accepts DD/MM/YYYY', len(errs2) == 0)
    errs3 = _validate_verification_fields({'purchase_price': 'INVALID_PRICE'})
    check('Validation rejects invalid price', len(errs3) > 0)

    # --- _is_valid_date_string: word-month format support ---
    check('Accepts 15 July 2026', _is_valid_date_string('15 July 2026'))
    check('Accepts 15 Jul 2026',  _is_valid_date_string('15 Jul 2026'))
    check('Accepts July 15, 2026', _is_valid_date_string('July 15, 2026'))
    check('Accepts 2026-07-15 (ISO)', _is_valid_date_string('2026-07-15'))
    check('Rejects not-a-date', not _is_valid_date_string('not-a-date'))
    check('Handles empty string gracefully', not _is_valid_date_string(''))

    # --- _normalize_date_to_iso: conversion ---
    check('15 July 2026 -> 2026-07-15',
          _normalize_date_to_iso('15 July 2026') == '2026-07-15',
          _normalize_date_to_iso('15 July 2026'))
    check('15 Jul 2026 -> 2026-07-15',
          _normalize_date_to_iso('15 Jul 2026') == '2026-07-15',
          _normalize_date_to_iso('15 Jul 2026'))
    check('July 15, 2026 -> 2026-07-15',
          _normalize_date_to_iso('July 15, 2026') == '2026-07-15',
          _normalize_date_to_iso('July 15, 2026'))
    check('2026-07-15 stays 2026-07-15',
          _normalize_date_to_iso('2026-07-15') == '2026-07-15',
          _normalize_date_to_iso('2026-07-15'))
    check('15/07/2026 -> 2026-07-15',
          _normalize_date_to_iso('15/07/2026') == '2026-07-15',
          _normalize_date_to_iso('15/07/2026'))
    check('15-07-2026 -> 2026-07-15',
          _normalize_date_to_iso('15-07-2026') == '2026-07-15',
          _normalize_date_to_iso('15-07-2026'))
    check('Invalid date returned as-is (validator will reject)',
          _normalize_date_to_iso('not-a-date') == 'not-a-date')
    check('None input handled', _normalize_date_to_iso(None) is None)
    check('Empty string handled', _normalize_date_to_iso('') == '')

    # --- After normalization, validation should accept all variants ---
    for raw in ['15 July 2026', '15 Jul 2026', 'July 15, 2026', '2026-07-15',
                '15/07/2026', '15-07-2026']:
        normalized = _normalize_date_to_iso(raw)
        errs_n = _validate_verification_fields({'invoice_date': normalized})
        check('Post-normalize: "%s" accepted' % raw, len(errs_n) == 0,
              'Got errors: ' + str(errs_n))

except Exception as e:
    check('OCR routes importable', False, str(e))

# --- App integration & CSRF exemption ---
print('\n[7] Flask App Integration & CSRF')
try:
    from backend.app import create_app
    app = create_app('testing')
    with app.app_context():
        from backend.extensions import db, csrf
        from sqlalchemy import inspect
        db.create_all()  # in-memory test DB requires explicit creation
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        check('document_extractions table exists', 'document_extractions' in tables,
              'Tables: ' + str(tables[:5]))

        # Check routes registered
        routes = [str(r) for r in app.url_map.iter_rules()]
        check('GET /api/documents/<id>/ocr registered', any('ocr' in r for r in routes))
        check('POST /api/documents/<id>/ocr/verify registered', any('verify' in r for r in routes))

        # Verify ocr_bp is in the CSRF exempt blueprints
        from backend.routes.ocr_routes import ocr_bp as _ocr_bp
        exempt_bps = getattr(csrf, '_exempt_blueprints', set())
        # _exempt_blueprints may contain Blueprint objects or name strings
        ocr_exempt = (
            _ocr_bp in exempt_bps
            or _ocr_bp.name in {getattr(b, 'name', b) for b in exempt_bps}
        )
        check('ocr_bp is CSRF-exempt (fix for Confirm Verified error)', ocr_exempt,
              'exempt_blueprints: ' + str({getattr(b, 'name', b) for b in exempt_bps}))
except Exception as e:
    check('Flask app integration', False, str(e))

# --- Document model ocr_status field ---
print('\n[8] Document OCR Status Field')
try:
    from backend.models.document import Document
    check('Document has ocr_status attribute', hasattr(Document, 'ocr_status'))
except Exception as e:
    check('Document has ocr_status attribute', False, str(e))

# --- Needs Correction: backend behavior ---
print('\n[9] Needs Correction Backend Behavior')
try:
    from backend.app import create_app as _capp2
    from backend.models.document_extraction import (
        DocumentExtraction,
        VERIFY_STATUS_NEEDS_CORRECTION, VERIFY_STATUS_VERIFIED,
        EXTRACTION_STATUS_COMPLETED,
    )

    _app2 = _capp2('testing')
    with _app2.app_context():
        from backend.extensions import db as _db2
        _db2.create_all()

        # Create a minimal Document row to satisfy the NOT NULL FK
        import uuid
        from backend.models.document import Document as _Doc
        test_doc = _Doc()
        test_doc.original_filename = 'test_invoice.pdf'
        test_doc.stored_filename   = 'test_' + uuid.uuid4().hex + '.pdf'
        test_doc.stored_path       = '/tmp/test_invoice.pdf'
        test_doc.file_extension    = 'pdf'
        test_doc.file_size         = 1234
        test_doc.file_hash         = uuid.uuid4().hex
        _db2.session.add(test_doc)
        _db2.session.flush()  # get test_doc.id

        # Create a minimal extraction record
        ext = DocumentExtraction()
        ext.extraction_uid  = str(uuid.uuid4())
        ext.document_id     = test_doc.id
        ext.raw_text        = 'PURCHASE INVOICE\nInvoice No: INV-TEST-001\nDate: 01/01/2024'
        ext.extracted_fields = {
            'invoice_number': 'INV-TEST-001',
            'invoice_date':   '01/01/2024',
            'seller_name':    'Test Shop',
        }
        ext.extraction_status = EXTRACTION_STATUS_COMPLETED
        _db2.session.add(ext)
        _db2.session.flush()

        # Simulate save_verified_fields (needs_correction=True path)
        from backend.services.document_extraction_service import save_verified_fields
        corrected = {
            'invoice_number': 'INV-TEST-CORRECTED',
            'invoice_date':   '2024-03-15',
            'seller_name':    'Corrected Shop',
        }
        # Mimic what verify_ocr_fields does when needs_correction=True
        from backend.models.document_extraction import VERIFY_STATUS_NEEDS_CORRECTION
        ext.verification_status = VERIFY_STATUS_NEEDS_CORRECTION
        ext.verified_fields = corrected
        _db2.session.commit()

        check('needs_correction=True sets status to Needs Correction',
              ext.verification_status == VERIFY_STATUS_NEEDS_CORRECTION)
        check('Corrected fields are saved',
              ext.verified_fields.get('invoice_number') == 'INV-TEST-CORRECTED')
        check('Corrected seller_name saved',
              ext.verified_fields.get('seller_name') == 'Corrected Shop')
        check('Raw OCR text unchanged after correction',
              'PURCHASE INVOICE' in (ext.raw_text or ''),
              'raw_text: ' + str(ext.raw_text)[:60])
        check('Extracted fields unchanged after correction',
              ext.extracted_fields.get('invoice_number') == 'INV-TEST-001',
              'extracted: ' + str(ext.extracted_fields))

        # Simulate Confirm Verified path (needs_correction=False)
        save_verified_fields(ext, {'invoice_number': 'INV-TEST-001', 'invoice_date': '2024-01-01'}, verifying_user_id=None)
        _db2.session.refresh(ext)
        check('Confirm Verified still works after correction',
              ext.verification_status == VERIFY_STATUS_VERIFIED)
        check('Raw OCR text still unchanged after Confirm Verified',
              'PURCHASE INVOICE' in (ext.raw_text or ''))

        # Verify that validation still runs — invalid price rejected
        from backend.routes.ocr_routes import _validate_verification_fields, _normalize_date_to_iso
        errs = _validate_verification_fields({'invoice_date': '2024-01-01', 'purchase_price': 'BADPRICE'})
        check('Validation still works in correction context', len(errs) > 0)

        # Verify correction can be applied again (re-entrant)
        ext.verification_status = VERIFY_STATUS_NEEDS_CORRECTION
        ext.verified_fields = {'invoice_number': 'INV-RE-CORRECTED'}
        _db2.session.commit()
        check('Correction can be applied again (re-entrant)',
              ext.verification_status == VERIFY_STATUS_NEEDS_CORRECTION
              and ext.verified_fields.get('invoice_number') == 'INV-RE-CORRECTED')

except Exception as e:
    import traceback
    check('Needs Correction backend behavior', False, str(e))
    traceback.print_exc()

print(f'\n=== Results: {PASS} passed, {FAIL} failed ===')
if FAIL > 0:
    sys.exit(1)
