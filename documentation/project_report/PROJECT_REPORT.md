# AssureX Claim Engine — Project Report

| Field | Details |
|-------|---------|
| **Project Name** | AssureX Claim Engine |
| **Team** | Maria, Khizra, Urooba, Zainab |
| **Category** | AI / Web Application |
| **Duration** | September 24–28, 2026 (5 days) |
| **Tech Stack** | Python, Flask, scikit-learn, Google Teachable Machine, RapidOCR, SQLite |

---

## 1. Executive Summary

AssureX Claim Engine is an AI-powered warranty claim validation and processing system for consumer electronics. The system automates the evaluation of warranty claims by combining a deterministic rule engine, a trained machine learning model, and an image classification model into a unified decision pipeline.

Claims that clearly pass or fail all criteria are auto-decided in seconds. Borderline and ambiguous claims are routed to a human reviewer with full AI context already prepared. The system achieves **89.8% accuracy** on held-out test data and **93.3%** on a 30-claim manual sample evaluation.

---

## 2. Problem Statement

Warranty claim processing in consumer electronics is manual, slow, and error-prone:
- Average processing time: 3–7 business days
- Fraudulent claims cost companies millions annually
- Valid claims get rejected due to reviewer error or missing paperwork
- No audit trail for decisions

**Target users:** Electronics manufacturers, retailers, and warranty service providers.

**Solution:** An automated AI system that validates claims in real-time, routes edge cases to reviewers, and maintains a complete audit trail.

---

## 3. Team Roles & Contributions

| Member | Role | Key Contributions |
|--------|------|-------------------|
| **Maria** | Project Lead, Backend Architecture | App structure, auth system, admin panel, testing coordination |
| **Khizra** | Rule Engine & Services | 6 warranty rules, final decision logic, OCR integration, contradiction detection |
| **Urooba** | AI/ML Models | Python model training, Teachable Machine setup, prediction service |
| **Zainab** | Frontend & UI | All HTML templates, CSS design system, dashboard animations, claim pages |

---

## 4. System Architecture

```
┌─────────────────────────────────────────────────────┐
│                  Web Browser (Client)                │
│            Dark Glassmorphism UI (Jinja2)            │
└─────────────────────┬───────────────────────────────┘
                      │ HTTP
┌─────────────────────▼───────────────────────────────┐
│              Flask Web Application                   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐  │
│  │  Auth    │ │  Claims  │ │  Admin   │ │  OCR   │  │
│  │ Routes   │ │  Routes  │ │  Routes  │ │ Routes │  │
│  └──────────┘ └──────────┘ └──────────┘ └────────┘  │
│  ┌────────────────────────────────────────────────┐  │
│  │           Service Layer                        │  │
│  │  ┌─────────────┐ ┌──────────────┐ ┌─────────┐ │  │
│  │  │ Rule Engine │ │ ML Predictor │ │   OCR   │ │  │
│  │  │  (6 rules)  │ │ (RandomForest│ │ Service │ │  │
│  │  └─────────────┘ │ + Teachable  │ └─────────┘ │  │
│  │  ┌─────────────┐ │  Machine)    │             │  │
│  │  │  Final Decn │ └──────────────┘             │  │
│  │  │   Engine    │                              │  │
│  │  └─────────────┘                              │  │
│  └────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────┐  │
│  │        SQLAlchemy ORM (12 Models)              │  │
│  └───────────────────┬────────────────────────────┘  │
└──────────────────────┼─────────────────────────────--┘
                       │
              ┌────────▼────────┐
              │  SQLite Database │
              │  (assurex.db)    │
              └─────────────────┘
```

---

## 5. Core Features

### 5.1 User Role System

| Role | Access Level | Key Capabilities |
|------|-------------|------------------|
| Customer | Own data only | Register products, submit claims, upload docs, track status |
| Service Centre | Assigned claims | View and update repair status |
| Claim Reviewer | All pending claims | Approve/Reject/Escalate with mandatory notes |
| Administrator | Full system | User management, reports, audit logs |

### 5.2 AI Decision Pipeline

```
Claim Submitted
      │
      ▼
[Warranty Rule Engine]          6 rules checked deterministically
      │
      ├─ All pass + ML Valid (≥0.80) ──→ AUTO-APPROVE
      ├─ Rules fail + ML Invalid (≥0.80) ──→ AUTO-REJECT
      └─ Borderline / ML confidence <0.80 ──→ MANUAL REVIEW
```

### 5.3 Six Warranty Rules

| Rule | Check | Failure Action |
|------|-------|---------------|
| 1 | Warranty not expired | Auto-Reject |
| 2 | Product age within limit | Auto-Reject |
| 3 | Damage type covered | Auto-Reject |
| 4 | Serial number matches | Flag for Review |
| 5 | No duplicate claim (30 days) | Flag for Review |
| 6 | No timeline contradictions | Flag for Review |

### 5.4 OCR Document Processing

1. Customer uploads invoice/receipt as PDF or image
2. RapidOCR extracts text fields (invoice_date, serial_number, purchase_price, seller_name)
3. Extracted data presented to customer in a review panel
4. Customer verifies and corrects any OCR errors
5. Verified fields stored and used in claim validation

### 5.5 Manual Review Workflow

When a claim is flagged:
- Reviewer sees: claim summary, AI prediction, confidence score, rule-by-rule results
- Reviewer chooses: Approve / Reject / Request More Info / Escalate
- Notes are **mandatory** for Reject, Escalate, Request Info (to protect customers)
- Decision triggers customer notification and claim status update

---

## 6. Database Models

| Model | Purpose | Key Fields |
|-------|---------|-----------|
| User | System users | name, email, role, is_active |
| Product | Registered devices | product_uid, serial_number, category, purchase_date |
| Warranty | Coverage policies | start_date, end_date, category, status |
| Claim | Warranty claims | claim_uid, status, damage_type, fault_date, fault_description |
| Document | Uploaded files | filename, doc_type, file_path, ocr_status |
| DocumentExtraction | OCR results | extracted_fields, verified_fields, verification_status |
| Prediction | AI outputs | predicted_class, valid_confidence, model_used |
| RuleResult | Rule engine outputs | rule_name, passed, reason |
| Notification | In-app messages | title, message, is_read, created_at |
| AuditLog | Admin actions | action, user_id, target_id, timestamp |
| RepairHistory | Repair records | repair_type, status, cost, technician |
| ModelVersion | AI model versions | version, accuracy, deployed_at |

---

## 7. AI Models

### 7.1 Python ML Model (Random Forest)

**Algorithm:** Random Forest Classifier (scikit-learn)  
**Training data:** 1,500 labelled claims  
**Features:** 14 encoded features (product age, damage type, warranty category, rule score, etc.)  
**Target classes:** Valid, Invalid, Manual Review

| Metric | Value |
|--------|-------|
| Training Accuracy | 94.3% |
| Validation Accuracy | 91.6% |
| Test Accuracy (unseen) | 89.8% |
| Macro F1-Score | 0.90 |

### 7.2 Google Teachable Machine (Image Model)

**Type:** Image classification (2 classes)  
**Classes:** Valid document, Invalid document  
**Training images:** 350+ per class  
**Validation accuracy:** 87.3%

### 7.3 Final Decision Aggregation

```python
if all_rules_pass and ml_valid_confidence >= 0.80 and image_valid:
    decision = "AUTO-APPROVE"
elif rules_failed_count >= 3 and ml_invalid_confidence >= 0.80:
    decision = "AUTO-REJECT"
else:
    decision = "MANUAL-REVIEW"
```

---

## 8. Security Implementation

| Measure | Implementation |
|---------|---------------|
| Password hashing | Werkzeug PBKDF2-SHA256 |
| Session management | Flask-Login with server-side sessions |
| CSRF protection | Flask-WTF CSRFProtect (global) |
| IDOR protection | Ownership check on every resource access |
| RBAC | Role checked at every protected route |
| Input sanitization | All inputs stripped, length-limited before DB |
| File validation | Type + size check on every upload |
| Audit logging | Immutable AuditLog for all admin actions |

---

## 9. Frontend Design System

**Theme:** Dark glassmorphism  
**Primary color:** `#38bdf8` (sky blue)  
**Background:** `#050b18` (deep navy)  
**Fonts:** Outfit (UI), Space Grotesk (headings)

**Animation libraries:**
- GSAP 3.12.2 — counter animations, timeline effects
- Three.js — particle sphere on landing page
- Vanilla Tilt — 3D card tilt on mouse movement
- CSS keyframes — shimmer sweeps, pulse glows

**Responsive:** Works on mobile (≥320px) and desktop, horizontal scroll on data tables

---

## 10. Testing

**Test framework:** pytest  
**Test files:** 25+ files covering all modules  
**Total test cases:** 75  
**Pass rate:** 100% (75/75)

Key areas tested:
- Authentication and session management
- Product and warranty CRUD
- Claim registration and document upload
- Warranty rule engine (6 rules)
- AI model loading and inference
- Duplicate and contradiction detection
- OCR field extraction and verification
- Manual review workflow
- Admin user management
- IDOR and RBAC protections

---

## 11. Challenges & Solutions

| Challenge | Solution |
|-----------|----------|
| OCR misreading non-numeric data as purchase_price | Pre-sanitize and clear non-numeric price before validation |
| CSRF 400 errors on fetch() API calls | Exempt API blueprints from CSRF; use JSON fetch instead of form POST |
| OCR panel scroll — verify button hidden | Move verify bar outside scroll container using flex column structure |
| Manual review button not visible below fold | Sticky fixed-position submit bar at bottom of viewport |
| Admin table content overflow | overflow-x: auto + fixed column widths + word-break |
| Missing icons in customer dashboard | Replace CDN-dependent icons with inline SVG for reliability |

---

## 12. Future Improvements

1. **PostgreSQL in production** — replace SQLite for multi-user concurrency
2. **Real-time notifications** — WebSockets (Flask-SocketIO) instead of polling
3. **Email notifications** — SendGrid integration for claim status emails
4. **Model retraining pipeline** — auto-retrain when 500+ new labelled claims accumulate
5. **Mobile app** — React Native or Flutter customer app
6. **Analytics dashboard** — claim trends, approval rates, fraud patterns
7. **API-first architecture** — REST API for third-party integrations

---

## 13. Deliverables Submitted

| # | Item | Location |
|---|------|----------|
| 1 | Project Report (this document) | `documentation/project_report/` |
| 2 | GitHub Source Code + README | Repository root |
| 3 | Dataset (CSV + Train/Val/Test) | `dataset/` + `ai_models/python_model/training_data/` |
| 4 | Python Model Training Evidence | `ai_models/python_model/` |
| 5 | Teachable Machine Export | `ai_models/teachable_machine/exported_model/` |
| 6 | Model Comparison Report | `documentation/model_comparison/` |
| 7 | Warranty Policy Config Files (3) | `config/warranty_policies/` |
| 8 | Test Cases Document | `documentation/testing/` |
| 9 | Installation & Execution Guide | `README.md` |
| 10 | Live Deployed Web App | [Deployment Link] |
| 11 | Demonstration Video | Submitted separately |
| 12 | Technical Blog Article | `documentation/TECHNICAL_BLOG.md` |
| 13 | AI Usage Declaration | `AI_USAGE.md` |

---

*Submitted by: Maria, Khizra, Urooba, Zainab*  
*September 2026 — AssureX Claim Engine*
