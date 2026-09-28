"""
AssureX Authentication & Authorization Test Suite (Step 2)
Tests User Registration, Login, Logout, Session Security,
Role-Based Access Control (RBAC), IDOR Ownership Protection, and Role Tampering Prevention.
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
    AuditLog
)
from backend.utils.security import (
    ROLE_CUSTOMER,
    ROLE_SERVICE_CENTER,
    ROLE_REVIEWER,
    ROLE_ADMIN
)


class AuthenticationTestCase(unittest.TestCase):
    """Test suite for authentication, registration, login/logout, and security controls."""

    def setUp(self):
        """Create fresh test app context and in-memory database."""
        self.app = create_app("testing")
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

        # Seed sample users for the 4 roles
        self.customer = User(
            name="Alice Customer",
            email="alice@customer.com",
            password="Password123!",
            role=ROLE_CUSTOMER
        )
        self.customer_b = User(
            name="Bob Customer",
            email="bob@customer.com",
            password="Password123!",
            role=ROLE_CUSTOMER
        )
        self.service_staff = User(
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
            email="adam@admin.com",
            password="Password123!",
            role=ROLE_ADMIN
        )
        db.session.add_all([
            self.customer,
            self.customer_b,
            self.service_staff,
            self.reviewer,
            self.admin
        ])
        db.session.commit()

    def tearDown(self):
        """Clean up database session and drop all tables."""
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    # =========================================================================
    # 1. REGISTRATION & ROLE SECURITY TESTS
    # =========================================================================

    def test_customer_public_registration_succeeds(self):
        """Test public customer registration succeeds and assigns Customer role."""
        payload = {
            "name": "New Customer",
            "email": "new.customer@example.com",
            "phone": "+1 555-1234",
            "password": "StrongPassword123!",
            "confirm_password": "StrongPassword123!",
            "role": ROLE_CUSTOMER
        }
        response = self.client.post("/auth/register", json=payload)
        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data["user"]["role"], ROLE_CUSTOMER)
        self.assertTrue(data["user"]["user_uid"].startswith("USR-"))

        # Verify in database
        user = User.query.filter_by(email="new.customer@example.com").first()
        self.assertIsNotNone(user)
        self.assertEqual(user.role, ROLE_CUSTOMER)
        self.assertTrue(user.check_password("StrongPassword123!"))

    def test_public_user_cannot_create_service_center_account(self):
        """Test public unauthenticated user cannot register as Service-Centre Employee (returns 403)."""
        payload = {
            "name": "Public Fake Technician",
            "email": "fake.tech@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
            "role": ROLE_SERVICE_CENTER
        }
        response = self.client.post("/auth/register", json=payload)
        self.assertEqual(response.status_code, 403)
        data = response.get_json()
        self.assertFalse(data.get("success"))
        self.assertIn("authorized Administrator", data.get("message", ""))
        self.assertIsNone(User.query.filter_by(email="fake.tech@example.com").first())

    def test_public_user_cannot_create_reviewer_account(self):
        """Test public unauthenticated user cannot register as Claim Reviewer (returns 403)."""
        payload = {
            "name": "Public Fake Reviewer",
            "email": "fake.reviewer@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
            "role": ROLE_REVIEWER
        }
        response = self.client.post("/auth/register", json=payload)
        self.assertEqual(response.status_code, 403)
        data = response.get_json()
        self.assertFalse(data.get("success"))
        self.assertIn("authorized Administrator", data.get("message", ""))
        self.assertIsNone(User.query.filter_by(email="fake.reviewer@example.com").first())

    def test_public_user_cannot_create_admin_account(self):
        """Test public unauthenticated user cannot register as Administrator (returns 403)."""
        payload = {
            "name": "Public Fake Admin",
            "email": "fake.admin@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
            "role": ROLE_ADMIN
        }
        response = self.client.post("/auth/register", json=payload)
        self.assertEqual(response.status_code, 403)
        data = response.get_json()
        self.assertFalse(data.get("success"))
        self.assertIn("authorized Administrator", data.get("message", ""))
        self.assertIsNone(User.query.filter_by(email="fake.admin@example.com").first())

    def test_admin_can_create_service_center_employee(self):
        """Test authenticated Administrator can create a Service-Centre Employee account."""
        # Login as Admin
        self.client.post("/auth/login", json={"email": "adam@admin.com", "password": "Password123!"})

        payload = {
            "name": "Authorized Tech Sam",
            "email": "sam.authorized@service.com",
            "password": "TechPassword123!",
            "confirm_password": "TechPassword123!",
            "role": ROLE_SERVICE_CENTER
        }
        response = self.client.post("/auth/register", json=payload)
        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data["user"]["role"], ROLE_SERVICE_CENTER)

        user = User.query.filter_by(email="sam.authorized@service.com").first()
        self.assertIsNotNone(user)
        self.assertEqual(user.role, ROLE_SERVICE_CENTER)

    def test_admin_can_create_claim_reviewer(self):
        """Test authenticated Administrator can create a Claim Reviewer account."""
        self.client.post("/auth/login", json={"email": "adam@admin.com", "password": "Password123!"})

        payload = {
            "name": "Authorized Reviewer Rita",
            "email": "rita.reviewer@staff.com",
            "password": "RitaPassword123!",
            "confirm_password": "RitaPassword123!",
            "role": ROLE_REVIEWER
        }
        response = self.client.post("/auth/register", json=payload)
        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data["user"]["role"], ROLE_REVIEWER)

        user = User.query.filter_by(email="rita.reviewer@staff.com").first()
        self.assertIsNotNone(user)
        self.assertEqual(user.role, ROLE_REVIEWER)

    def test_admin_can_create_administrator(self):
        """Test authenticated Administrator can create another Administrator account."""
        self.client.post("/auth/login", json={"email": "adam@admin.com", "password": "Password123!"})

        payload = {
            "name": "Secondary Admin Alex",
            "email": "alex.admin@domain.com",
            "password": "AlexPassword123!",
            "confirm_password": "AlexPassword123!",
            "role": ROLE_ADMIN
        }
        response = self.client.post("/auth/register", json=payload)
        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data["user"]["role"], ROLE_ADMIN)

        user = User.query.filter_by(email="alex.admin@domain.com").first()
        self.assertIsNotNone(user)
        self.assertEqual(user.role, ROLE_ADMIN)

    def test_dashboard_redirect_for_each_role(self):
        """Test login returns correct dashboard URL redirect for each of the 4 roles."""
        role_logins = [
            ("alice@customer.com", "/dashboard"),
            ("sam@service.com", "/service-center/dashboard"),
            ("rachel@reviewer.com", "/reviewer/dashboard"),
            ("adam@admin.com", "/admin/dashboard"),
        ]

        for email, expected_url in role_logins:
            res = self.client.post("/auth/login", json={"email": email, "password": "Password123!"})
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertIn(expected_url, data.get("redirect_url", ""))
            self.client.get("/auth/logout")

    def test_duplicate_email_registration_rejected(self):
        """Test registering with an existing email is rejected."""
        payload = {
            "name": "Alice Duplicate",
            "email": "alice@customer.com",
            "password": "Password123!",
            "confirm_password": "Password123!"
        }
        response = self.client.post("/auth/register", json=payload)
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertFalse(data.get("success"))
        self.assertTrue(any("already exists" in err for err in data.get("errors", [])))

    def test_invalid_email_format_rejected(self):
        """Test registration with invalid email format is rejected."""
        payload = {
            "name": "Invalid Email",
            "email": "not-an-email",
            "password": "Password123!",
            "confirm_password": "Password123!"
        }
        response = self.client.post("/auth/register", json=payload)
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertFalse(data.get("success"))

    def test_password_mismatch_rejected(self):
        """Test registration with mismatched passwords is rejected."""
        payload = {
            "name": "Mismatch Test",
            "email": "mismatch@example.com",
            "password": "Password123!",
            "confirm_password": "DifferentPassword123!"
        }
        response = self.client.post("/auth/register", json=payload)
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertTrue(any("do not match" in err for err in data.get("errors", [])))

    def test_weak_password_rejected(self):
        """Test registration with weak password (under 8 chars or all letters) is rejected."""
        payload = {
            "name": "Weak Pass",
            "email": "weak@example.com",
            "password": "short",
            "confirm_password": "short"
        }
        response = self.client.post("/auth/register", json=payload)
        self.assertEqual(response.status_code, 400)

    # =========================================================================
    # 2. LOGIN TESTS
    # =========================================================================

    def test_valid_login_success(self):
        """Test valid login returns 200, user info, and role dashboard URL."""
        payload = {
            "email": "alice@customer.com",
            "password": "Password123!"
        }
        response = self.client.post("/auth/login", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data["user"]["email"], "alice@customer.com")
        self.assertIn("/dashboard", data.get("redirect_url", ""))

    def test_invalid_password_rejected_with_generic_message(self):
        """Test invalid password returns generic error message without leaking details."""
        payload = {
            "email": "alice@customer.com",
            "password": "WrongPassword!"
        }
        response = self.client.post("/auth/login", json=payload)
        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertFalse(data.get("success"))
        self.assertEqual(data.get("message"), "Invalid email or password.")

    def test_unknown_email_rejected_with_generic_message(self):
        """Test unknown email returns identical generic error message."""
        payload = {
            "email": "nonexistent@example.com",
            "password": "Password123!"
        }
        response = self.client.post("/auth/login", json=payload)
        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertEqual(data.get("message"), "Invalid email or password.")

    # =========================================================================
    # 3. LOGOUT TESTS
    # =========================================================================

    def test_logout_clears_session_and_protects_routes(self):
        """Test logout clears session and subsequent protected requests are rejected."""
        # Login
        self.client.post("/auth/login", json={
            "email": "alice@customer.com",
            "password": "Password123!"
        })

        # Access protected route (should succeed)
        res_me = self.client.get("/auth/me")
        self.assertEqual(res_me.status_code, 200)

        # Logout
        res_logout = self.client.get("/auth/logout")
        self.assertIn(res_logout.status_code, (200, 302))

        # Access protected API route again (must fail with 401)
        res_after_api = self.client.get("/auth/me")
        self.assertEqual(res_after_api.status_code, 401)

        # Access protected web dashboard again (must redirect to login or return 401)
        res_after_web = self.client.get("/dashboard")
        self.assertIn(res_after_web.status_code, (302, 401))

    # =========================================================================
    # 4. ROLE-BASED ACCESS CONTROL (RBAC) TESTS
    # =========================================================================

    def test_customer_access_permissions(self):
        """Customer can access customer area, but is rejected from Admin and Reviewer portals."""
        # Login as Customer
        self.client.post("/auth/login", json={"email": "alice@customer.com", "password": "Password123!"})

        # Can access customer dashboard
        res_dash = self.client.get("/dashboard")
        self.assertEqual(res_dash.status_code, 200)

        # Cannot access Admin dashboard
        res_admin = self.client.get("/admin/dashboard")
        self.assertEqual(res_admin.status_code, 403)

        # Cannot access Reviewer dashboard
        res_reviewer = self.client.get("/reviewer/dashboard")
        self.assertEqual(res_reviewer.status_code, 403)

        # Cannot access Service Centre dashboard
        res_service = self.client.get("/service-center/dashboard")
        self.assertEqual(res_service.status_code, 403)

        # Cannot access Predictions API
        res_pred = self.client.get("/api/predictions/status")
        self.assertEqual(res_pred.status_code, 403)

    def test_service_center_access_permissions(self):
        """Service-Centre Employee can access service portal, but cannot access Admin portal."""
        self.client.post("/auth/login", json={"email": "sam@service.com", "password": "Password123!"})

        # Can access service-center dashboard
        res_service = self.client.get("/service-center/dashboard")
        self.assertEqual(res_service.status_code, 200)

        # Cannot access Admin dashboard
        res_admin = self.client.get("/admin/dashboard")
        self.assertEqual(res_admin.status_code, 403)

        # Cannot access Admin user management
        res_users = self.client.get("/admin/users")
        self.assertEqual(res_users.status_code, 403)

    def test_reviewer_access_permissions(self):
        """Claim Reviewer can access reviewer portal and prediction API, but cannot access Admin area."""
        self.client.post("/auth/login", json={"email": "rachel@reviewer.com", "password": "Password123!"})

        # Can access reviewer dashboard
        res_rev = self.client.get("/reviewer/dashboard")
        self.assertEqual(res_rev.status_code, 200)

        # Can access predictions API
        res_pred = self.client.get("/api/predictions/status")
        self.assertEqual(res_pred.status_code, 200)

        # Cannot access Admin dashboard
        res_admin = self.client.get("/admin/dashboard")
        self.assertEqual(res_admin.status_code, 403)

    def test_admin_access_permissions(self):
        """Administrator can access admin dashboard and manage system users."""
        self.client.post("/auth/login", json={"email": "adam@admin.com", "password": "Password123!"})

        # Can access admin dashboard
        res_admin = self.client.get("/admin/dashboard")
        self.assertEqual(res_admin.status_code, 200)

        # Can list users
        res_users = self.client.get("/admin/users")
        self.assertEqual(res_users.status_code, 200)
        data = res_users.get_json()
        self.assertTrue(data.get("count") >= 5)

        # Admin can create privileged user (e.g. new Reviewer)
        res_create = self.client.post("/admin/users", json={
            "name": "New Reviewer Staff",
            "email": "new.reviewer@staff.com",
            "password": "StaffPassword123!",
            "role": ROLE_REVIEWER
        })
        self.assertEqual(res_create.status_code, 201)
        created_user = User.query.filter_by(email="new.reviewer@staff.com").first()
        self.assertIsNotNone(created_user)
        self.assertEqual(created_user.role, ROLE_REVIEWER)

    # =========================================================================
    # 5. IDOR / CROSS-CUSTOMER OWNERSHIP PROTECTION TESTS
    # =========================================================================

    def test_customer_cannot_access_other_customer_claim_or_product(self):
        """
        CRITICAL IDOR PROTECTION TEST:
        Customer A cannot view or fetch Customer B's Product, Warranty, Claim, or Document.
        """
        # Create Product, Warranty, Claim, and Document owned by Customer B
        prod_b = Product(
            user_id=self.customer_b.id,
            product_name="Bob Laptop",
            brand="Dell",
            model="XPS 15",
            serial_number="SN-DELL-BOB-1234",
            purchase_date=date.today() - timedelta(days=60),
            purchase_price=1800.0,
            retailer="Dell Direct",
            warranty_length=12
        )
        db.session.add(prod_b)
        db.session.commit()

        war_b = Warranty(
            product_id=prod_b.id,
            start_date=date.today() - timedelta(days=60),
            expiry_date=date.today() + timedelta(days=300),
            warranty_status="Active"
        )
        db.session.add(war_b)
        db.session.commit()

        claim_b = Claim(
            user_id=self.customer_b.id,
            product_id=prod_b.id,
            warranty_id=war_b.id,
            fault_date=date.today() - timedelta(days=5),
            fault_description="Battery swelling",
            damage_type="Battery Defect",
            claim_status="Submitted"
        )
        db.session.add(claim_b)
        db.session.commit()

        doc_b = Document(
            claim_id=claim_b.id,
            product_id=prod_b.id,
            document_type="Receipt",
            original_filename="bob_receipt.pdf",
            stored_filename="DOC-999_bob_receipt.pdf",
            stored_path="documents/DOC-999_bob_receipt.pdf",
            file_extension="pdf",
            file_size=12345,
            file_hash="mock_hash_12345"
        )
        db.session.add(doc_b)
        db.session.commit()

        # Login as Customer A (Alice)
        self.client.post("/auth/login", json={"email": "alice@customer.com", "password": "Password123!"})

        # Alice attempts to access Bob's Product -> 403 Forbidden
        res_prod = self.client.get(f"/api/products/{prod_b.id}")
        self.assertEqual(res_prod.status_code, 403)

        # Alice attempts to access Bob's Warranty -> 403 Forbidden
        res_war = self.client.get(f"/api/warranties/{war_b.id}")
        self.assertEqual(res_war.status_code, 403)

        # Alice attempts to access Bob's Claim -> 403 Forbidden
        res_claim = self.client.get(f"/api/claims/{claim_b.id}")
        self.assertEqual(res_claim.status_code, 403)

        # Alice attempts to access Bob's Document -> 403 Forbidden
        res_doc = self.client.get(f"/api/documents/{doc_b.id}")
        self.assertEqual(res_doc.status_code, 403)

    # =========================================================================
    # 6. ROLE TAMPERING PROTECTION
    # =========================================================================

    def test_customer_cannot_elevate_own_role_via_profile_update(self):
        """
        CRITICAL ROLE TAMPERING TEST:
        A logged-in customer updating their profile cannot change their role.
        """
        self.client.post("/auth/login", json={"email": "alice@customer.com", "password": "Password123!"})

        # Alice attempts to send role: "Administrator" in profile update
        response = self.client.put("/auth/profile", json={
            "name": "Alice Updated",
            "role": ROLE_ADMIN
        })
        self.assertEqual(response.status_code, 200)

        # Verify Alice's role in DB is STILL Customer
        user = User.query.filter_by(email="alice@customer.com").first()
        self.assertEqual(user.name, "Alice Updated")
        self.assertEqual(user.role, ROLE_CUSTOMER)
        self.assertNotEqual(user.role, ROLE_ADMIN)

    # =========================================================================
    # 7. AUDIT LOGGING OF AUTH EVENTS
    # =========================================================================

    def test_audit_logs_recorded_for_auth_events(self):
        """Test that logins, failed logins, and registrations generate audit logs."""
        # Failed login attempt
        self.client.post("/auth/login", json={"email": "alice@customer.com", "password": "BadPassword"})

        failed_logs = AuditLog.query.filter_by(action="AUTH_LOGIN_FAILED").all()
        self.assertTrue(len(failed_logs) >= 1)

        # Successful login
        self.client.post("/auth/login", json={"email": "alice@customer.com", "password": "Password123!"})
        success_logs = AuditLog.query.filter_by(action="AUTH_LOGIN_SUCCESS").all()
        self.assertTrue(len(success_logs) >= 1)


if __name__ == "__main__":
    unittest.main()
