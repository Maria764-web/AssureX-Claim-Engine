"""
AssureX AI Model Configuration
Configuration settings for dual-model architecture:
1. Python ML Model (scikit-learn / joblib)
2. Google Teachable Machine Model (Vision / TFJS)
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Model Paths & Endpoints
PYTHON_MODEL_PATH = os.environ.get(
    "PYTHON_MODEL_PATH",
    str(BASE_DIR / "ai_models" / "python_model" / "saved_models" / "assurex_claim_decision_model.pkl")
)
TEACHABLE_MACHINE_MODEL_URL = os.environ.get("TEACHABLE_MACHINE_MODEL_URL", "")
TEACHABLE_MACHINE_MODEL_DIR = os.environ.get(
    "TEACHABLE_MACHINE_MODEL_DIR",
    str(BASE_DIR / "ai_models" / "teachable_machine" / "exported_model")
)
IMAGE_MODEL_PATH = os.environ.get(
    "IMAGE_MODEL_PATH",
    str(BASE_DIR / "ai_models" / "teachable_machine" / "exported_model" / "assurex_image_model.pkl")
)

# Prediction Classes
CLAIM_PREDICTION_CLASSES = ["Valid", "Invalid", "Manual Review"]

# Confidence Thresholds
CONFIDENCE_THRESHOLD_VALID = 0.80
CONFIDENCE_THRESHOLD_REJECT = 0.80
CONFIDENCE_THRESHOLD_MANUAL_REVIEW = 0.60

# Model Framework Identifiers
MODEL_TYPE_PYTHON = "Python ML Model"
MODEL_TYPE_TEACHABLE_MACHINE = "Google Teachable Machine Model"
