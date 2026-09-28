"""
AssureX Python Model Service
Handles loading, feature extraction, inference, and prediction persistence
for the trained AssureX Claim Decision Model (.pkl).
"""

import json
import logging
import os
from pathlib import Path
from typing import Dict, Any, Tuple, Optional, Union
import joblib

from backend.config.model_config import PYTHON_MODEL_PATH, MODEL_TYPE_PYTHON
from backend.extensions import db
from backend.models.prediction import Prediction
from backend.models.model_version import ModelVersion
from backend.services.preprocessing import extract_features_from_claim, prepare_feature_matrix

logger = logging.getLogger(__name__)

# Module-level cache for loaded model package singleton
_MODEL_CACHE: Dict[str, Any] = {}


def load_python_model_package(custom_path: Optional[str] = None) -> Tuple[Optional[dict], Optional[str]]:
    """
    Load the trained Python model package from the given or configured .pkl file path.
    Loads once and caches the package dictionary in memory.

    Returns:
        (package_dict, None) on success, or (None, error_message) on failure.
    """
    target_path_str = custom_path or PYTHON_MODEL_PATH
    target_path = Path(target_path_str).resolve()

    cache_key = str(target_path)
    if cache_key in _MODEL_CACHE:
        return _MODEL_CACHE[cache_key], None

    if not target_path.is_file():
        err_msg = f"Model file not found at path: {target_path}"
        logger.error(err_msg)
        return None, err_msg

    try:
        package = joblib.load(target_path)
        if not isinstance(package, dict):
            return None, f"Invalid model package format: expected dict, got {type(package).__name__}"

        required_keys = ["model", "feature_columns", "classes"]
        for rk in required_keys:
            if rk not in package:
                return None, f"Model package missing required key: '{rk}'"

        _MODEL_CACHE[cache_key] = package
        logger.info("Successfully loaded and cached Python model package from %s", target_path)

        # Register version in database if inside Flask application context
        _try_register_model_version(package)

        return package, None
    except Exception as e:
        err_msg = f"Failed to load Python model file '{target_path.name}': {str(e)}"
        logger.error(err_msg, exc_info=True)
        return None, err_msg


def _try_register_model_version(package: dict) -> None:
    """Register or update ModelVersion record in database if within app context."""
    try:
        model_name = package.get("model_name", MODEL_TYPE_PYTHON)
        existing = db.session.query(ModelVersion).filter_by(model_name=model_name).first()
        if not existing:
            new_mv = ModelVersion(
                model_name=model_name,
                version="1.0.0",
                framework="Scikit-Learn",
                accuracy=float(package.get("test_accuracy", 0.9867)),
                is_active=True,
                notes=f"Average confidence: {package.get('average_confidence', 0.9618):.4f}"
            )
            db.session.add(new_mv)
            db.session.commit()
    except Exception as e:
        logger.debug("ModelVersion auto-registration skipped (outside active DB session): %s", e)


def clear_model_cache() -> None:
    """Clear cached model packages (useful for testing)."""
    _MODEL_CACHE.clear()


def predict_claim_decision(
    claim_or_data: Union[Any, Dict[str, Any]],
    model_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Execute AI inference on structured claim input using the trained Python model.

    Args:
        claim_or_data: A Claim model instance or a raw feature dictionary.
        model_path: Optional override for model .pkl path.

    Returns:
        Dictionary containing prediction results, probabilities, and model metadata,
        or error information.
    """
    package, err = load_python_model_package(model_path)
    if not package:
        return {
            "success": False,
            "error": err or "Model unavailable",
            "message": err or "Python AI model could not be loaded."
        }

    model = package["model"]
    feature_columns = package["feature_columns"]
    classes = package["classes"]
    model_name = package.get("model_name", MODEL_TYPE_PYTHON)
    test_accuracy = package.get("test_accuracy")
    avg_confidence = package.get("average_confidence")

    # 1. Extract feature dictionary
    if isinstance(claim_or_data, dict):
        raw_features = claim_or_data
    else:
        raw_features = extract_features_from_claim(claim_or_data)

    # 2. Prepare aligned feature matrix
    X_aligned = prepare_feature_matrix(raw_features, feature_columns)

    # 3. Model Inference
    try:
        predicted_class_raw = model.predict(X_aligned)[0]
        probabilities_raw = model.predict_proba(X_aligned)[0]
    except Exception as e:
        err_msg = f"Model inference error: {str(e)}"
        logger.error(err_msg, exc_info=True)
        return {
            "success": False,
            "error": err_msg,
            "message": "AI prediction calculation failed."
        }

    # Map class probabilities
    class_probs = {}
    for idx, cls_name in enumerate(classes):
        class_probs[str(cls_name)] = float(probabilities_raw[idx])

    predicted_class = str(predicted_class_raw)
    confidence = float(class_probs.get(predicted_class, max(probabilities_raw)))

    valid_conf = float(class_probs.get("Valid", 0.0))
    invalid_conf = float(class_probs.get("Invalid", 0.0))
    manual_conf = float(class_probs.get("Manual Review", 0.0))

    return {
        "success": True,
        "predicted_class": predicted_class,
        "confidence": confidence,
        "class_probabilities": class_probs,
        "valid_confidence": valid_conf,
        "invalid_confidence": invalid_conf,
        "manual_review_confidence": manual_conf,
        "top_prediction": predicted_class,
        "model_name": model_name,
        "model_version": "1.0.0",
        "test_accuracy": test_accuracy,
        "average_confidence": avg_confidence,
        "features_used": raw_features
    }


def save_claim_prediction(claim_id: int, prediction_result: dict) -> Prediction:
    """
    Save prediction results for a claim into the database.

    Args:
        claim_id: Claim ID integer.
        prediction_result: Output dictionary from predict_claim_decision.

    Returns:
        Newly created Prediction database object.
    """
    metadata_json = json.dumps({
        "test_accuracy": prediction_result.get("test_accuracy"),
        "average_confidence": prediction_result.get("average_confidence"),
        "class_probabilities": prediction_result.get("class_probabilities"),
        "features_used": prediction_result.get("features_used")
    })

    prediction = Prediction(
        claim_id=claim_id,
        model_name=prediction_result.get("model_name", MODEL_TYPE_PYTHON),
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
