"""
AssureX Step 5C Test Suite: Python Model Integration
Tests model loading, feature preparation, prediction calculation,
database persistence, and API endpoint security.
"""

import unittest
from pathlib import Path
from backend.app import create_app
from backend.extensions import db
from backend.models.user import User
from backend.models.product import Product
from backend.models.claim import Claim
from backend.models.prediction import Prediction
from backend.services.python_model_service import (
    load_python_model_package,
    predict_claim_decision,
    save_claim_prediction,
    clear_model_cache
)
from backend.services.preprocessing import extract_features_from_claim, prepare_feature_matrix
from backend.utils.security import ROLE_CUSTOMER, ROLE_ADMIN, ROLE_REVIEWER


class TestPythonModelIntegration(unittest.TestCase):
    def setUp(self):
        self.app = create_app("testing")
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.client = self.app.test_client()

        db.create_all()
        clear_model_cache()

        # Setup test users
        self.customer1 = User(
            name="Test Customer 1",
            email="cust1_python_test@assurex.com",
            password="Password123!",
            role=ROLE_CUSTOMER
        )
        self.customer2 = User(
            name="Test Customer 2",
            email="cust2_python_test@assurex.com",
            password="Password123!",
            role=ROLE_CUSTOMER
        )
        self.reviewer = User(
            name="Test Reviewer",
            email="reviewer_python_test@assurex.com",
            password="Password123!",
            role=ROLE_REVIEWER
        )
        db.session.add_all([self.customer1, self.customer2, self.reviewer])
        db.session.commit()

        # Setup test product and claim
        from datetime import date
        self.product1 = Product(
            user_id=self.customer1.id,
            product_name="iPhone 15 Pro",
            brand="Apple",
            model="A3090",
            serial_number="SN-APL-2026-99",
            purchase_date=date(2025, 1, 15),
            purchase_price=999.99
        )
        db.session.add(self.product1)
        db.session.commit()

        self.claim1 = Claim(
            user_id=self.customer1.id,
            product_id=self.product1.id,
            fault_date=date(2026, 6, 1),
            fault_description="Screen touch non-responsive after update",
            damage_type="Hardware Defect",
            product_age=16,
            claim_status="Submitted"
        )
        db.session.add(self.claim1)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()
        clear_model_cache()

    # 1. Model File Exists
    def test_model_file_exists(self):
        model_path = Path("ai_models/python_model/saved_models/assurex_claim_decision_model.pkl")
        self.assertTrue(model_path.exists(), "Model file assurex_claim_decision_model.pkl must exist on disk")

    # 2. Model Loads Successfully & Package Metadata
    def test_model_load_and_metadata(self):
        package, err = load_python_model_package()
        self.assertIsNone(err, f"Model package failed to load: {err}")
        self.assertIsNotNone(package)
        self.assertIn("model", package)
        self.assertIn("feature_columns", package)
        self.assertIn("classes", package)
        self.assertEqual(package.get("model_name"), "AssureX Calibrated Decision Tree")
        self.assertGreater(package.get("test_accuracy", 0), 0.90)

    # 3. Expected Classes
    def test_model_classes(self):
        package, _ = load_python_model_package()
        classes = list(package["classes"])
        self.assertCountEqual(classes, ["Invalid", "Manual Review", "Valid"])

    # 4. Feature Preparation & Alignment
    def test_feature_preparation_and_alignment(self):
        package, _ = load_python_model_package()
        feature_cols = package["feature_columns"]

        raw_data = extract_features_from_claim(self.claim1)
        self.assertNotIn("Claim_ID", raw_data)

        df_aligned = prepare_feature_matrix(raw_data, feature_cols)
        self.assertEqual(list(df_aligned.columns), feature_cols)
        self.assertEqual(len(df_aligned), 1)

    # 5. Missing and Extra Columns Handling
    def test_missing_and_extra_columns(self):
        package, _ = load_python_model_package()
        feature_cols = package["feature_columns"]

        # Partial raw data missing several columns, plus an unexpected extra column
        partial_data = {
            "Product_Category": "Mobile",
            "UNEXPECTED_EXTRA_COLUMN": "TestValue",
            "Claim_ID": "CLM-99999"  # Must be stripped
        }
        df_aligned = prepare_feature_matrix(partial_data, feature_cols)
        self.assertEqual(list(df_aligned.columns), feature_cols)
        self.assertNotIn("UNEXPECTED_EXTRA_COLUMN", df_aligned.columns)
        self.assertNotIn("Claim_ID", df_aligned.columns)

    # 6. Model Prediction & Probabilities
    def test_prediction_inference(self):
        res = predict_claim_decision(self.claim1)
        self.assertTrue(res["success"])
        self.assertIn(res["predicted_class"], ["Invalid", "Manual Review", "Valid"])
        self.assertGreaterEqual(res["confidence"], 0.0)
        self.assertLessEqual(res["confidence"], 1.0)
        self.assertIn("class_probabilities", res)
        for cls_name in ["Invalid", "Manual Review", "Valid"]:
            self.assertIn(cls_name, res["class_probabilities"])
            self.assertGreaterEqual(res["class_probabilities"][cls_name], 0.0)
            self.assertLessEqual(res["class_probabilities"][cls_name], 1.0)

    # 7. Database Persistence
    def test_database_persistence(self):
        res = predict_claim_decision(self.claim1)
        prediction_obj = save_claim_prediction(self.claim1.id, res)
        self.assertIsNotNone(prediction_obj.id)
        self.assertEqual(prediction_obj.claim_id, self.claim1.id)
        self.assertEqual(prediction_obj.predicted_class, res["predicted_class"])

        # Fetch from DB
        fetched = db.session.get(Prediction, prediction_obj.id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.model_name, "AssureX Calibrated Decision Tree")

    def _login_as(self, user):
        with self.client.session_transaction() as sess:
            sess["_user_id"] = str(user.id)
            sess["_fresh"] = True

    # 8. API Predict Endpoint (Authenticated Owner)
    def test_api_predict_authenticated_owner(self):
        with self.client as c:
            with c.session_transaction() as sess:
                sess["_user_id"] = str(self.customer1.id)
                sess["_fresh"] = True
            response = c.post(f"/api/claims/{self.claim1.id}/predict")
            self.assertEqual(response.status_code, 200)
            json_data = response.get_json()
            self.assertTrue(json_data.get("success"))
            self.assertIn("prediction", json_data)
            self.assertIn(json_data["prediction"]["predicted_class"], ["Invalid", "Manual Review", "Valid"])

    # 9. API Predict Endpoint IDOR Protection (Unauthorized Customer)
    def test_api_predict_unauthorized_idor(self):
        with self.client as c:
            with c.session_transaction() as sess:
                sess["_user_id"] = str(self.customer2.id)
                sess["_fresh"] = True
            response = c.post(f"/api/claims/{self.claim1.id}/predict")
            self.assertEqual(response.status_code, 403)
            json_data = response.get_json()
            self.assertFalse(json_data.get("success"))
            self.assertEqual(json_data.get("error"), "Forbidden")

    # 10. API Predict Endpoint Nonexistent Claim
    def test_api_predict_missing_claim(self):
        with self.client as c:
            with c.session_transaction() as sess:
                sess["_user_id"] = str(self.customer1.id)
                sess["_fresh"] = True
            response = c.post("/api/claims/999999/predict")
            self.assertEqual(response.status_code, 404)

    # 11. Controlled Error for Missing Model File
    def test_missing_model_file_controlled_error(self):
        clear_model_cache()
        res = predict_claim_decision(self.claim1, model_path="nonexistent_model.pkl")
        self.assertFalse(res["success"])
        self.assertIn("error", res)
        self.assertIn("nonexistent_model.pkl", res["error"])

    # 12. Prediction Status & Get Prediction Endpoints
    def test_prediction_status_route(self):
        with self.client as c:
            with c.session_transaction() as sess:
                sess["_user_id"] = str(self.reviewer.id)
                sess["_fresh"] = True
            response = c.get("/api/predictions/status")
            self.assertEqual(response.status_code, 200)
            data = response.get_json()
            self.assertTrue(data.get("model_loaded"))
            self.assertEqual(data.get("model_name"), "AssureX Calibrated Decision Tree")


if __name__ == "__main__":
    unittest.main()
