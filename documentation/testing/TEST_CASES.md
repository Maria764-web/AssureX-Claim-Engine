# AssureX Claim Engine — Test Cases Document

**Project:** AssureX Claim Engine  
**Team:** Maria, Khizra, Urooba, Zainab  
**Date:** September 2026  
**Total Test Cases:** 75  
**Test Framework:** pytest (Python unittest)

---

## Test Execution Summary

| Module | Test Cases | Pass | Fail |
|--------|-----------|------|------|
| Authentication | 8 | 8 | 0 |
| Product Registration | 7 | 7 | 0 |
| Warranty Management | 8 | 8 | 0 |
| Claim Registration & Documents | 18 | 18 | 0 |
| Warranty Policy Rules | 6 | 6 | 0 |
| AI Model & Prediction | 6 | 6 | 0 |
| Duplicate & Contradiction Detection | 6 | 6 | 0 |
| OCR & Document Extraction | 5 | 5 | 0 |
| Manual Review Workflow | 5 | 5 | 0 |
| Admin & User Management | 6 | 6 | 0 |
| **TOTAL** | **75** | **75** | **0** |

---

## Module 1 — Authentication

| TC# | Test Case | Input | Expected Output | Result |
|-----|-----------|-------|-----------------|--------|
| TC-01 | Customer registration with valid data | name, email, password, role=customer | Account created, redirected to dashboard | PASS |
| TC-02 | Registration with duplicate email | Existing email address | Error: "Email already registered" | PASS |
| TC-03 | Login with correct credentials | Valid email + password | Session created, redirected by role | PASS |
| TC-04 | Login with wrong password | Valid email + wrong password | Error: "Invalid credentials" | PASS |
| TC-05 | Login with non-existent email | Unknown email | Error: "Invalid credentials" | PASS |
| TC-06 | Access protected page without login | GET /dashboard (no session) | Redirect to /login | PASS |
| TC-07 | Logout clears session | Active session → GET /logout | Session cleared, redirect to login | PASS |
| TC-08 | Role-based access — customer cannot access admin panel | Customer session → GET /admin/ | 403 Forbidden | PASS |

---

## Module 2 — Product Registration

| TC# | Test Case | Input | Expected Output | Result |
|-----|-----------|-------|-----------------|--------|
| TC-09 | Register product with all valid fields | product_name, category, serial_number, purchase_date | Product created, assigned unique product_uid | PASS |
| TC-10 | Register product with duplicate serial number | Same serial for different product | Error: serial number already exists | PASS |
| TC-11 | Product linked to logged-in user | Authenticated customer registers product | Product.user_id == current_user.id | PASS |
| TC-12 | List products shows only user's own products | 2 users each with 2 products | Each user sees only their own 2 products | PASS |
| TC-13 | Product age calculated correctly | Purchase date 18 months ago | product_age = 18 months | PASS |
| TC-14 | IDOR — user cannot view another user's product | User A accesses User B's product URL | 403 Forbidden | PASS |
| TC-15 | Product with missing required field | Missing serial_number | Validation error returned | PASS |

---

## Module 3 — Warranty Management

| TC# | Test Case | Input | Expected Output | Result |
|-----|-----------|-------|-----------------|--------|
| TC-16 | Create warranty for registered product | product_id, start_date, end_date, category | Warranty created, status=active | PASS |
| TC-17 | Warranty expiry detection — active | end_date = today + 30 days | warranty_status = active | PASS |
| TC-18 | Warranty expiry detection — expired | end_date = today - 1 day | warranty_status = expired | PASS |
| TC-19 | Warranty category stored correctly | category = "Premium Coverage" | warranty.category = "Premium Coverage" | PASS |
| TC-20 | Cannot create duplicate warranty for same product | Same product_id, overlapping dates | Error: warranty already exists | PASS |
| TC-21 | Extended warranty shows original + extended dates | Extended plan linked to base plan | Both date ranges displayed | PASS |
| TC-22 | Exclusions preserved and visible | Exclusion: "accidental damage" | Exclusion visible in warranty detail | PASS |
| TC-23 | Customer tampering protection — warranty dates cannot be modified by customer | Customer PATCH warranty dates | 403 Forbidden | PASS |

---

## Module 4 — Claim Registration & Document Upload

| TC# | Test Case | Input | Expected Output | Result |
|-----|-----------|-------|-----------------|--------|
| TC-24 | Create claim for registered product | product_id, damage_type, fault_description | Claim created, status=draft | PASS |
| TC-25 | Claim gets unique Claim ID | Submit claim | claim_uid like CLM-XXXXX | PASS |
| TC-26 | Claim linked to user | Authenticated customer creates claim | claim.user_id == current_user.id | PASS |
| TC-27 | Claim linked to product | product_id provided | claim.product_id == product.id | PASS |
| TC-28 | Claim linked to warranty | warranty_id provided | claim.warranty_id == warranty.id | PASS |
| TC-29 | Required fields validation | Missing fault_description | Validation error | PASS |
| TC-30 | Valid PDF upload | Upload valid .pdf file | Document created, file saved | PASS |
| TC-31 | Valid image upload (PNG) | Upload valid .png file | Document created, file saved | PASS |
| TC-32 | Valid image upload (JPG) | Upload valid .jpg file | Document created, file saved | PASS |
| TC-33 | Invalid file type rejected | Upload .exe file | Error: file type not allowed | PASS |
| TC-34 | Oversized file rejected | Upload 25MB file (limit 10MB) | Error: file too large | PASS |
| TC-35 | Missing required document detected | Claim without invoice/receipt | Warning: missing required document | PASS |
| TC-36 | IDOR — cannot access another user's claim | User A GET User B's claim URL | 403 Forbidden | PASS |
| TC-37 | IDOR — cannot access another user's document | User A GET User B's document URL | 403 Forbidden | PASS |
| TC-38 | Duplicate Claim ID constraint | Force duplicate claim_uid | Database constraint error | PASS |
| TC-39 | Claim details display correctly | GET /claims/<id> | All claim fields shown | PASS |
| TC-40 | Service Centre can create claim on behalf of customer | Service centre employee + customer_id | Claim created for customer | PASS |
| TC-41 | Additional document upload to existing claim | POST /claims/<id>/documents | New document attached to claim | PASS |

---

## Module 5 — Warranty Policy Rules Engine

| TC# | Test Case | Input | Expected Output | Result |
|-----|-----------|-------|-----------------|--------|
| TC-42 | Rule 1 — Warranty active | claim date ≤ warranty end_date | rule_result = PASS | PASS |
| TC-43 | Rule 2 — Warranty expired | claim date > warranty end_date | rule_result = FAIL, reason = expired | PASS |
| TC-44 | Rule 3 — Product age within limit | product_age = 10 months, limit = 12 | rule_result = PASS | PASS |
| TC-45 | Rule 4 — Product age exceeds limit | product_age = 15 months, limit = 12 | rule_result = FAIL | PASS |
| TC-46 | Rule 5 — Excluded damage type rejected | damage_type = "accidental" (excluded) | rule_result = FAIL | PASS |
| TC-47 | Rule 6 — Serial number mismatch detected | claim serial ≠ registered serial | rule_result = FAIL | PASS |

---

## Module 6 — AI Model & Prediction

| TC# | Test Case | Input | Expected Output | Result |
|-----|-----------|-------|-----------------|--------|
| TC-48 | Python ML model loads successfully | Load .pkl file | No exception, model ready | PASS |
| TC-49 | Valid claim prediction | All rules pass, low product age | Predicted class = "Valid" | PASS |
| TC-50 | Invalid claim prediction | Multiple rules fail, high age | Predicted class = "Invalid" | PASS |
| TC-51 | Manual review prediction | Mixed signals, borderline | Predicted class = "Manual Review" | PASS |
| TC-52 | Confidence threshold logic | valid_confidence = 0.85 | Decision = Auto-Approve (threshold 0.80) | PASS |
| TC-53 | Final decision aggregation | Rules + ML model combined | Single final decision returned | PASS |

---

## Module 7 — Duplicate & Contradiction Detection

| TC# | Test Case | Input | Expected Output | Result |
|-----|-----------|-------|-----------------|--------|
| TC-54 | Duplicate claim detected — same product, same period | 2 claims for same product in 30 days | Duplicate flag raised | PASS |
| TC-55 | Non-duplicate — different product | 2 claims for different products | No duplicate flag | PASS |
| TC-56 | Contradiction — damage date before purchase date | fault_date < purchase_date | Contradiction detected | PASS |
| TC-57 | Contradiction — claim after warranty expiry | claim_date > warranty_end_date | Contradiction detected | PASS |
| TC-58 | No contradiction — valid timeline | purchase → warranty start → fault → claim | No contradiction | PASS |
| TC-59 | Contradiction raises manual review flag | Contradiction detected | claim flagged for manual review | PASS |

---

## Module 8 — OCR & Document Extraction

| TC# | Test Case | Input | Expected Output | Result |
|-----|-----------|-------|-----------------|--------|
| TC-60 | OCR triggered on invoice upload | Upload invoice PDF | Text extracted, extraction record created | PASS |
| TC-61 | OCR extracts invoice date | Invoice with date "15 July 2026" | invoice_date = "2026-07-15" | PASS |
| TC-62 | Non-numeric purchase price auto-cleared | OCR reads "bank transfer" in price field | purchase_price = "" (cleared, no error) | PASS |
| TC-63 | Customer can correct OCR fields | Customer edits serial_number | Updated value saved in verified_fields | PASS |
| TC-64 | OCR status tracks completion | OCR runs → succeeds | extraction_status = "completed" | PASS |

---

## Module 9 — Manual Review Workflow

| TC# | Test Case | Input | Expected Output | Result |
|-----|-----------|-------|-----------------|--------|
| TC-65 | Reviewer can approve a claim | action = "approve" | claim_status = approved, notification sent | PASS |
| TC-66 | Reviewer can reject with notes | action = "reject", notes = "Outside warranty period" | claim_status = rejected, notes saved | PASS |
| TC-67 | Reject without notes blocked | action = "reject", notes = "" | Error: notes required for reject | PASS |
| TC-68 | Escalate without notes blocked | action = "escalate", notes = "" | Error: notes required for escalate | PASS |
| TC-69 | Reviewer cannot access claims of other reviewers | Reviewer A GET Reviewer B's claim | 403 Forbidden | PASS |

---

## Module 10 — Admin & User Management

| TC# | Test Case | Input | Expected Output | Result |
|-----|-----------|-------|-----------------|--------|
| TC-70 | Admin can view all users | GET /admin/users | All users listed with roles | PASS |
| TC-71 | Admin can deactivate user | PATCH user is_active = false | User cannot log in | PASS |
| TC-72 | Admin can change user role | PATCH user role = "reviewer" | Role updated, access changes | PASS |
| TC-73 | Admin can view all claims | GET /admin/claims | All claims from all users shown | PASS |
| TC-74 | Admin dashboard metrics correct | 3 users, 5 claims | user_count=3, claim_count=5 | PASS |
| TC-75 | Audit log records admin action | Admin deactivates user | AuditLog entry created with timestamp | PASS |

---

## How to Run Tests

```bash
# Activate virtual environment first
venv\Scripts\activate

# Run all tests
pytest tests/ -v

# Run specific module
pytest tests/test_claims.py -v
pytest tests/test_warranty_rules.py -v
pytest tests/test_final_decision.py -v

# Run with coverage
pytest tests/ --cov=backend --cov-report=html
```

---

*Document prepared by: Maria, Khizra, Urooba, Zainab — AssureX Team — September 2026*
