"""
AssureX Product Registration & Management Test Suite (Step 3)
Tests Customer Product Registration, Validation, Unique UID Generation,
Automatic Warranty Creation, Ownership Enforcement, IDOR Protection, Duplicate Serial Check, and Listing Isolation.
"""

import unittest
from datetime import date, timedelta
from backend.app import create_app
from backend.extensions import db
from backend.models import User, Product, Warranty, AuditLog
from backend.utils.security import ROLE_CUSTOMER, ROLE_ADMIN


class ProductTestCase(unittest.TestCase):
    """Test suite for product registration, management, and validation."""

    def setUp(self):
        """Set up in-memory test database and seed sample users."""
        self.app = create_app("testing")
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

        # Seed two customers and one admin
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
        self.admin = User(
            name="Adam Admin",
            email="admin@test.com",
            password="Password123!",
            role=ROLE_ADMIN
        )
        db.session.add_all([self.customer_a, self.customer_b, self.admin])
        db.session.commit()

    def tearDown(self):
        """Clean up database and pop context."""
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    # =========================================================================
    # 1. PRODUCT REGISTRATION TESTS
    # =========================================================================

    def test_valid_product_registration(self):
        """Test valid product registration generates PRD UID and creates default Warranty."""
        # Login as Customer A
        self.client.post("/auth/login", json={"email": "alice@test.com", "password": "Password123!"})

        purchase_date_str = (date.today() - timedelta(days=30)).isoformat()
        payload = {
            "product_name": "Smart 4K Television 65-Inch",
            "brand": "LG",
            "model": "OLED65C3",
            "serial_number": "SN-LG-987654321",
            "purchase_date": purchase_date_str,
            "purchase_price": 1799.99,
            "retailer": "BestBuy Online",
            "warranty_length": 24
        }
        response = self.client.post("/api/products", json=payload)
        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        self.assertTrue(data.get("success"))

        prod_data = data["product"]
        self.assertEqual(prod_data["product_name"], "Smart 4K Television 65-Inch")
        self.assertEqual(prod_data["brand"], "LG")
        self.assertEqual(prod_data["serial_number"], "SN-LG-987654321")
        self.assertTrue(prod_data["product_uid"].startswith("PRD-"))
        self.assertEqual(prod_data["user_id"], self.customer_a.id)

        # Verify Warranty was automatically generated
        war_data = data["warranty"]
        self.assertTrue(war_data["warranty_uid"].startswith("WAR-"))
        self.assertEqual(war_data["warranty_status"], "Active")

        # Verify Audit Log
        audit = AuditLog.query.filter_by(action="PRODUCT_REGISTERED").first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.entity_id, prod_data["product_uid"])

    def test_user_id_spoofing_prevented(self):
        """
        CRITICAL SECURITY TEST:
        Customer A sending user_id of Customer B in registration payload
        MUST be ignored, and product MUST belong to Customer A.
        """
        self.client.post("/auth/login", json={"email": "alice@test.com", "password": "Password123!"})

        payload = {
            "user_id": self.customer_b.id,  # Attempt to spoof owner
            "product_name": "Wireless Noise Cancelling Headphones",
            "brand": "Sony",
            "model": "WH-1000XM5",
            "serial_number": "SN-SONY-XM5-1122",
            "purchase_date": date.today().isoformat(),
            "purchase_price": 399.00,
            "retailer": "Amazon",
            "warranty_length": 12
        }
        response = self.client.post("/api/products", json=payload)
        self.assertEqual(response.status_code, 201)
        data = response.get_json()

        # Product must be assigned to Alice (Customer A), NOT Bob
        product = db.session.get(Product, data["product"]["id"])
        self.assertEqual(product.user_id, self.customer_a.id)
        self.assertNotEqual(product.user_id, self.customer_b.id)

    # =========================================================================
    # 2. VALIDATION TESTS
    # =========================================================================

    def test_missing_required_fields_rejected(self):
        """Test registration with missing mandatory fields is rejected with 400."""
        self.client.post("/auth/login", json={"email": "alice@test.com", "password": "Password123!"})

        # Empty payload
        response = self.client.post("/api/products", json={})
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertFalse(data.get("success"))
        self.assertTrue(len(data.get("errors", [])) >= 4)

    def test_future_purchase_date_rejected(self):
        """Test purchase date in the future is rejected."""
        self.client.post("/auth/login", json={"email": "alice@test.com", "password": "Password123!"})

        future_date = (date.today() + timedelta(days=10)).isoformat()
        payload = {
            "product_name": "Future Phone",
            "brand": "Apple",
            "model": "iPhone 16",
            "serial_number": "SN-IP16-9999",
            "purchase_date": future_date,
            "purchase_price": 999.00,
            "retailer": "Apple Store",
            "warranty_length": 12
        }
        response = self.client.post("/api/products", json=payload)
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertTrue(any("cannot be in the future" in err for err in data.get("errors", [])))

    def test_negative_price_rejected(self):
        """Test negative purchase price is rejected."""
        self.client.post("/auth/login", json={"email": "alice@test.com", "password": "Password123!"})

        payload = {
            "product_name": "Negative Price Item",
            "brand": "BrandX",
            "model": "ModelY",
            "serial_number": "SN-XYZ-1234",
            "purchase_date": date.today().isoformat(),
            "purchase_price": -50.00,
            "retailer": "Retailer",
            "warranty_length": 12
        }
        response = self.client.post("/api/products", json=payload)
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertTrue(any("positive" in err for err in data.get("errors", [])))

    def test_invalid_serial_number_format_rejected(self):
        """Test serial number with invalid characters is rejected."""
        self.client.post("/auth/login", json={"email": "alice@test.com", "password": "Password123!"})

        payload = {
            "product_name": "Invalid Serial Item",
            "brand": "BrandX",
            "model": "ModelY",
            "serial_number": "SN @@@ /// !!!",
            "purchase_date": date.today().isoformat(),
            "purchase_price": 100.00,
            "retailer": "Retailer",
            "warranty_length": 12
        }
        response = self.client.post("/api/products", json=payload)
        self.assertEqual(response.status_code, 400)

    def test_duplicate_serial_number_rejected(self):
        """Test registering the same serial number twice under the same customer is rejected."""
        self.client.post("/auth/login", json={"email": "alice@test.com", "password": "Password123!"})

        payload = {
            "product_name": "Phone One",
            "brand": "BrandA",
            "model": "ModelA",
            "serial_number": "SN-DUPLICATE-999",
            "purchase_date": date.today().isoformat(),
            "purchase_price": 500.00,
            "retailer": "Retailer A",
            "warranty_length": 12
        }
        res1 = self.client.post("/api/products", json=payload)
        self.assertEqual(res1.status_code, 201)

        # Attempt to register identical serial number under same user
        res2 = self.client.post("/api/products", json=payload)
        self.assertEqual(res2.status_code, 400)
        data2 = res2.get_json()
        self.assertTrue(any("already registered" in err for err in data2.get("errors", [])))

    # =========================================================================
    # 3. LISTING & ISOLATION TESTS
    # =========================================================================

    def test_customer_only_sees_own_products(self):
        """Customer A only receives their own products in GET /api/products."""
        # Create product for Customer A
        prod_a = Product(
            user_id=self.customer_a.id,
            product_name="Alice Tablet",
            brand="Apple",
            model="iPad Pro",
            serial_number="SN-ALICE-1111",
            purchase_date=date.today(),
            purchase_price=800.0,
            retailer="Apple Store",
            warranty_length=12
        )
        # Create product for Customer B
        prod_b = Product(
            user_id=self.customer_b.id,
            product_name="Bob Monitor",
            brand="Dell",
            model="UltraSharp",
            serial_number="SN-BOB-2222",
            purchase_date=date.today(),
            purchase_price=600.0,
            retailer="Dell",
            warranty_length=24
        )
        db.session.add_all([prod_a, prod_b])
        db.session.commit()

        # Login as Alice
        self.client.post("/auth/login", json={"email": "alice@test.com", "password": "Password123!"})
        res = self.client.get("/api/products")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["products"][0]["product_name"], "Alice Tablet")

    def test_admin_sees_all_registered_products(self):
        """Administrator receives all products from all customers."""
        prod_a = Product(
            user_id=self.customer_a.id,
            product_name="Alice Item",
            brand="BrandA",
            model="ModelA",
            serial_number="SN-A-1",
            purchase_date=date.today(),
            purchase_price=100.0,
            retailer="Store",
            warranty_length=12
        )
        prod_b = Product(
            user_id=self.customer_b.id,
            product_name="Bob Item",
            brand="BrandB",
            model="ModelB",
            serial_number="SN-B-1",
            purchase_date=date.today(),
            purchase_price=200.0,
            retailer="Store",
            warranty_length=12
        )
        db.session.add_all([prod_a, prod_b])
        db.session.commit()

        self.client.post("/auth/login", json={"email": "admin@test.com", "password": "Password123!"})
        res = self.client.get("/api/products")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["count"] >= 2)

    # =========================================================================
    # 4. PRODUCT DETAIL & IDOR PROTECTION TESTS
    # =========================================================================

    def test_get_product_by_id_and_uid(self):
        """Customer can retrieve their own product by ID and UID with attached warranties."""
        prod = Product(
            user_id=self.customer_a.id,
            product_name="Gaming Laptop",
            brand="ASUS",
            model="ROG Zephyrus",
            serial_number="SN-ASUS-9999",
            purchase_date=date.today() - timedelta(days=10),
            purchase_price=2199.0,
            retailer="MicroCenter",
            warranty_length=12
        )
        db.session.add(prod)
        db.session.commit()

        war = Warranty(
            product_id=prod.id,
            warranty_provider="ASUS ROG Care",
            start_date=date.today() - timedelta(days=10),
            expiry_date=date.today() + timedelta(days=355),
            warranty_status="Active"
        )
        db.session.add(war)
        db.session.commit()

        self.client.post("/auth/login", json={"email": "alice@test.com", "password": "Password123!"})

        # By numeric ID
        res_id = self.client.get(f"/api/products/{prod.id}")
        self.assertEqual(res_id.status_code, 200)
        data_id = res_id.get_json()
        self.assertTrue(data_id["success"])
        self.assertEqual(data_id["product"]["product_uid"], prod.product_uid)
        self.assertEqual(len(data_id["warranties"]), 1)

        # By public UID
        res_uid = self.client.get(f"/api/products/by-uid/{prod.product_uid}")
        self.assertEqual(res_uid.status_code, 200)
        data_uid = res_uid.get_json()
        self.assertTrue(data_uid["success"])
        self.assertEqual(data_uid["product"]["id"], prod.id)

    def test_customer_cannot_access_other_customer_product_by_uid(self):
        """Customer A cannot access Customer B's product by UID (returns 403)."""
        prod_b = Product(
            user_id=self.customer_b.id,
            product_name="Bob Secret Laptop",
            brand="Apple",
            model="MacBook Pro",
            serial_number="SN-MAC-BOB-99",
            purchase_date=date.today(),
            purchase_price=2499.0,
            retailer="Apple",
            warranty_length=12
        )
        db.session.add(prod_b)
        db.session.commit()

        self.client.post("/auth/login", json={"email": "alice@test.com", "password": "Password123!"})
        res = self.client.get(f"/api/products/by-uid/{prod_b.product_uid}")
        self.assertEqual(res.status_code, 403)


if __name__ == "__main__":
    unittest.main()
