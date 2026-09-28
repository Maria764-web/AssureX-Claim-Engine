# AssureX Claim Engine

> AI-powered warranty claim validation system for consumer electronics — built for competition submission.

**Team:** Maria · Khizra · Urooba · Zainab  
**Project Start:** September 24, 2026  
**Stack:** Python · Flask · SQLAlchemy · scikit-learn · Google Teachable Machine · RapidOCR  
**GitHub:** https://github.com/tumhara-username/AssureX-Claim-Engine

---

## What is AssureX?

AssureX is a full-stack web application that automates the processing of warranty claims for consumer electronics. When a customer submits a claim, the system:

1. Runs **6 warranty rule checks** (product age, serial number, damage type, duplicate detection, etc.)
2. Feeds claim data into a **trained Random Forest ML model** for outcome prediction
3. Uses **Google Teachable Machine** image analysis on submitted documents
4. Combines all signals into a **final decision**: Auto-Approve, Auto-Reject, or Flag for Manual Review
5. Sends **real-time notifications** at every stage

---

## User Roles

| Role | Description |
|------|-------------|
| **Customer** | Register products, submit claims, upload documents, track status |
| **Claim Reviewer** | Review flagged claims, approve/reject/escalate with notes |
| **Service Centre Employee** | View assigned claims, update repair status |
| **Administrator** | Full access: manage users, view reports, monitor system |

---

## Key Features

- Dark glassmorphism UI with 3D animations (GSAP, Three.js, Vanilla Tilt)
- Role-based access control (RBAC) with Flask-Login
- OCR document scanning — customer can verify/correct extracted fields
- AI dual-model architecture (tabular ML + image classification)
- 6-rule warranty engine with contradiction & duplicate detection
- Real-time notifications (in-app)
- Admin dashboard: user management, claim overview, audit logs
- Manual review workflow: reviewer notes mandatory for reject/escalate
- CSRF protection across all routes

---

## Project Structure

```
AssureX/
├── app.py                          # Flask application entry point
├── run.py                          # Development server runner
├── requirements.txt                # Python dependencies
├── README.md                       # This file
├── AI_USAGE.md                     # AI tools declaration
├── DEVLOG.md                       # Day-by-day development log
│
├── backend/
│   ├── config/
│   │   ├── config.py               # Flask config (dev/prod/test)
│   │   ├── model_config.py         # AI model paths & thresholds
│   │   └── database_config.py      # SQLAlchemy database config
│   ├── models/                     # SQLAlchemy ORM models
│   │   ├── user.py
│   │   ├── claim.py
│   │   ├── product.py
│   │   ├── warranty.py
│   │   ├── document.py
│   │   ├── prediction.py
│   │   ├── notification.py
│   │   └── audit_log.py
│   ├── routes/                     # Flask blueprints
│   │   ├── auth_routes.py
│   │   ├── claim_routes.py
│   │   ├── admin_routes.py
│   │   ├── reviewer_routes.py
│   │   ├── ocr_routes.py
│   │   └── ...
│   ├── services/                   # Business logic
│   │   ├── warranty_rules.py       # 6-rule warranty engine
│   │   ├── final_decision.py       # AI + rules aggregation
│   │   ├── ocr_service.py          # RapidOCR integration
│   │   ├── contradiction_detection.py
│   │   └── duplicate_claim_detection.py
│   └── extensions.py               # Flask extensions (db, csrf, login)
│
├── frontend/
│   ├── pages/                      # Jinja2 HTML templates
│   │   ├── base.html               # Master layout
│   │   ├── index.html              # Landing page
│   │   ├── dashboard.html          # Customer dashboard
│   │   ├── admin-dashboard.html    # Admin panel
│   │   ├── claim_detail.html       # Claim detail + OCR panel
│   │   ├── manual_review.html      # Reviewer decision page
│   │   └── ...
│   └── css/
│       └── style.css               # Global 3D animation library
│
├── ai_models/
│   ├── python_model/
│   │   ├── training_data/
│   │   │   ├── claims_data.csv     # 1,500 labelled claim records
│   │   │   └── train_claim_model.py
│   │   └── saved_models/
│   │       └── assurex_claim_decision_model.pkl
│   └── teachable_machine/
│       ├── training_images/
│       │   ├── Valid/              # ~500 valid claim document images
│       │   └── Invalid/            # ~500 invalid claim document images
│       └── exported_model/         # Teachable Machine export (model.json + weights)
│
├── dataset/
│   ├── raw/                        # Original unprocessed data
│   ├── train/                      # 70% split — 1,050 records
│   ├── validation/                 # 15% split — 225 records
│   └── test/                       # 15% split — 225 unseen records
│
├── documentation/
│   ├── project_report/             # Full project report (PDF)
│   ├── model_comparison/           # 30+ claim model comparison matrix
│   ├── testing/                    # Test cases document
│   ├── installation_guide/         # Step-by-step setup guide
│   └── screenshots/                # App screenshots
│
├── database/
│   └── migrations/                 # Flask-Migrate migration files
│
├── deployment/
│   ├── requirements.txt            # Production dependencies
│   └── .env.example                # Environment variable template
│
├── config/
│   └── warranty_policies/          # Warranty category config files
│
└── tests/                          # Pytest test suite (25+ test files)
```

---

## Installation & Setup Guide

### Prerequisites

- Python 3.9 or higher
- pip (Python package manager)
- Git

### Step 1 — Clone the Repository

```bash
git clone https://github.com/your-team/assurex-claim-engine.git
cd assurex-claim-engine
```

### Step 2 — Create Virtual Environment

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Mac / Linux
python3 -m venv venv
source venv/bin/activate
```

### Step 3 — Install Dependencies

```bash
pip install -r requirements.txt
```

Required packages include:
- `flask` — web framework
- `flask-sqlalchemy` — ORM
- `flask-login` — session management
- `flask-wtf` — CSRF protection
- `flask-migrate` — database migrations
- `scikit-learn` — ML model
- `joblib` — model serialization
- `rapidocr-onnxruntime` — OCR engine
- `pandas`, `numpy` — data processing

### Step 4 — Environment Variables

Copy the example env file and fill in values:

```bash
cp deployment/.env.example .env
```

Minimum required variables:
```
FLASK_ENV=development
SECRET_KEY=your-secret-key-here
DATABASE_URL=sqlite:///assurex.db
UPLOAD_FOLDER=uploads
```

### Step 5 — Initialize Database

```bash
flask --app backend.app init-db
```

This creates all tables in `instance/assurex.db`.

### Step 6 — Create Admin Account

```bash
flask --app backend.app create-admin
```

Follow the prompts to set admin name, email, and password.

### Step 7 — Run the Application

```bash
python run.py
```

Or:
```bash
flask --app backend.app run --debug
```

Open your browser at: **http://127.0.0.1:5000**

---

## AI Model Setup

### Python ML Model (Random Forest)

The trained model is already saved at `ai_models/python_model/saved_models/assurex_claim_decision_model.pkl`.

To retrain from scratch:

```bash
cd ai_models/python_model/training_data
python train_claim_model.py
```

The script will output:
- Accuracy score
- Classification report
- Confusion matrix
- New `.pkl` model file

### Google Teachable Machine Model

1. Go to [teachablemachine.withgoogle.com](https://teachablemachine.withgoogle.com)
2. Create Image Project
3. Upload images from `ai_models/teachable_machine/training_images/Valid/` and `Invalid/`
4. Train the model
5. Export → TensorFlow.js → Download
6. Place exported files in `ai_models/teachable_machine/exported_model/`
7. Update `TEACHABLE_MACHINE_MODEL_URL` in `.env` if using hosted version

---

## Dataset

| Split | Records | Percentage |
|-------|---------|------------|
| Training | 1,050 | 70% |
| Validation | 225 | 15% |
| Test (unseen) | 225 | 15% |
| **Total** | **1,500** | **100%** |

Classes: `Valid` · `Invalid` · `Manual Review` (500 each)

CSV location: `ai_models/python_model/training_data/claims_data.csv`

---

## Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_claims.py -v

# Run with coverage report
pytest tests/ --cov=backend --cov-report=term-missing
```

---

## Warranty Policy Categories

The system supports configurable warranty policies. Config files are located in `config/warranty_policies/`. Three default categories:

- **Standard Electronics** — 12-month coverage, accidental damage excluded
- **Premium Coverage** — 24-month coverage, accidental damage included
- **Extended Warranty** — 36-month coverage, includes parts & labour

See `config/warranty_policies/` for full JSON configuration.

---

## Deployment (Production)

For live deployment on Render (free tier):

1. Push code to GitHub
2. Go to [render.com](https://render.com) → New Web Service
3. Connect your GitHub repo
4. Build command: `pip install -r deployment/requirements.txt`
5. Start command: `gunicorn backend.app:app`
6. Add environment variables in Render dashboard

---

## Competition Deliverables Status

| # | Deliverable | Status |
|---|-------------|--------|
| 1 | Project Report (PDF) | `documentation/project_report/` |
| 2 | GitHub Repository + README | `README.md` (this file) |
| 3 | Dataset (CSV + Train/Val/Test) | `dataset/` + `ai_models/python_model/training_data/` |
| 4 | Python Model Training Evidence | `ai_models/python_model/` |
| 5 | Teachable Machine Export | `ai_models/teachable_machine/exported_model/` |
| 6 | Model Comparison Report | `documentation/model_comparison/` |
| 7 | Warranty Policy Config Files | `config/warranty_policies/` |
| 8 | Test Cases Document | `documentation/testing/` |
| 9 | Installation & Execution Guide | This README (above) |
| 10 | Live Deployed Web App | Link in project report |
| 11 | Demonstration Video | Submitted separately |
| 12 | Technical Blog Article | `documentation/` |
| 13 | AI Usage Declaration | `AI_USAGE.md` ✅ |

---

## License

This project was developed for academic competition purposes.  
Team: Maria, Khizra, Urooba, Zainab — September 2026
