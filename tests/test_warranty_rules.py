"""
AssureX Warranty Policy Rules Test Suite (Step 4)
Tests deterministic warranty policy rules:
- Rule 1: Valid date <= expiry date -> active
- Rule 2: Valid date > expiry date -> expired
- Rule 3: No active status after expiry
- Rule 4: Exclusions visible and preserved
- Rule 5: Extended warranties display original and extended details
- Rule 6: Customer tampering protection
"""

import unittest
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from backend.app import create_app
from backend.extensions import db
from backend.models import User, Product, Warranty, AuditLog
from backend.utils.security import ROLE_CUSTOMER, ROLE_ADMIN


class WarrantyPolicyRulesTestCase(unittest.TestCase):
    """Test suite for deterministic warranty policy validation rules."""

    def setUp(self):
        """Setup test context with clean database."""
        self.app = create_app("testing")
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

        self.user = User(
            name="Policy Tester",
            email="policy@test.com",
            password="Password123!",
            role=ROLE_CUSTOMER
        )
        self.admin = User(
            name="Policy Admin",
            email="admin@test.com",
            password="Password123!",
            role=ROLE_ADMIN
        )
        db.session.add_all([self.user, self.admin])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_rule_1_and_2_status_boundaries(self):
        """Test boundary conditions for Rule 1 (Active) and Rule 2 (Expired)."""
        today = date.today()

        prod = Product(
            user_id=self.user.id,
            product_name="Test Device",
            brand="AssureBrand",
            model="TX-100",
            serial_number="SN-TEST-BOUND-1",
            purchase_date=today - timedelta(days=365),
            purchase_price=500.0,
            retailer="Test Store",
            warranty_length=12
        )
        db.session.add(prod)
        db.session.commit()

        # Exactly expiring today
        war_today = Warranty(
            product_id=prod.id,
            warranty_provider="Test Provider",
            start_date=today - timedelta(days=365),
            expiry_date=today,
            warranty_duration=12
        )
        self.assertTrue(war_today.is_active(today))
        self.assertEqual(war_today.calculate_status(today), "Nearing Expiry")

        # Expired yesterday
        war_yesterday = Warranty(
            product_id=prod.id,
            warranty_provider="Test Provider",
            start_date=today - timedelta(days=366),
            expiry_date=today - timedelta(days=1),
            warranty_duration=12
        )
        self.assertFalse(war_yesterday.is_active(today))
        self.assertEqual(war_yesterday.calculate_status(today), "Expired")

    def test_rule_4_exclusions_remain_visible(self):
        """Rule 4: Warranty exclusions must remain visible and accessible in serialization."""
        today = date.today()
        prod = Product(
            user_id=self.user.id,
            product_name="Test Drone",
            brand="SkyFly",
            model="DR-2",
            serial_number="SN-TEST-EXCLUSIONS-1",
            purchase_date=today,
            purchase_price=800.0,
            retailer="Sky Store",
            warranty_length=12
        )
        db.session.add(prod)
        db.session.commit()

        war = Warranty(
            product_id=prod.id,
            warranty_provider="SkyFly Care",
            start_date=today,
            expiry_date=today + relativedelta(months=12),
            warranty_duration=12,
            covered_items="Gimbal, Flight Controller, Rotors",
            exclusions="Water landing, intentional collision, unauthorized third-party propeller blades"
        )
        db.session.add(war)
        db.session.commit()

        d = war.to_dict()
        self.assertIn("Water landing", d["exclusions"])
        self.assertIn("Gimbal", d["covered_items"])

    def test_rule_5_extended_warranty_details(self):
        """Rule 5: If extended, both original warranty information and extension information are maintained."""
        today = date.today()
        prod = Product(
            user_id=self.user.id,
            product_name="Camera 8K",
            brand="Canon",
            model="R5",
            serial_number="SN-CANON-EXT-1",
            purchase_date=today,
            purchase_price=3500.0,
            retailer="B&H",
            warranty_length=12
        )
        db.session.add(prod)
        db.session.commit()

        orig_start = today
        orig_expiry = today + relativedelta(months=12)

        war = Warranty(
            product_id=prod.id,
            warranty_provider="Canon USA",
            start_date=orig_start,
            expiry_date=orig_expiry,
            warranty_duration=12,
            covered_items="Sensor, Shutter",
            exclusions="Sand damage"
        )
        db.session.add(war)
        db.session.commit()

        # Admin extension
        self.client.post("/auth/login", json={"email": "admin@test.com", "password": "Password123!"})
        res = self.client.post(f"/api/warranties/{war.id}/extend", json={
            "duration_months": 24,
            "details": "AssureX Platinum Extended Warranty Coverage"
        })
        self.assertEqual(res.status_code, 200)

        data = res.get_json()["warranty"]
        self.assertEqual(data["warranty_duration"], 12)  # Original duration preserved
        self.assertTrue(data["is_extended"])
        self.assertIn("AssureX Platinum Extended", data["extended_details"])
        self.assertEqual(data["start_date"], orig_start.isoformat())
        self.assertEqual(data["expiry_date"], (orig_expiry + relativedelta(months=24)).isoformat())


if __name__ == "__main__":
    unittest.main()
