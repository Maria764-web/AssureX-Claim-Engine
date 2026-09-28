"""
AssureX Frontend Integration & Navigation Test Suite
Validates the complete web browsing flow for Steps 1-3:
Register -> Login -> Dashboard (DB metrics) -> Products -> Register Product (HTML form) -> Product Details -> Profile -> Logout.
"""

import unittest
from datetime import date, timedelta
from backend.app import create_app
from backend.extensions import db
from backend.models import User, Product, Warranty
from backend.models.warranty import WARRANTY_ACTIVE, WARRANTY_EXPIRED
from backend.utils.security import (
    ROLE_CUSTOMER,
    ROLE_SERVICE_CENTER,
    ROLE_REVIEWER,
    ROLE_ADMIN
)


class FrontendIntegrationTestCase(unittest.TestCase):
    """End-to-end integration test suite for customer website experience."""

    def setUp(self):
        """Initialize test client and clean in-memory database."""
        self.app = create_app("testing")
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

        # Seed initial customer
        self.customer = User(
            name="Sarah Jenkins",
            email="sarah@example.com",
            phone="+1 555-0144",
            password="SecurePassword123!",
            role=ROLE_CUSTOMER
        )
        db.session.add(self.customer)
        db.session.commit()

    def tearDown(self):
        """Teardown database context."""
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_customer_registration_html_flow(self):
        """Test registration via HTML form redirects to login with success flash."""
        response = self.client.post("/auth/register", data={
            "name": "Marcus Vance",
            "email": "marcus@example.com",
            "phone": "+1 555-0188",
            "password": "StrongPassword123!",
            "confirm_password": "StrongPassword123!"
        }, follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Registration successful", response.data)
        self.assertIn(b"Sign in to your account", response.data)

        # Confirm user was saved in DB
        user = User.query.filter_by(email="marcus@example.com").first()
        self.assertIsNotNone(user)
        self.assertEqual(user.role, ROLE_CUSTOMER)

    def test_customer_login_and_dashboard_db_metrics(self):
        """Test customer login redirects to /dashboard with live DB summary counts."""
        # 1. Login
        login_res = self.client.post("/auth/login", data={
            "email": "sarah@example.com",
            "password": "SecurePassword123!"
        }, follow_redirects=False)
        self.assertEqual(login_res.status_code, 302)
        self.assertIn("/dashboard", login_res.headers.get("Location", ""))

        # 2. Access dashboard with 0 products
        dash_res = self.client.get("/dashboard")
        self.assertEqual(dash_res.status_code, 200)
        self.assertIn(b"Welcome back, Sarah Jenkins", dash_res.data)
        self.assertIn(b"No Products Registered Yet", dash_res.data)
        self.assertIn(b"Registered Products", dash_res.data)

        # 3. Seed 2 products: 1 Active, 1 Expired
        p1 = Product(
            user_id=self.customer.id,
            product_name="MacBook Pro 16",
            brand="Apple",
            model="M3 Max",
            serial_number="SN-APPL-12345",
            purchase_date=date.today() - timedelta(days=60),
            purchase_price=2499.00,
            retailer="Apple Store",
            warranty_length=24
        )
        p2 = Product(
            user_id=self.customer.id,
            product_name="Sony Headphones",
            brand="Sony",
            model="WH-1000XM5",
            serial_number="SN-SONY-67890",
            purchase_date=date.today() - timedelta(days=400),
            purchase_price=399.00,
            retailer="BestBuy",
            warranty_length=12
        )
        db.session.add_all([p1, p2])
        db.session.flush()

        w1 = Warranty(
            product_id=p1.id,
            warranty_provider="AppleCare+",
            start_date=p1.purchase_date,
            expiry_date=p1.purchase_date + timedelta(days=730),
            covered_items="All hardware defects",
            exclusions="Intentional damage",
            warranty_status=WARRANTY_ACTIVE
        )
        w2 = Warranty(
            product_id=p2.id,
            warranty_provider="Sony Manufacturer Warranty",
            start_date=p2.purchase_date,
            expiry_date=p2.purchase_date + timedelta(days=365),
            covered_items="Audio hardware",
            exclusions="Water damage",
            warranty_status=WARRANTY_EXPIRED
        )
        db.session.add_all([w1, w2])
        db.session.commit()

        # 4. Reload dashboard and verify database metrics
        dash_res2 = self.client.get("/dashboard")
        self.assertEqual(dash_res2.status_code, 200)
        self.assertIn(b"MacBook Pro 16", dash_res2.data)
        self.assertIn(b"Sony Headphones", dash_res2.data)
        self.assertIn(b"View Details", dash_res2.data)

    def test_product_registration_html_form_flow(self):
        """Test full HTML product registration flow with redirect to product detail page."""
        # Login
        self.client.post("/auth/login", data={
            "email": "sarah@example.com",
            "password": "SecurePassword123!"
        })

        # GET registration form
        form_page = self.client.get("/products/register")
        self.assertEqual(form_page.status_code, 200)
        self.assertIn(b"Register New Product", form_page.data)

        # POST registration form
        purchase_date_str = (date.today() - timedelta(days=10)).isoformat()
        reg_res = self.client.post("/products/register", data={
            "product_name": "UltraWide OLED Monitor 34-Inch",
            "brand": "Dell Alienware",
            "model": "AW3423DWF",
            "serial_number": "SN-DELL-556677",
            "purchase_date": purchase_date_str,
            "purchase_price": "899.99",
            "retailer": "Dell Direct Online",
            "warranty_length": "36"
        }, follow_redirects=True)

        self.assertEqual(reg_res.status_code, 200)
        # Should render product detail page with success message
        self.assertIn(b"registered successfully", reg_res.data)
        self.assertIn(b"UltraWide OLED Monitor 34-Inch", reg_res.data)
        self.assertIn(b"AW3423DWF", reg_res.data)
        self.assertIn(b"SN-DELL-556677", reg_res.data)
        self.assertIn(b"Warranty Coverage", reg_res.data)
        self.assertIn(b"Dell Alienware Manufacturer Warranty", reg_res.data)

    def test_products_list_view_and_isolation(self):
        """Test /products lists only the authenticated customer's own products."""
        # Create second user with a product
        other_user = User(
            name="Bob Stranger",
            email="bob.stranger@example.com",
            password="SecurePassword123!",
            role=ROLE_CUSTOMER
        )
        db.session.add(other_user)
        db.session.flush()

        other_prod = Product(
            user_id=other_user.id,
            product_name="Bob Private Drone",
            brand="DJI",
            model="Mini 4 Pro",
            serial_number="SN-DJI-SECRET-99",
            purchase_date=date.today(),
            purchase_price=759.00,
            retailer="B&H Photo",
            warranty_length=12
        )
        db.session.add(other_prod)
        db.session.commit()

        # Login as Sarah
        self.client.post("/auth/login", data={
            "email": "sarah@example.com",
            "password": "SecurePassword123!"
        })

        # Sarah views /products
        res = self.client.get("/products")
        self.assertEqual(res.status_code, 200)
        self.assertNotIn(b"Bob Private Drone", res.data)
        self.assertNotIn(b"SN-DJI-SECRET-99", res.data)

        # Sarah attempts to view Bob's product directly (IDOR check)
        idor_res = self.client.get(f"/products/{other_prod.id}", follow_redirects=True)
        self.assertIn(b"Access forbidden", idor_res.data)

    def test_profile_view_and_update(self):
        """Test viewing and updating profile details."""
        # Login
        self.client.post("/auth/login", data={
            "email": "sarah@example.com",
            "password": "SecurePassword123!"
        })

        # GET profile
        get_res = self.client.get("/auth/profile")
        self.assertEqual(get_res.status_code, 200)
        self.assertIn(b"My Profile Details", get_res.data)
        self.assertIn(b"sarah@example.com", get_res.data)

        # POST profile update
        update_res = self.client.post("/auth/profile", data={
            "name": "Sarah Jenkins-Smith",
            "phone": "+1 555-9988"
        }, follow_redirects=True)
        self.assertEqual(update_res.status_code, 200)
        self.assertIn(b"Profile updated successfully", update_res.data)
        self.assertIn(b"Sarah Jenkins-Smith", update_res.data)

    def test_logout_clears_session(self):
        """Test logout clears session and redirects to login."""
        self.client.post("/auth/login", data={
            "email": "sarah@example.com",
            "password": "SecurePassword123!"
        })

        # Logout
        logout_res = self.client.get("/auth/logout", follow_redirects=True)
        self.assertEqual(logout_res.status_code, 200)
        self.assertIn(b"Sign in to your account", logout_res.data)

        # Try accessing protected dashboard
        dash_res = self.client.get("/dashboard", follow_redirects=True)
        self.assertIn(b"Please log in to access this page", dash_res.data)

    def test_root_landing_page_unauthenticated(self):
        """Test GET / opens the AssureX website landing page with login and register actions."""
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"AssureX", res.data)
        self.assertIn(b"Claim Engine", res.data)
        self.assertIn(b"AI-Powered Document Ops", res.data)
        self.assertIn(b"/auth/login", res.data)
        self.assertIn(b"/auth/register", res.data)
        self.assertIn(b"Sign In to Portal", res.data)
        self.assertIn(b"Create Customer Account", res.data)

    def test_root_authenticated_redirects_to_customer_dashboard(self):
        """Test authenticated Customer opening / is redirected to /dashboard."""
        self.client.post("/auth/login", data={
            "email": "sarah@example.com",
            "password": "SecurePassword123!"
        })

        root_res = self.client.get("/", follow_redirects=False)
        self.assertEqual(root_res.status_code, 302)
        self.assertIn("/dashboard", root_res.headers.get("Location", ""))

    def test_root_authenticated_redirects_for_all_roles(self):
        """Test authenticated users of each role redirect to their respective dashboard from /."""
        # 1. Service Center Employee
        staff = User(name="Sam Tech", email="sam.tech@example.com", password="Password123!", role=ROLE_SERVICE_CENTER)
        # 2. Claim Reviewer
        reviewer = User(name="Rachel Rev", email="rachel.rev@example.com", password="Password123!", role=ROLE_REVIEWER)
        # 3. Admin
        admin = User(name="Adam Admin", email="adam.admin@example.com", password="Password123!", role=ROLE_ADMIN)
        db.session.add_all([staff, reviewer, admin])
        db.session.commit()

        role_expectations = [
            ("sam.tech@example.com", "/service-center/dashboard"),
            ("rachel.rev@example.com", "/reviewer/dashboard"),
            ("adam.admin@example.com", "/admin/dashboard"),
        ]

        for email, expected_dashboard in role_expectations:
            # Login
            self.client.post("/auth/login", data={"email": email, "password": "Password123!"})
            # Hit root route /
            res = self.client.get("/", follow_redirects=False)
            self.assertEqual(res.status_code, 302)
            self.assertIn(expected_dashboard, res.headers.get("Location", ""))
            # Logout
            self.client.get("/auth/logout")

    def test_health_check_json_endpoint(self):
        """Test /health remains a machine-readable JSON health endpoint."""
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIsNotNone(data)
        self.assertEqual(data.get("status"), "healthy")
        self.assertEqual(data.get("database"), "connected")
        self.assertEqual(data.get("service"), "AssureX Claim Engine")


if __name__ == "__main__":
    unittest.main()

