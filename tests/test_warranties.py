"""
AssureX Warranty Management & Policy Rules Test Suite (Step 4)
Tests customer warranty access, dynamic status calculations, IDOR protections,
role-based inspections (Service Centre, Reviewer, Admin), deterministic policy rules,
and controlled admin warranty extensions with audit logging.
"""

import unittest
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from backend.app import create_app
from backend.extensions import db
from backend.models import User, Product, Warranty, AuditLog
from backend.utils.security import (
    ROLE_CUSTOMER,
    ROLE_SERVICE_CENTER,
    ROLE_REVIEWER,
    ROLE_ADMIN
)


class WarrantyTestCase(unittest.TestCase):
    """Test suite for warranty management, policy rules, and role-based access."""

    def setUp(self):
        """Set up in-memory test database and seed sample users and products with warranties."""
        self.app = create_app("testing")
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

        # Seed 4 accounts representing the 4 system roles
        self.customer_a = User(
            name="Alice Customer",
            email="alice@test.com",
            password="Password123!",
            role=ROLE_CUSTOMER
        )
        self.customer_b = User(
            name="Bob Customer",
            email="bob@test.com",
            password="Password123!",
            role=ROLE_CUSTOMER
        )
        self.service_emp = User(
            name="Sam Service",
            email="sam@service.com",
            password="Password123!",
            role=ROLE_SERVICE_CENTER
        )
        self.reviewer = User(
            name="Rachel Reviewer",
            email="rachel@reviewer.com",
            password="Password123!",
            role=ROLE_REVIEWER
        )
        self.admin = User(
            name="Adam Admin",
            email="admin@test.com",
            password="Password123!",
            role=ROLE_ADMIN
        )
        db.session.add_all([
            self.customer_a, self.customer_b,
            self.service_emp, self.reviewer, self.admin
        ])
        db.session.commit()

        # Seed products and warranties for Customer A
        today = date.today()

        # 1. Active Warranty (Purchased 30 days ago, 12 months duration)
        self.prod_a1 = Product(
            user_id=self.customer_a.id,
            product_name="Ultra OLED TV 55",
            brand="LG",
            model="OLED55",
            serial_number="SN-ALICE-OLED1",
            purchase_date=today - timedelta(days=30),
            purchase_price=1299.99,
            retailer="BestBuy",
            warranty_length=12
        )
        db.session.add(self.prod_a1)
        db.session.commit()

        self.war_a1 = Warranty(
            product_id=self.prod_a1.id,
            warranty_provider="LG Electronics Direct",
            start_date=today - timedelta(days=30),
            expiry_date=today - timedelta(days=30) + relativedelta(months=12),
            warranty_duration=12,
            covered_items="Display panel, power supply, main logic board, internal speaker modules",
            exclusions="Accidental drop damage, liquid ingress, unauthorized third-party disassembly, screen burn-in due to static image display exceeding 8 consecutive hours"
        )

        # 2. Nearing Expiry Warranty (Expires in 15 days)
        self.prod_a2 = Product(
            user_id=self.customer_a.id,
            product_name="Pro Noise-Canceling Headphones",
            brand="Sony",
            model="WH-1000XM5",
            serial_number="SN-ALICE-SONY1",
            purchase_date=today - timedelta(days=350),
            purchase_price=399.99,
            retailer="Amazon",
            warranty_length=12
        )
        db.session.add(self.prod_a2)
        db.session.commit()

        self.war_a2 = Warranty(
            product_id=self.prod_a2.id,
            warranty_provider="Sony Corporation",
            start_date=today - timedelta(days=350),
            expiry_date=today + timedelta(days=15),
            warranty_duration=12,
            covered_items="Acoustic drivers, active noise-cancellation microchips, battery charging circuit",
            exclusions="Cosmetic earpad wear, sweat/water submersion, cracked headband from impact"
        )

        # 3. Expired Warranty (Expired 45 days ago)
        self.prod_a3 = Product(
            user_id=self.customer_a.id,
            product_name="Old Blender Pro",
            brand="NutriBullet",
            model="NB-900",
            serial_number="SN-ALICE-BLEND1",
            purchase_date=today - timedelta(days=410),
            purchase_price=99.99,
            retailer="Target",
            warranty_length=12
        )
        db.session.add(self.prod_a3)
        db.session.commit()

        self.war_a3 = Warranty(
            product_id=self.prod_a3.id,
            warranty_provider="NutriBullet Warranty Care",
            start_date=today - timedelta(days=410),
            expiry_date=today - timedelta(days=45),
            warranty_duration=12,
            covered_items="Motor base, drive socket, blade assembly",
            exclusions="Plastic cup cracking from thermal shock, blade dulling from normal grinding wear"
        )

        # Seed a product and warranty for Customer B
        self.prod_b1 = Product(
            user_id=self.customer_b.id,
            product_name="Galaxy Flagship Smartphone",
            brand="Samsung",
            model="S24 Ultra",
            serial_number="SN-BOB-SAMSUNG1",
            purchase_date=today - timedelta(days=60),
            purchase_price=1199.99,
            retailer="Samsung Direct",
            warranty_length=24
        )
        db.session.add(self.prod_b1)
        db.session.commit()

        self.war_b1 = Warranty(
            product_id=self.prod_b1.id,
            warranty_provider="Samsung Direct",
            start_date=today - timedelta(days=60),
            expiry_date=today - timedelta(days=60) + relativedelta(months=24),
            warranty_duration=24,
            covered_items="Motherboard, OLED touch matrix, camera modules",
            exclusions="Cracked glass, submersion beyond IP68 rating, root/jailbreak firmware alterations"
        )

        db.session.add_all([self.war_a1, self.war_a2, self.war_a3, self.war_b1])
        db.session.commit()

    def tearDown(self):
        """Clean up database and pop context."""
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    # =========================================================================
    # 1. DYNAMIC WARRANTY STATUS & POLICY RULES TESTS
    # =========================================================================

    def test_dynamic_warranty_status_calculation(self):
        """Test dynamic calculation of warranty statuses: Active, Nearing Expiry, Expired, Extended."""
        today = date.today()

        # Rule 1: Future expiry > 30 days -> Active
        self.assertEqual(self.war_a1.calculate_status(as_of_date=today), "Active")
        self.assertTrue(self.war_a1.is_active(as_of_date=today))

        # Rule 1b: Expiry within 30 days -> Nearing Expiry
        self.assertEqual(self.war_a2.calculate_status(as_of_date=today), "Nearing Expiry")
        self.assertTrue(self.war_a2.is_active(as_of_date=today))

        # Rule 2: Past expiry -> Expired
        self.assertEqual(self.war_a3.calculate_status(as_of_date=today), "Expired")
        self.assertFalse(self.war_a3.is_active(as_of_date=today))

        # Rule 5: Extended warranty -> Extended
        self.war_a1.is_extended = True
        self.assertEqual(self.war_a1.calculate_status(as_of_date=today), "Extended")

    def test_expired_warranty_cannot_be_active(self):
        """Rule 3: A product cannot have an active warranty after its warranty expiry date."""
        today = date.today()
        self.assertTrue(self.war_a3.expiry_date < today)
        self.assertFalse(self.war_a3.is_active(as_of_date=today))
        self.assertEqual(self.war_a3.calculate_status(as_of_date=today), "Expired")

    # =========================================================================
    # 2. CUSTOMER WARRANTY VIEW & IDOR PROTECTION TESTS
    # =========================================================================

    def test_customer_can_view_own_warranties_api_and_browser(self):
        """Test customer can view list of their own warranties via API and browser HTML."""
        # Login as Customer A
        self.client.post("/auth/login", json={"email": "alice@test.com", "password": "Password123!"})

        # Browser GET /warranties
        res_html = self.client.get("/warranties")
        self.assertEqual(res_html.status_code, 200)
        content = res_html.data.decode("utf-8")
        self.assertIn("My Warranties &amp; Policy Certificates", content)
        self.assertIn("Ultra OLED TV 55", content)
        self.assertIn("SN-ALICE-OLED1", content)
        self.assertIn("Pro Noise-Canceling Headphones", content)
        self.assertIn(self.war_a1.warranty_uid, content)

        # Must NOT include Customer B's products
        self.assertNotIn("Galaxy Flagship Smartphone", content)
        self.assertNotIn("SN-BOB-SAMSUNG1", content)

        # API GET /api/warranties
        res_api = self.client.get("/api/warranties")
        self.assertEqual(res_api.status_code, 200)
        data = res_api.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("count"), 3)
        uids = [w["warranty_uid"] for w in data["warranties"]]
        self.assertIn(self.war_a1.warranty_uid, uids)
        self.assertNotIn(self.war_b1.warranty_uid, uids)

    def test_customer_can_view_own_warranty_detail(self):
        """Test customer can view certificate detail of their own warranty."""
        self.client.post("/auth/login", json={"email": "alice@test.com", "password": "Password123!"})

        res = self.client.get(f"/warranties/{self.war_a1.id}")
        self.assertEqual(res.status_code, 200)
        content = res.data.decode("utf-8")
        self.assertIn("Official Warranty Certificate", content)
        self.assertIn(self.war_a1.warranty_uid, content)
        self.assertIn("LG Electronics Direct", content)
        self.assertIn("Display panel, power supply", content)
        self.assertIn("Accidental drop damage", content)

    def test_idor_customer_cannot_view_other_customer_warranty(self):
        """
        CRITICAL SECURITY TEST: Prevent IDOR.
        Customer A attempting to access Customer B's warranty via:
        1. Numeric DB ID (/warranties/<id>)
        2. Warranty UID (/warranties/by-uid/<uid>)
        3. API endpoint (/api/warranties/<id>)
        MUST return 403 Forbidden.
        """
        # Login as Customer A (Alice)
        self.client.post("/auth/login", json={"email": "alice@test.com", "password": "Password123!"})

        # 1. Access by numeric ID via Browser (redirected with forbidden flash)
        res1 = self.client.get(f"/warranties/{self.war_b1.id}")
        self.assertEqual(res1.status_code, 302)
        self.assertIn("/warranties", res1.headers.get("Location"))

        # 2. Access by UID via Browser (redirected)
        res2 = self.client.get(f"/warranties/by-uid/{self.war_b1.warranty_uid}")
        self.assertEqual(res2.status_code, 302)

        # 3. Access via API by ID (returns 403 Forbidden)
        res3 = self.client.get(f"/api/warranties/{self.war_b1.id}")
        self.assertEqual(res3.status_code, 403)
        data3 = res3.get_json()
        self.assertFalse(data3.get("success"))

        # 4. Access via API by UID (returns 403 Forbidden)
        res4 = self.client.get(f"/api/warranties/by-uid/{self.war_b1.warranty_uid}")
        self.assertEqual(res4.status_code, 403)
        data4 = res4.get_json()
        self.assertFalse(data4.get("success"))

    def test_customer_cannot_modify_warranty_dates_or_status(self):
        """Rule 6: Customers cannot manually alter warranty provider, dates, or status."""
        self.client.post("/auth/login", json={"email": "alice@test.com", "password": "Password123!"})

        # Attempting POST/PUT on extension route as customer
        res = self.client.post(
            f"/api/warranties/{self.war_a1.id}/extend",
            json={"duration_months": 12, "details": "Customer unauthorized extension"}
        )
        self.assertEqual(res.status_code, 403)

    # =========================================================================
    # 3. SERVICE-CENTRE EMPLOYEE WARRANTY LOOKUP TESTS
    # =========================================================================

    def test_service_centre_employee_warranty_lookup(self):
        """Test Service-Centre Employee can search and inspect warranties across all products."""
        self.client.post("/auth/login", json={"email": "sam@service.com", "password": "Password123!"})

        # Can access lookup page
        res = self.client.get("/warranties")
        self.assertEqual(res.status_code, 200)
        content = res.data.decode("utf-8")
        self.assertIn("Service Centre Warranty Verification Hub", content)

        # Search by Serial Number
        res_sn = self.client.get(f"/warranties?q={self.prod_a1.serial_number}")
        self.assertEqual(res_sn.status_code, 200)
        self.assertIn(self.war_a1.warranty_uid, res_sn.data.decode("utf-8"))

        # Search by Warranty UID
        res_uid = self.client.get(f"/warranties?q={self.war_b1.warranty_uid}")
        self.assertEqual(res_uid.status_code, 200)
        self.assertIn(self.prod_b1.product_name, res_uid.data.decode("utf-8"))

        # Inspect specific warranty details
        res_detail = self.client.get(f"/warranties/{self.war_a1.id}")
        self.assertEqual(res_detail.status_code, 200)

        # Service-Centre employee cannot extend warranty (Admin only)
        res_ext = self.client.post(
            f"/api/warranties/{self.war_a1.id}/extend",
            json={"duration_months": 6, "details": "Technician attempt"}
        )
        self.assertEqual(res_ext.status_code, 403)

    # =========================================================================
    # 4. CLAIM REVIEWER WARRANTY INSPECTION TESTS
    # =========================================================================

    def test_claim_reviewer_warranty_inspection(self):
        """Test Claim Reviewer can inspect warranty details and policy clauses for claim review."""
        self.client.post("/auth/login", json={"email": "rachel@reviewer.com", "password": "Password123!"})

        # Can view warranties list
        res = self.client.get("/warranties")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Claim Reviewer Policy Inspection Hub", res.data.decode("utf-8"))

        # Can inspect warranty certificate and exclusions
        res_detail = self.client.get(f"/warranties/{self.war_a1.id}")
        self.assertEqual(res_detail.status_code, 200)
        content = res_detail.data.decode("utf-8")
        self.assertIn("Accidental drop damage", content)
        self.assertIn("Display panel, power supply", content)

        # Reviewer cannot extend warranty (Admin only)
        res_ext = self.client.post(
            f"/api/warranties/{self.war_a1.id}/extend",
            json={"duration_months": 6, "details": "Reviewer attempt"}
        )
        self.assertEqual(res_ext.status_code, 403)

    # =========================================================================
    # 5. ADMINISTRATOR WARRANTY MANAGEMENT & EXTENSION TESTS
    # =========================================================================

    def test_admin_can_view_and_filter_all_warranties(self):
        """Test Administrator can view all warranties and filter by status."""
        self.client.post("/auth/login", json={"email": "admin@test.com", "password": "Password123!"})

        # List all warranties
        res = self.client.get("/warranties")
        self.assertEqual(res.status_code, 200)
        content = res.data.decode("utf-8")
        self.assertIn("Global Warranty Management &amp; Policy Control", content)
        self.assertIn(self.war_a1.warranty_uid, content)
        self.assertIn(self.war_b1.warranty_uid, content)

        # Filter by status: active
        res_active = self.client.get("/warranties?status=active")
        self.assertEqual(res_active.status_code, 200)
        active_content = res_active.data.decode("utf-8")
        self.assertIn(self.war_a1.warranty_uid, active_content)
        self.assertNotIn(self.war_a3.warranty_uid, active_content)

        # Filter by status: expired
        res_expired = self.client.get("/warranties?status=expired")
        self.assertEqual(res_expired.status_code, 200)
        expired_content = res_expired.data.decode("utf-8")
        self.assertIn(self.war_a3.warranty_uid, expired_content)
        self.assertNotIn(self.war_a1.warranty_uid, expired_content)

    def test_admin_warranty_extension_and_audit_log(self):
        """Test Administrator extending a warranty updates expiry date and creates audit log."""
        self.client.post("/auth/login", json={"email": "admin@test.com", "password": "Password123!"})

        old_expiry = self.war_a1.expiry_date
        extension_months = 12

        payload = {
            "duration_months": extension_months,
            "details": "AssureX Loyalty Care Plan Extended by Admin"
        }

        res = self.client.post(f"/api/warranties/{self.war_a1.id}/extend", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data["warranty"]["status"], "Extended")
        self.assertTrue(data["warranty"]["is_extended"])

        # Reload from DB
        updated_war = db.session.get(Warranty, self.war_a1.id)
        self.assertTrue(updated_war.is_extended)
        self.assertEqual(updated_war.expiry_date, old_expiry + relativedelta(months=extension_months))
        self.assertIn("AssureX Loyalty Care Plan", updated_war.extended_details)

        # Verify Audit Log entry was generated
        audit = AuditLog.query.filter_by(action="WARRANTY_EXTENDED", entity_id=self.war_a1.warranty_uid).first()
        self.assertIsNotNone(audit)
        self.assertIn("Admin", audit.description)
        self.assertIn("extended warranty", audit.description)

    # =========================================================================
    # 6. PRODUCT DETAIL LINKS TO WARRANTY TEST
    # =========================================================================

    def test_product_detail_links_to_warranty(self):
        """Test product detail page contains link to View Full Warranty Certificate."""
        self.client.post("/auth/login", json={"email": "alice@test.com", "password": "Password123!"})

        res = self.client.get(f"/products/{self.prod_a1.id}")
        self.assertEqual(res.status_code, 200)
        content = res.data.decode("utf-8")
        self.assertIn("View Full Warranty Certificate", content)
        self.assertIn(f"/warranties/{self.war_a1.id}", content)

    # =========================================================================
    # 7. UNAUTHORIZED ACCESS PROTECTION
    # =========================================================================

    def test_unauthenticated_user_redirected_to_login(self):
        """Test unauthenticated user is redirected to login when accessing /warranties."""
        res_browser = self.client.get("/warranties")
        self.assertEqual(res_browser.status_code, 302)
        self.assertIn("/auth/login", res_browser.headers.get("Location"))

        res_api = self.client.get("/api/warranties")
        self.assertEqual(res_api.status_code, 401)


if __name__ == "__main__":
    unittest.main()
