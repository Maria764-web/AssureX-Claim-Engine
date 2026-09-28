"""
AssureX Backend Foundation Tests
Verifies app initialization, database connection, health endpoint, error handling,
and model entity relationship integrity.
"""

import unittest
from datetime import date, timedelta
from backend.app import create_app
from backend.extensions import db
from backend.models import (
    User,
    Product,
    Warranty,
    Claim,
    Document,
    RepairHistory,
    Prediction,
    RuleResult,
    Notification,
    AuditLog,
    ModelVersion,
    WARRANTY_ACTIVE,
    CLAIM_STATUS_SUBMITTED,
    DOC_TYPE_RECEIPT,
    RULE_STATUS_PASSED
)
from backend.utils.security import ROLE_CUSTOMER, ROLE_ADMIN, ROLE_REVIEWER, ROLE_SERVICE_CENTER
from backend.utils.helpers import generate_uid


class FoundationTestCase(unittest.TestCase):
    """Test suite for AssureX core architecture foundation."""

    def setUp(self):
        """Set up in-memory test application and database tables."""
        self.app = create_app("testing")
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

    def tearDown(self):
        """Clean up database and pop context."""
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_health_check_endpoint(self):
        """Test GET /health returns 200 and healthy database status."""
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data.get("status"), "healthy")
        self.assertEqual(data.get("database"), "connected")
        self.assertEqual(data.get("service"), "AssureX Claim Engine")

    def test_root_landing_endpoint(self):
        """Test GET / renders the user-facing AssureX landing page (HTML) and not raw JSON."""
        # Unauthenticated request returns HTML landing page
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"AssureX", response.data)
        self.assertIn(b"AI-Powered Document Ops", response.data)
        self.assertIn(b"Sign In to Portal", response.data)
        self.assertIn(b"Create Customer Account", response.data)
        self.assertIn(b"<!DOCTYPE html>", response.data)

        # Even with JSON Accept header, root route / serves the website landing page
        header_res = self.client.get("/", headers={"Accept": "application/json"})
        self.assertEqual(header_res.status_code, 200)
        self.assertIn(b"<!DOCTYPE html>", header_res.data)
        self.assertIn(b"AssureX Claim Engine", header_res.data)


    def test_unique_identifier_format(self):
        """Test cryptographic UID generator creates proper prefixed strings."""
        usr_id = generate_uid("USR")
        prd_id = generate_uid("PRD")
        clm_id = generate_uid("CLM")
        self.assertTrue(usr_id.startswith("USR-"))
        self.assertTrue(prd_id.startswith("PRD-"))
        self.assertTrue(clm_id.startswith("CLM-"))
        self.assertEqual(len(usr_id), 12)  # USR- (4) + 8 chars

    def test_user_creation_and_password_hashing(self):
        """Test user creation, roles, and password hashing security."""
        user = User(
            name="Jane Doe",
            email="jane@example.com",
            password="SecurePassword123!",
            role=ROLE_CUSTOMER,
            phone="+1234567890"
        )
        db.session.add(user)
        db.session.commit()

        self.assertIsNotNone(user.id)
        self.assertTrue(user.user_uid.startswith("USR-"))
        self.assertNotEqual(user.password_hash, "SecurePassword123!")
        self.assertTrue(user.check_password("SecurePassword123!"))
        self.assertFalse(user.check_password("WrongPassword"))
        self.assertEqual(user.role, ROLE_CUSTOMER)

    def test_complete_relational_hierarchy(self):
        """Test cascade relationships: User -> Product -> Warranty -> Claim -> Documents/Predictions/Rules."""
        # 1. User
        customer = User(
            name="Alice Smith",
            email="alice@example.com",
            password="Password123!",
            role=ROLE_CUSTOMER
        )
        db.session.add(customer)
        db.session.commit()

        # 2. Product
        product = Product(
            user_id=customer.id,
            product_name="Smart OLED TV 55-inch",
            brand="Sony",
            model="Bravia XR",
            serial_number="SN-SONY-998877",
            purchase_date=date.today() - timedelta(days=90),
            purchase_price=1299.99,
            retailer="BestBuy",
            warranty_length=24
        )
        db.session.add(product)
        db.session.commit()

        # 3. Warranty
        warranty = Warranty(
            product_id=product.id,
            warranty_provider="Sony Extended Care",
            start_date=date.today() - timedelta(days=90),
            expiry_date=date.today() + timedelta(days=640),
            covered_items="Screen, motherboard, power supply",
            exclusions="Liquid spill, physical drop",
            warranty_status=WARRANTY_ACTIVE
        )
        db.session.add(warranty)
        db.session.commit()

        # 4. Claim
        claim = Claim(
            user_id=customer.id,
            product_id=product.id,
            warranty_id=warranty.id,
            fault_date=date.today() - timedelta(days=2),
            fault_description="Screen has vertical lines across panel without any physical damage.",
            damage_type="Internal Display Fault",
            product_age=3,
            claim_status=CLAIM_STATUS_SUBMITTED
        )
        db.session.add(claim)
        db.session.commit()

        # 5. Document
        doc = Document(
            claim_id=claim.id,
            product_id=product.id,
            document_type=DOC_TYPE_RECEIPT,
            original_filename="receipt_bestbuy.pdf",
            stored_filename="DOC-123456_receipt_bestbuy.pdf",
            stored_path="documents/DOC-123456_receipt_bestbuy.pdf",
            file_extension="pdf",
            mime_type="application/pdf",
            file_size=1048576,
            file_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        )
        db.session.add(doc)

        # 6. Repair History
        repair = RepairHistory(
            product_id=product.id,
            claim_id=claim.id,
            repair_date=date.today() - timedelta(days=1),
            repair_centre="Sony Authorized Service Hub",
            parts_replaced="Display Ribbon Cable",
            repair_cost=150.0,
            is_authorized_centre=True,
            notes="Initial diagnostic complete"
        )
        db.session.add(repair)

        # 7. Prediction
        pred = Prediction(
            claim_id=claim.id,
            model_name="Python ML Model",
            model_version="1.0.0",
            predicted_class="Valid",
            valid_confidence=0.92,
            invalid_confidence=0.05,
            manual_review_confidence=0.03,
            top_prediction="Valid",
            raw_metadata='{"feature_count": 12}'
        )
        db.session.add(pred)

        # 8. Rule Result
        rule = RuleResult(
            claim_id=claim.id,
            rule_name="Warranty Period Check",
            rule_status=RULE_STATUS_PASSED,
            rule_result="Within Valid Warranty Period",
            details="Expiry is in future"
        )
        db.session.add(rule)

        # 9. Notification
        notif = Notification(
            user_id=customer.id,
            title="Claim Received",
            message="Your claim has been submitted successfully."
        )
        db.session.add(notif)

        # 10. Audit Log
        audit = AuditLog(
            user_id=customer.id,
            action="CLAIM_SUBMISSION",
            entity_type="Claim",
            entity_id=claim.claim_uid,
            description="Submitted claim for Smart OLED TV"
        )
        db.session.add(audit)

        # 11. Model Version
        mv = ModelVersion(
            model_name="ClaimClassifierML",
            version="1.0.0",
            framework="Scikit-Learn",
            accuracy=0.94
        )
        db.session.add(mv)

        db.session.commit()

        # Verify cross-relationships
        self.assertEqual(len(customer.products), 1)
        self.assertEqual(customer.products[0].product_name, "Smart OLED TV 55-inch")
        self.assertEqual(len(product.claims), 1)
        self.assertEqual(product.claims[0].claim_uid, claim.claim_uid)
        self.assertEqual(len(claim.documents), 1)
        self.assertEqual(len(claim.predictions), 1)
        self.assertEqual(len(claim.rule_results), 1)
        self.assertEqual(len(customer.notifications), 1)
        self.assertEqual(len(customer.audit_logs), 1)

    def test_error_handler_json_response(self):
        """Test 404 handler returns structured JSON when requested via JSON/API path."""
        response = self.client.get("/api/nonexistent-endpoint-xyz")
        self.assertEqual(response.status_code, 404)
        data = response.get_json()
        self.assertFalse(data.get("success"))
        self.assertEqual(data.get("status_code"), 404)


if __name__ == "__main__":
    unittest.main()
