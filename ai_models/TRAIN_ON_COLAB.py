"""
==========================================================
AssureX - Complete Model Training Script for Google Colab
==========================================================

INSTRUCTIONS:
  1. Open Google Colab: https://colab.research.google.com
  2. Upload this file + both data files to Colab:
       - claims_data.xlsx   (from ai_models/python_model/training_data/)
       - AssureX_TeachableMachine_Training.zip  (original zip file)
  3. Run this entire script
  4. Download 2 files:
       - assurex_claim_decision_model.pkl
       - assurex_image_model.pkl
  5. Place them in your project:
       assurex_claim_decision_model.pkl
         → ai_models/python_model/saved_models/assurex_claim_decision_model.pkl
       assurex_image_model.pkl
         → ai_models/teachable_machine/exported_model/assurex_image_model.pkl

INSTALL (Colab already has most of these):
  !pip install scikit-learn pandas openpyxl Pillow joblib numpy
==========================================================
"""

import os, zipfile
import numpy as np
import pandas as pd
import joblib
from PIL import Image
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report

# ──────────────────────────────────────────────
# PART 1: CLAIM DECISION MODEL (from Excel)
# ──────────────────────────────────────────────
print("=" * 60)
print("PART 1: Training Claim Decision Model from Excel")
print("=" * 60)

df = pd.read_excel("claims_data.xlsx")
df = df.drop(columns=["Claim_ID"], errors="ignore")

TARGET = "Claim_Decision"
X_raw = df.drop(columns=[TARGET])
y = df[TARGET].astype(str)

print(f"Rows: {len(df)}")
print(f"Class distribution:\n{y.value_counts()}\n")

X_encoded = pd.get_dummies(X_raw)
feature_columns = list(X_encoded.columns)

X_train, X_test, y_train, y_test = train_test_split(
    X_encoded, y, test_size=0.2, random_state=42, stratify=y
)

clf_model = RandomForestClassifier(
    n_estimators=200, max_depth=15,
    min_samples_split=5, random_state=42,
    class_weight="balanced", n_jobs=-1
)
clf_model.fit(X_train, y_train)

y_pred = clf_model.predict(X_test)
test_acc = accuracy_score(y_test, y_pred)
avg_conf = float(np.mean(np.max(clf_model.predict_proba(X_test), axis=1)))

print(f"Accuracy: {test_acc:.4f}")
print(classification_report(y_test, y_pred))

claim_model_pkg = {
    "model": clf_model,
    "feature_columns": feature_columns,
    "classes": list(clf_model.classes_),
    "model_name": "AssureX-RandomForest-v2",
    "test_accuracy": test_acc,
    "average_confidence": avg_conf
}
joblib.dump(claim_model_pkg, "assurex_claim_decision_model.pkl")
print("Saved: assurex_claim_decision_model.pkl\n")

# ──────────────────────────────────────────────
# PART 2: IMAGE CLASSIFIER (from images zip)
# ──────────────────────────────────────────────
print("=" * 60)
print("PART 2: Training Image Classifier from Images")
print("=" * 60)

ZIP_PATH = "AssureX_TeachableMachine_Training.zip"
EXTRACT_DIR = "training_images"
IMG_SIZE = (64, 64)
CLASS_MAP = {"Valid": "Valid", "Invalid": "Invalid", "Manual_Review": "Manual Review"}

if not os.path.exists(EXTRACT_DIR):
    with zipfile.ZipFile(ZIP_PATH, "r") as z:
        z.extractall(EXTRACT_DIR)
    print("Extracted zip.")

def get_features(path, size=(64, 64)):
    try:
        img = Image.open(path).convert("RGB").resize(size)
        arr = np.array(img, dtype=np.float32) / 255.0
        pixels = arr.flatten()
        r, g, b = arr[:,:,0], arr[:,:,1], arr[:,:,2]
        stats = np.array([
            r.mean(), r.std(), r.min(), r.max(),
            g.mean(), g.std(), g.min(), g.max(),
            b.mean(), b.std(), b.min(), b.max(),
            arr.mean(), arr.std(), arr.max()-arr.min()
        ])
        return np.concatenate([pixels, stats])
    except:
        return None

X_img, y_img = [], []
for folder, label in CLASS_MAP.items():
    fpath = os.path.join(EXTRACT_DIR, folder)
    if not os.path.exists(fpath):
        print(f"  WARNING: {fpath} not found")
        continue
    files = [f for f in os.listdir(fpath) if f.lower().endswith((".jpg",".jpeg",".png"))]
    print(f"  {folder}: {len(files)} images")
    for f in files:
        feat = get_features(os.path.join(fpath, f), IMG_SIZE)
        if feat is not None:
            X_img.append(feat)
            y_img.append(label)

X_img = np.array(X_img)
y_img = np.array(y_img)
print(f"\nImage dataset: {X_img.shape[0]} samples, {X_img.shape[1]} features")

Xi_train, Xi_test, yi_train, yi_test = train_test_split(
    X_img, y_img, test_size=0.2, random_state=42, stratify=y_img
)

img_model = RandomForestClassifier(
    n_estimators=100, max_depth=20,
    random_state=42, class_weight="balanced", n_jobs=-1
)
img_model.fit(Xi_train, yi_train)

yi_pred = img_model.predict(Xi_test)
img_acc = accuracy_score(yi_test, yi_pred)
img_conf = float(np.mean(np.max(img_model.predict_proba(Xi_test), axis=1)))

print(f"Image Accuracy: {img_acc:.4f}")
print(classification_report(yi_test, yi_pred))

img_model_pkg = {
    "model": img_model,
    "classes": list(img_model.classes_),
    "img_size": list(IMG_SIZE),
    "model_name": "AssureX-ImageClassifier-v1",
    "test_accuracy": img_acc,
    "average_confidence": img_conf
}
joblib.dump(img_model_pkg, "assurex_image_model.pkl")
print("Saved: assurex_image_model.pkl\n")

# ──────────────────────────────────────────────
# DOWNLOAD FILES (run in Colab)
# ──────────────────────────────────────────────
print("=" * 60)
print("DONE! Now download both files:")
print("  assurex_claim_decision_model.pkl")
print("  assurex_image_model.pkl")
print("=" * 60)

# Uncomment in Colab to auto-download:
# from google.colab import files
# files.download("assurex_claim_decision_model.pkl")
# files.download("assurex_image_model.pkl")
