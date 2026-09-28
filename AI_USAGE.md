# AI Usage Declaration — AssureX Claim Engine

**Team:** Maria, Khizra, Urooba, Zainab
**Project Start:** September 24, 2026

---

## What We Built Ourselves (No AI)

- Flask application structure and configuration (`app.py`, `backend/config/`)
- All database models: User, Product, Warranty, Claim, Document, Prediction, AuditLog, Notification, RepairHistory, RuleResult, ModelVersion (`backend/models/`)
- All Flask routes and controllers: auth, products, warranties, claims, admin, reviewer, service center, notifications, reports (`backend/routes/`)
- Python ML model training script and feature engineering (`ai_models/python_model/train_claim_model.py`)
- Teachable Machine image model training setup (`ai_models/teachable_machine/`)
- Warranty rule engine — all 6 rules written manually (`backend/services/warranty_rules.py`)
- Final claim decision logic — aggregation of rule engine + AI model (`backend/services/final_decision.py`)
- OCR and document extraction service — RapidOCR based (`backend/services/ocr_service.py`, `document_extraction_service.py`)
- OCR verification UI — customer can review and correct extracted fields (`backend/routes/ocr_routes.py`)
- Contradiction detection, duplicate claim detection (`backend/services/contradiction_detection.py`, `duplicate_claim_detection.py`)
- Serial number verification service (`backend/services/serial_verification.py`)
- Missing document detection service (`backend/services/missing_document_detection.py`)
- Duplicate document detection via SHA-256 hash fingerprint (`backend/services/duplicate_document_detection.py`)
- Pre-submission validation assistant — 7 checks before claim submit (`backend/services/pre_submission_check.py`)
- Claim Summary Card generator — PNG image for Teachable Machine input (`backend/services/claim_card_generator.py`)
- Model comparison service — confidence gap + consistency status (`backend/services/model_comparison.py`)
- Anomaly detection and system monitoring service (`backend/services/anomaly_service.py`)
- Warranty expiry alert notifications (`backend/services/notification_service.py`)
- Warranty policy service — JSON config based category policies (`backend/services/warranty_policy_service.py`)
- Reviewer workflow service — manual override, approve, reject, escalate (`backend/services/reviewer_service.py`)
- Repair history service and routes (`backend/routes/repair_routes.py`)
- Analytics service (`backend/services/analytics_service.py`)
- Plain-language claim summary service (`backend/services/claim_summary_service.py`)
- PDF report generation (`backend/services/report_service.py` — `generate_claim_pdf()`)
- Training dataset — 1500 rows, 500 per class, 70/15/15 split, CSV format (`ai_models/python_model/training_data/claims_data.csv`)
- All database migration scripts (`database/`)
- All test files — 30+ test cases written manually (`tests/`)
- HTML page structure and Jinja2 template logic (forms, CSRF, flash messages, role-based rendering)

---

## Where We Took AI Assistance

We used an AI coding assistant for the following:

**1. Frontend UI styling only:**
- Dark glassmorphism CSS theme (colors, gradients, blur effects)
- CSS animations (marquee scroll, button shimmer, badge glow, star burst click effect)
- Dashboard layout polish and metric card hover effects
- Login/register page video background and star particle canvas animation
- Hero section layout and button animation styles

**2. PDF report visual layout (fpdf2):**
- Section layout and color scheme of the downloadable PDF claim report
- Typography and spacing choices in `generate_claim_pdf()`

**The AI did NOT touch:**
- Any Flask route or business logic
- Any AI/ML model training or inference code
- Any database model or migration
- Any rule engine decision logic
- Jinja2 template logic (form actions, CSRF tokens, url_for calls, role checks)
- Any service logic (pre-submission checks, anomaly detection, duplicate detection, serial verification, model comparison)
- Training data, feature engineering, or model evaluation code

---

## Why

We took UI styling and PDF layout help to save time so we could focus on the core
competition requirement — the AI-powered claim decision engine, rule engine,
model training, and all backend services — which we built entirely ourselves.

---

Declared honestly by Team AssureX — September 2026
