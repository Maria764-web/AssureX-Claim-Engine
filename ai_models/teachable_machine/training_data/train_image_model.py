"""
AssureX Image Model - Training Script
Run this on Google Colab or any Python environment.

Steps:
  1. Upload AssureX_TeachableMachine_Training.zip to Colab
  2. Run this script
  3. Download assurex_image_model.pkl
  4. Put it in: ai_models/teachable_machine/exported_model/assurex_image_model.pkl

Image folder structure expected (inside zip):
  Valid/
  Invalid/
  Manual_Review/
"""

import os
import zipfile
import numpy as np
import joblib
from PIL import Image
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report

# === PATHS ===
ZIP_PATH = "AssureX_TeachableMachine_Training.zip"
EXTRACT_DIR = "training_images"
OUTPUT_PKL = "assurex_image_model.pkl"
IMG_SIZE = (64, 64)  # resize all images to this

# === EXTRACT ZIP ===
if not os.path.exists(EXTRACT_DIR):
    print("Extracting zip...")
    with zipfile.ZipFile(ZIP_PATH, "r") as z:
        z.extractall(EXTRACT_DIR)
    print("Extracted.")

# === LOAD IMAGES ===
CLASS_NAMES = ["Valid", "Invalid", "Manual_Review"]
CLASS_LABEL_MAP = {"Valid": "Valid", "Invalid": "Invalid", "Manual_Review": "Manual Review"}

def extract_image_features(img_path: str, size=(64, 64)):
    """Extract feature vector from image: pixel values + color stats."""
    try:
        img = Image.open(img_path).convert("RGB").resize(size)
        arr = np.array(img, dtype=np.float32) / 255.0
        # Flatten pixels
        pixels = arr.flatten()
        # Color statistics per channel
        r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
        stats = np.array([
            r.mean(), r.std(), r.min(), r.max(),
            g.mean(), g.std(), g.min(), g.max(),
            b.mean(), b.std(), b.min(), b.max(),
            # Brightness
            arr.mean(), arr.std(),
            # Contrast proxy
            arr.max() - arr.min()
        ])
        return np.concatenate([pixels, stats])
    except Exception as e:
        print(f"  Skipping {img_path}: {e}")
        return None

X, y = [], []
print("Loading images and extracting features...")
for class_folder in CLASS_NAMES:
    folder_path = os.path.join(EXTRACT_DIR, class_folder)
    if not os.path.exists(folder_path):
        print(f"  WARNING: folder not found: {folder_path}")
        continue
    label = CLASS_LABEL_MAP.get(class_folder, class_folder)
    files = [f for f in os.listdir(folder_path) if f.lower().endswith((".jpg", ".jpeg", ".png"))]
    print(f"  {class_folder}: {len(files)} images -> label='{label}'")
    for fname in files:
        path = os.path.join(folder_path, fname)
        feat = extract_image_features(path, IMG_SIZE)
        if feat is not None:
            X.append(feat)
            y.append(label)

X = np.array(X)
y = np.array(y)
print(f"\nDataset: {X.shape[0]} images, {X.shape[1]} features each")
print(f"Classes: {np.unique(y)}")

# === TRAIN ===
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)
print(f"\nTrain: {len(X_train)}, Test: {len(X_test)}")

print("Training RandomForest on image features...")
model = RandomForestClassifier(
    n_estimators=100,
    max_depth=20,
    random_state=42,
    class_weight="balanced",
    n_jobs=-1
)
model.fit(X_train, y_train)

# === EVALUATE ===
y_pred = model.predict(X_test)
test_accuracy = accuracy_score(y_test, y_pred)
print(f"\nTest Accuracy: {test_accuracy:.4f}")
print("\nClassification Report:")
print(classification_report(y_test, y_pred))

y_proba = model.predict_proba(X_test)
avg_confidence = float(np.mean(np.max(y_proba, axis=1)))
print(f"Average Confidence: {avg_confidence:.4f}")

# === SAVE ===
image_model_package = {
    "model": model,
    "classes": list(model.classes_),
    "img_size": list(IMG_SIZE),
    "model_name": "AssureX-ImageClassifier-v1",
    "test_accuracy": test_accuracy,
    "average_confidence": avg_confidence
}
joblib.dump(image_model_package, OUTPUT_PKL)
print(f"\nImage model saved to: {OUTPUT_PKL}")
print("\nDONE! Download and put in:")
print("  ai_models/teachable_machine/exported_model/assurex_image_model.pkl")
