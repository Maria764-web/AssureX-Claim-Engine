"""
AssureX Step 5D Test Suite: Teachable Machine Model Integration
Tests Teachable Machine model directory & files existence, metadata loading,
graceful handling of missing/corrupt model files, authentication & IDOR security checks,
image evidence prediction execution, response structure, and regression check for Python model.
"""

import os
import unittest
from datetime import date
from pathlib import Path
from PIL import Image

from backend.app import create_app
from backend.extensions import db
from backend.models.user import User
from backend.models.product import Product
from backend.models.claim import Claim
from backend.models.document import Document
from backend.models.prediction import Prediction
from backend.services.teachable_machine_service import (
    load_teachable_machine_model,
    predict_image_claim_decision,
    save_teachable_prediction,
    clear_teachable_machine_cache,
    find_claim_evidence_image
)
from backend.services.python_model_service import (
    predict_claim_decision,
    load_python_model_package
)
from backend.utils.security import ROLE_CUSTOMER, ROLE_ADMIN, ROLE_REVIEWER


class TestTeachableMachineIntegration(unittest.TestCase):
    def setUp(self):
        self.app = create_app("testing")
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.client = self.app.test_client()

        db.create_all()
        clear_teachable_machine_cache()

        # Setup test users
        self.customer1 = User(
            name="Test Customer 1",
            email="cust1_tm_test@assurex.com",
            password="Password123!",
            role=ROLE_CUSTOMER
        )
        self.customer2 = User(
            name="Test Customer 2",
            email="cust2_tm_test@assurex.com",
            password="Password123!",
            role=ROLE_CUSTOMER
        )
        self.reviewer = User(
            name="Test Reviewer",
            email="reviewer_tm_test@assurex.com",
            password="Password123!",
            role=ROLE_REVIEWER
        )
        db.session.add_all([self.customer1, self.customer2, self.reviewer])
        db.session.commit()

        # Setup test product and claim
        self.product1 = Product(
            user_id=self.customer1.id,
            product_name="Samsung Galaxy S24",
            brand="Samsung",
            model="SM-S921B",
            serial_number="SN-SSG-2026-88",
            purchase_date=date(2025, 3, 10),
            purchase_price=899.99
        )
        db.session.add(self.product1)
        db.session.commit()

        self.claim1 = Claim(
            user_id=self.customer1.id,
            product_id=self.product1.id,
            fault_date=date(2026, 7, 1),
            fault_description="Cracked OLED display after drop",
            damage_type="Physical Damage",
            product_age=16,
            claim_status="Submitted"
        )
        db.session.add(self.claim1)
        db.session.commit()

        # Temporary test image setup
        self.test_img_path = Path("instance") / "test_damage_evidence.jpg"
        self.test_img_path.parent.mkdir(parents=True, exist_ok=True)
        img = Image.new("RGB", (224, 224), color=(200, 100, 50))
        img.save(self.test_img_path)

    def tearDown(self):
        if self.test_img_path.exists():
            try:
                os.remove(self.test_img_path)
            except OSError:
                pass
        db.session.remove()
        db.drop_all()
        self.app_context.pop()
        clear_teachable_machine_cache()

    # 1. Test model files exist
    def test_model_files_exist(self):
        export_dir = Path("ai_models/teachable_machine/exported_model")
        self.assertTrue(export_dir.exists(), "Teachable Machine model directory must exist")
        self.assertTrue((export_dir / "model.json").exists(), "model.json must exist")
        self.assertTrue((export_dir / "metadata.json").exists(), "metadata.json must exist")

    # 2. Test metadata & class labels load correctly
    def test_metadata_and_classes_load(self):
        package, err = load_teachable_machine_model()
        self.assertIsNone(err, f"Model loading failed: {err}")
        self.assertIsNotNone(package)
        self.assertIn("labels", package)
        self.assertCountEqual(package["labels"], ["Valid", "Invalid", "Manual Review"])
        self.assertEqual(package.get("model_name"), "Google Teachable Machine Model")

    # 3. Test service handles missing or corrupt model gracefully
    def test_service_handles_missing_model_gracefully(self):
        clear_teachable_machine_cache()
        package, err = load_teachable_machine_model(custom_dir="non_existent_dir_xyz")
        self.assertIsNone(package)
        self.assertIsNotNone(err)
        self.assertIn("not found", err)

        res = predict_image_claim_decision(claim=self.claim1, model_dir="non_existent_dir_xyz")
        self.assertFalse(res["success"])
        self.assertIn("error", res)
        self.assertIn("not found", res["error"])

    # 4. Test endpoint authentication required
    def test_endpoint_authentication_required(self):
        response = self.client.post(f"/api/claims/{self.claim1.id}/teachable-predict")
        # Unauthenticated request should return 401 or 302 redirect to login
        self.assertIn(response.status_code, [401, 302])

    # 5. Test ownership protection (IDOR)
    def test_endpoint_ownership_protection_idor(self):
        with self.client as c:
            with c.session_transaction() as sess:
                sess["_user_id"] = str(self.customer2.id)
                sess["_fresh"] = True
            response = c.post(f"/api/claims/{self.claim1.id}/teachable-predict")
            self.assertEqual(response.status_code, 403)
            data = response.get_json()
            self.assertFalse(data.get("success"))
            self.assertEqual(data.get("error"), "Forbidden")

    # 6. Test prediction when no claim image available
    def test_prediction_no_claim_image_available(self):
        with self.client as c:
            with c.session_transaction() as sess:
                sess["_user_id"] = str(self.customer1.id)
                sess["_fresh"] = True
            response = c.post(f"/api/claims/{self.claim1.id}/teachable-predict")
            self.assertEqual(response.status_code, 400)
            data = response.get_json()
            self.assertFalse(data.get("success"))
            self.assertIn("No claim evidence image available", data.get("message", ""))

    # 7. Test prediction response structure with evidence image
    def test_prediction_response_structure_with_image(self):
        doc = Document(
            claim_id=self.claim1.id,
            document_uid="DOC-TEST-IMG-001",
            document_type="Damage Photo",
            original_filename="test_damage_evidence.jpg",
            stored_filename="test_damage_evidence.jpg",
            stored_path=str(self.test_img_path),
            file_size=1024,
            file_extension="jpg",
            file_hash="test_hash_1234567890"
        )
        db.session.add(doc)
        db.session.commit()

        found_img = find_claim_evidence_image(self.claim1)
        self.assertIsNotNone(found_img)
        self.assertEqual(os.path.abspath(found_img), os.path.abspath(str(self.test_img_path)))

        with self.client as c:
            with c.session_transaction() as sess:
                sess["_user_id"] = str(self.customer1.id)
                sess["_fresh"] = True
            response = c.post(f"/api/claims/{self.claim1.id}/teachable-predict")
            self.assertEqual(response.status_code, 200)
            data = response.get_json()
            self.assertTrue(data.get("success"))
            self.assertIn(data.get("predicted_class"), ["Valid", "Invalid", "Manual Review"])
            self.assertGreaterEqual(data.get("confidence", 0), 0.0)
            self.assertLessEqual(data.get("confidence", 0), 1.0)
            self.assertEqual(data.get("model_name"), "Google Teachable Machine Model")
            self.assertEqual(data.get("model_version"), "1.0.0")
            self.assertIn("timestamp", data)
            self.assertIn("prediction", data)
            self.assertEqual(data["prediction"]["claim_id"], self.claim1.id)

    # 8. Test no regression to Python model
    def test_no_regression_to_python_model(self):
        package, err = load_python_model_package()
        self.assertIsNone(err)
        self.assertIsNotNone(package)
        self.assertEqual(package.get("model_name"), "AssureX Calibrated Decision Tree")

        res = predict_claim_decision(self.claim1)
        self.assertTrue(res.get("success"))
        self.assertIn(res.get("predicted_class"), ["Valid", "Invalid", "Manual Review"])

        with self.client as c:
            with c.session_transaction() as sess:
                sess["_user_id"] = str(self.customer1.id)
                sess["_fresh"] = True
            response = c.post(f"/api/claims/{self.claim1.id}/predict")
            self.assertEqual(response.status_code, 200)
            data = response.get_json()
            self.assertTrue(data.get("success"))
            self.assertIn("prediction", data)


if __name__ == "__main__":
    unittest.main()
