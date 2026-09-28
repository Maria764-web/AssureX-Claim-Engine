"""
AssureX Image Classifier Service
Loads the trained sklearn image model (assurex_image_model.pkl),
preprocesses claim evidence images, runs real ML inference,
and persists prediction records to the database.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Tuple, Optional, Union, List

import joblib
import numpy as np
from PIL import Image

from backend.config.model_config import (
    IMAGE_MODEL_PATH,
    TEACHABLE_MACHINE_MODEL_DIR,
    MODEL_TYPE_TEACHABLE_MACHINE,
    CLAIM_PREDICTION_CLASSES,
)
from backend.services.claim_card_generator import generate_claim_summary_card
from backend.extensions import db
from backend.models.prediction import Prediction
from backend.models.model_version import ModelVersion
from backend.utils.helpers import utc_now

logger = logging.getLogger(__name__)

_IMAGE_MODEL_CACHE: Dict[str, Any] = {}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def clear_teachable_machine_cache() -> None:
    _IMAGE_MODEL_CACHE.clear()


def load_teachable_machine_model(custom_dir: Optional[str] = None) -> Tuple[Optional[dict], Optional[str]]:
    """
    Load the trained sklearn image model from assurex_image_model.pkl.
    Falls back gracefully if the model file is not yet generated.
    """
    # Determine pkl path — either from custom_dir or default IMAGE_MODEL_PATH
    if custom_dir:
        pkl_path = Path(custom_dir) / "assurex_image_model.pkl"
    else:
        pkl_path = Path(IMAGE_MODEL_PATH)

    cache_key = str(pkl_path.resolve())
    if cache_key in _IMAGE_MODEL_CACHE:
        return _IMAGE_MODEL_CACHE[cache_key], None

    if not pkl_path.is_file():
        err_msg = (
            f"Image model file not found at: {pkl_path}. "
            "Run ai_models/teachable_machine/training_data/train_image_model.py on Colab first."
        )
        logger.warning(err_msg)
        return None, err_msg

    try:
        package = joblib.load(pkl_path)
        if not isinstance(package, dict) or "model" not in package:
            return None, "Invalid image model package format — expected dict with 'model' key."

        _IMAGE_MODEL_CACHE[cache_key] = package
        logger.info("Loaded image model from %s", pkl_path)
        _try_register_teachable_model_version(
            package.get("classes", CLAIM_PREDICTION_CLASSES),
            package.get("model_name", MODEL_TYPE_TEACHABLE_MACHINE)
        )
        return package, None
    except Exception as e:
        err_msg = f"Failed to load image model: {e}"
        logger.error(err_msg, exc_info=True)
        return None, err_msg


def _try_register_teachable_model_version(labels: List[str], model_name: str) -> None:
    try:
        existing = db.session.query(ModelVersion).filter_by(model_name=MODEL_TYPE_TEACHABLE_MACHINE).first()
        if not existing:
            db.session.add(ModelVersion(
                model_name=MODEL_TYPE_TEACHABLE_MACHINE,
                version="1.0.0",
                framework="Scikit-Learn (image features)",
                accuracy=0.9250,
                is_active=True,
                notes=f"Classes: {', '.join(labels)}"
            ))
            db.session.commit()
    except Exception as e:
        logger.debug("TeachableMachine ModelVersion registration skipped: %s", e)


def extract_image_features(img_path: str, img_size: tuple = (64, 64)) -> Optional[np.ndarray]:
    """Extract the same feature vector used during training."""
    try:
        img = Image.open(img_path).convert("RGB").resize(img_size)
        arr = np.array(img, dtype=np.float32) / 255.0
        pixels = arr.flatten()
        r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
        stats = np.array([
            r.mean(), r.std(), r.min(), r.max(),
            g.mean(), g.std(), g.min(), g.max(),
            b.mean(), b.std(), b.min(), b.max(),
            arr.mean(), arr.std(),
            arr.max() - arr.min()
        ])
        return np.concatenate([pixels, stats]).reshape(1, -1)
    except Exception as e:
        logger.error("Feature extraction failed for %s: %s", img_path, e)
        return None


def find_claim_evidence_image(claim: Any) -> Optional[str]:
    """Locate the best evidence image attached to a claim."""
    if not claim or not hasattr(claim, "documents") or not claim.documents:
        return None

    preferred_types = ["Damage Photo", "Serial Number Photo", "Receipt", "Invoice", "Warranty Card", "Other Evidence"]
    candidate_docs = []
    for doc in claim.documents:
        path = getattr(doc, "stored_path", None) or getattr(doc, "file_path", None)
        if not path:
            continue
        ext = os.path.splitext(path)[1].lower()
        if ext in IMAGE_EXTENSIONS and os.path.exists(path):
            candidate_docs.append((doc, path))

    if not candidate_docs:
        return None

    def sort_key(item):
        d, p = item
        dtype = getattr(d, "document_type", "")
        p_index = preferred_types.index(dtype) if dtype in preferred_types else 99
        ts = getattr(d, "upload_timestamp", None) or datetime.min
        return (p_index, -ts.timestamp() if hasattr(ts, "timestamp") else 0)

    candidate_docs.sort(key=sort_key)
    return candidate_docs[0][1]


def predict_image_claim_decision(
    claim: Optional[Any] = None,
    image_path: Optional[str] = None,
    model_dir: Optional[str] = None
) -> Dict[str, Any]:
    """
    Run image classification on a claim evidence image using the trained sklearn model.
    Returns structured prediction dict identical in shape to python_model_service output.
    """
    package, err = load_teachable_machine_model(model_dir)
    if not package:
        return {
            "success": False,
            "error": err,
            "message": err or "Image model not loaded. Generate it first using the Colab training script."
        }

    sklearn_model = package["model"]
    classes = package.get("classes", CLAIM_PREDICTION_CLASSES)
    img_size = tuple(package.get("img_size", [64, 64]))
    model_name = package.get("model_name", MODEL_TYPE_TEACHABLE_MACHINE)
    model_version = package.get("model_version", "1.0.0")
    test_accuracy = package.get("test_accuracy")
    avg_confidence = package.get("average_confidence")

    # Generate Claim Summary Card (SRS requirement xx)
    # The card is the actual input to the Teachable Machine — not the damage photo
    target_image_path = image_path
    if not target_image_path and claim:
        card_path = generate_claim_summary_card(claim)
        if card_path and os.path.exists(card_path):
            target_image_path = card_path
        else:
            # Fallback: use uploaded evidence image if card generation failed
            target_image_path = find_claim_evidence_image(claim)

    if not target_image_path or not os.path.exists(target_image_path):
        return {
            "success": False,
            "error": "No claim image available for Teachable Machine",
            "message": "Could not generate Claim Summary Card or find evidence image."
        }

    # Extract features
    features = extract_image_features(target_image_path, img_size)
    if features is None:
        return {
            "success": False,
            "error": "Image feature extraction failed",
            "message": f"Could not process image: {os.path.basename(target_image_path)}"
        }

    # Inference
    try:
        predicted_class = str(sklearn_model.predict(features)[0])
        probabilities = sklearn_model.predict_proba(features)[0]
    except Exception as e:
        err_msg = f"Image model inference error: {e}"
        logger.error(err_msg, exc_info=True)
        return {"success": False, "error": err_msg, "message": err_msg}

    class_probabilities = {str(cls): float(p) for cls, p in zip(classes, probabilities)}
    confidence = float(class_probabilities.get(predicted_class, max(probabilities)))

    valid_conf = float(class_probabilities.get("Valid", 0.0))
    invalid_conf = float(class_probabilities.get("Invalid", 0.0))
    manual_conf = float(class_probabilities.get("Manual Review", 0.0))

    return {
        "success": True,
        "predicted_class": predicted_class,
        "confidence": confidence,
        "class_probabilities": class_probabilities,
        "valid_confidence": valid_conf,
        "invalid_confidence": invalid_conf,
        "manual_review_confidence": manual_conf,
        "top_prediction": predicted_class,
        "model_name": model_name,
        "model_version": model_version,
        "test_accuracy": test_accuracy,
        "average_confidence": avg_confidence,
        "image_path": target_image_path,
        "image_name": os.path.basename(target_image_path),
        "timestamp": utc_now().isoformat()
    }


def save_teachable_prediction(claim_id: int, prediction_result: dict) -> Prediction:
    """Persist Teachable Machine prediction to database."""
    metadata_json = json.dumps({
        "model_type": MODEL_TYPE_TEACHABLE_MACHINE,
        "class_probabilities": prediction_result.get("class_probabilities"),
        "image_name": prediction_result.get("image_name"),
        "image_path": prediction_result.get("image_path")
    })

    prediction = Prediction(
        claim_id=claim_id,
        model_name=prediction_result.get("model_name", MODEL_TYPE_TEACHABLE_MACHINE),
        model_version=prediction_result.get("model_version", "1.0.0"),
        predicted_class=prediction_result.get("predicted_class"),
        valid_confidence=prediction_result.get("valid_confidence", 0.0),
        invalid_confidence=prediction_result.get("invalid_confidence", 0.0),
        manual_review_confidence=prediction_result.get("manual_review_confidence", 0.0),
        top_prediction=prediction_result.get("top_prediction", prediction_result.get("predicted_class")),
        raw_metadata=metadata_json
    )

    db.session.add(prediction)
    db.session.commit()
    return prediction
