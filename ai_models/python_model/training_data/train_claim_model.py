"""
AssureX Claim Decision Model - Training Script
Run this on Google Colab or any Python environment with sklearn installed.

Steps:
  1. Upload claims_data.csv (or claims_data.xlsx) to Colab
  2. Run this script
  3. Download assurex_claim_decision_model.pkl
  4. Put it in: ai_models/python_model/saved_models/assurex_claim_decision_model.pkl

Dataset Split (competition requirement):
  - Total: 1,500 claims (500 Valid, 500 Invalid, 500 Manual Review)
  - Training:   70%  -> 1,050 claims
  - Validation: 15%  ->   225 claims
  - Testing:    15%  ->   225 claims
  NOTE: Testing data is never shown to model during training.
"""

import pandas as pd
import numpy as np
import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score

# === PATHS ===
CSV_PATH   = "claims_data.csv"     # primary — CSV format
EXCEL_PATH = "claims_data.xlsx"    # fallback — Excel format
OUTPUT_PKL = "assurex_claim_decision_model.pkl"

# === LOAD DATA ===
print("Loading data...")
try:
    df = pd.read_csv(CSV_PATH)
    print(f"Loaded CSV: {CSV_PATH}")
except FileNotFoundError:
    df = pd.read_excel(EXCEL_PATH)
    print(f"Loaded Excel: {EXCEL_PATH}")
print(f"Rows: {len(df)}, Columns: {list(df.columns)}")

# === FEATURE ENGINEERING ===
# Drop Claim_ID - never use as feature
df = df.drop(columns=["Claim_ID"], errors="ignore")

# Target column
TARGET = "Claim_Decision"
X_raw = df.drop(columns=[TARGET])
y = df[TARGET].astype(str)

print(f"\nClass distribution:\n{y.value_counts()}")

# One-hot encode all categorical columns
X_encoded = pd.get_dummies(X_raw)
feature_columns = list(X_encoded.columns)
print(f"\nFeature columns ({len(feature_columns)}):\n{feature_columns}")

# === DATA SPLIT: 70% Train / 15% Validation / 15% Test ===
# Step 1: Split off 15% test set (never shown to model during training)
X_trainval, X_test, y_trainval, y_test = train_test_split(
    X_encoded, y, test_size=0.15, random_state=42, stratify=y
)
# Step 2: Split remaining 85% into 70% train + 15% validation
#         (0.15 / 0.85 = 0.1765 of trainval gives us 15% of total)
X_train, X_val, y_train, y_val = train_test_split(
    X_trainval, y_trainval, test_size=0.1765, random_state=42, stratify=y_trainval
)
print(f"\nData Split (competition requirement 70/15/15):")
print(f"  Training:   {len(X_train):>4} rows  (70%)")
print(f"  Validation: {len(X_val):>4} rows  (15%)")
print(f"  Testing:    {len(X_test):>4} rows  (15%)")
print(f"  Total:      {len(X_train)+len(X_val)+len(X_test):>4} rows")

# === TRAIN MODEL (on Training set only) ===
print("\nTraining RandomForest on training set...")
model = RandomForestClassifier(
    n_estimators=200,
    max_depth=15,
    min_samples_split=5,
    random_state=42,
    class_weight="balanced",
    n_jobs=-1
)
model.fit(X_train, y_train)

# === EVALUATE ON VALIDATION SET ===
y_val_pred = model.predict(X_val)
val_accuracy = accuracy_score(y_val, y_val_pred)
print(f"\nValidation Accuracy: {val_accuracy:.4f}")
print("\nValidation Classification Report:")
print(classification_report(y_val, y_val_pred))

# === EVALUATE ON TEST SET (held-out, never seen during training) ===
y_test_pred = model.predict(X_test)
test_accuracy = accuracy_score(y_test, y_test_pred)
print(f"\nTest Accuracy (held-out): {test_accuracy:.4f}")
print("\nTest Classification Report:")
print(classification_report(y_test, y_test_pred))

# Average confidence on test set
y_proba = model.predict_proba(X_test)
avg_confidence = float(np.mean(np.max(y_proba, axis=1)))
print(f"Average Confidence: {avg_confidence:.4f}")

# === SAVE IN REQUIRED FORMAT ===
# python_model_service.py expects a dict with these exact keys
model_package = {
    "model": model,
    "feature_columns": feature_columns,
    "classes": list(model.classes_),
    "model_name": "AssureX-RandomForest-v2",
    "test_accuracy": test_accuracy,
    "val_accuracy": val_accuracy,
    "average_confidence": avg_confidence,
    "data_split": {"train": len(X_train), "val": len(X_val), "test": len(X_test)},
    "sklearn_version": "check with: import sklearn; sklearn.__version__"
}

joblib.dump(model_package, OUTPUT_PKL)
print(f"\nModel saved to: {OUTPUT_PKL}")
print(f"Classes: {model_package['classes']}")
print("\nDONE! Download this pkl and put it in:")
print("  ai_models/python_model/saved_models/assurex_claim_decision_model.pkl")
