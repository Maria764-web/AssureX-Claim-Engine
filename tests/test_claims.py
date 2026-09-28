"""
AssureX Step 5A — Claim Registration & Document Upload Foundation Test Suite
Tests:
1. Customer can create a claim.
2. Claim receives a unique Claim ID.
3. Claim correctly links to User.
4. Claim correctly links to Product.
5. Claim correctly links to Warranty.
6. Required claim fields are validated.
7. Valid PDF upload works.
8. Valid image upload works (PNG, JPG, WEBP).
9. Invalid file type is rejected.
10. Oversized file is rejected.
11. Missing required document is detected.
12. Unauthorized user cannot access another user's claim (IDOR protection).
13. Unauthorized user cannot access another user's document (IDOR protection).
14. Duplicate Claim ID cannot be created (unique constraint).
15. Claim details display correctly.
16. Existing Step 1-4 functionality still works.
17. Service-Centre Employee can create a claim on behalf of customer.
18. Additional document upload to existing claim.
"""

import io
import unittest
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from backend.app import create_app
from backend.extensions import db
from backend.models import (
    User,
    Product,
    Warranty,
    Claim,
    Document,
    CLAIM_STATUS_DRAFT,
    CLAIM_STATUS_SUBMITTED,
    DOC_TYPE_RECEIPT,
    DOC_TYPE_INVOICE,
    DOC_TYPE_DAMAGE_PHOTO,
    DOC_TYPE_WARRANTY_CARD
)
from backend.services.claim_service import calculate_product_age_months
from backend.utils.security import (
    ROLE_CUSTOMER,
    ROLE_SERVICE_CENTER,
    ROLE_REVIEWER,
    ROLE_ADMIN
)


def create_dummy_file(filename: str, content: bytes = b"%PDF-1.4 dummy file content", mimetype: str = "application/pdf"):
    """Helper to create dummy in-memory files for upload testing."""
    return (io.BytesIO(content), filename, mimetype)


class Step5AClaimTestCase(unittest.TestCase):
    """Test suite for Step 5A Claim Registration & Document Upload Foundation."""

    def setUp(self):
        """Set up in-memory test database, seed users, products, and warranties."""
        self.app = create_app("testing")
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

        # Seed Users
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
        db.session.add_all([self.customer_a, self.customer_b, self.service_emp, self.reviewer, self.admin])
        db.session.commit()

        # Seed Product for Customer A (Purchased 6 months ago)
        self.purchase_date = date.today() - relativedelta(months=6)
        self.product_a = Product(
            user_id=self.customer_a.id,
            product_name="ProBook Laptop 15",
            brand="Dell",
            model="XPS-15-9530",
            serial_number="SN-DELL-9530-001",
            purchase_date=self.purchase_date,
            purchase_price=1500.00,
            retailer="Dell Direct",
            warranty_length=24
        )
        db.session.add(self.product_a)
        db.session.commit()

        # Seed Warranty for Product A
        self.warranty_a = Warranty(
            product_id=self.product_a.id,
            warranty_provider="Dell Premium Support",
            start_date=self.purchase_date,
            expiry_date=self.purchase_date + relativedelta(months=24),
            covered_items="Motherboard, screen, internal battery.",
            exclusions="Spills, accidental drops.",
            warranty_status="Active"
        )
        db.session.add(self.warranty_a)

        # Seed Product for Customer B
        self.product_b = Product(
            user_id=self.customer_b.id,
            product_name="Galaxy Phone S24",
            brand="Samsung",
            model="SM-S928B",
            serial_number="SN-SAMS-S24-999",
            purchase_date=self.purchase_date,
            purchase_price=999.00,
            retailer="Samsung Store",
            warranty_length=12
        )
        db.session.add(self.product_b)
        db.session.commit()

    def tearDown(self):
        """Clean up database and application context."""
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def login(self, email: str, password: str = "Password123!"):
        """Helper to log in as a specific user."""
        return self.client.post("/auth/login", json={
            "email": email,
            "password": password
        })

    # Test 1 & 2 & 3 & 4 & 5: Customer can create a claim, receives unique ID, correctly links User, Product, Warranty
    def test_customer_can_create_claim_with_proper_links(self):
        """Test 1-5: Successful claim registration properly links User, Product, and Warranty."""
        self.login(self.customer_a.email)

        receipt_file = (io.BytesIO(b"%PDF-1.4 invoice pdf data"), "invoice.pdf")
        damage_file = (io.BytesIO(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR dummy png data"), "screen_crack.png")

        res = self.client.post("/api/claims", data={
            "product_id": self.product_a.id,
            "fault_date": (date.today() - timedelta(days=2)).isoformat(),
            "fault_description": "Display screen flickers with horizontal lines and fails to power on.",
            "damage_type": "Screen / Display Defect",
            "purchase_reference": "INV-DELL-849204",
            "service_history_notes": "No prior repairs.",
            "receipt_file": receipt_file,
            "damage_photo_file": damage_file
        }, content_type="multipart/form-data")

        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertTrue(data["success"])
        claim_data = data["claim"]

        # 2. Unique Claim ID
        self.assertTrue(claim_data["claim_uid"].startswith("CLM-"))
        # 3. User link
        self.assertEqual(claim_data["user_id"], self.customer_a.id)
        # 4. Product link
        self.assertEqual(claim_data["product_id"], self.product_a.id)
        # 5. Warranty link
        self.assertEqual(claim_data["warranty_id"], self.warranty_a.id)
        # Product age calculation
        self.assertGreaterEqual(claim_data["product_age"], 5)
        # Documents count
        self.assertEqual(data["documents"][0]["document_type"], DOC_TYPE_RECEIPT)

    # Test 6: Required claim fields are validated
    def test_required_claim_fields_validation(self):
        """Test 6: Form validation fails with clear messages on missing required fields."""
        self.login(self.customer_a.email)

        # Missing fault description & damage type
        res = self.client.post("/api/claims", data={
            "product_id": self.product_a.id,
            "fault_date": date.today().isoformat(),
            "fault_description": "",  # Empty
            "damage_type": ""
        }, content_type="multipart/form-data")

        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertFalse(data["success"])
        self.assertTrue(any("Fault description is required" in e for e in data["errors"]))
        self.assertTrue(any("Damage/fault type is required" in e for e in data["errors"]))

    # Test 6b: Fault date in future is rejected
    def test_fault_date_cannot_be_in_future(self):
        """Test 6b: Fault date in the future is rejected."""
        self.login(self.customer_a.email)
        future_date = (date.today() + timedelta(days=5)).isoformat()

        res = self.client.post("/api/claims", data={
            "product_id": self.product_a.id,
            "fault_date": future_date,
            "fault_description": "Device spontaneously stopped turning on yesterday.",
            "damage_type": "Power / Battery Failure"
        }, content_type="multipart/form-data")

        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertTrue(any("Fault date cannot be in the future" in e for e in data["errors"]))

    # Test 6c: Fault date cannot precede product purchase date
    def test_fault_date_cannot_precede_purchase_date(self):
        """Test 6c: Fault date preceding purchase date is rejected."""
        self.login(self.customer_a.email)
        prior_date = (self.purchase_date - timedelta(days=10)).isoformat()

        res = self.client.post("/api/claims", data={
            "product_id": self.product_a.id,
            "fault_date": prior_date,
            "fault_description": "Device was broken before purchase date.",
            "damage_type": "Other Hardware Malfunction"
        }, content_type="multipart/form-data")

        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertTrue(any("cannot be prior to product purchase date" in e for e in data["errors"]))

    # Test 7 & 8: Valid PDF and Image upload works
    def test_valid_pdf_and_image_uploads(self):
        """Test 7 & 8: PDF, PNG, JPG, and WEBP evidence uploads succeed."""
        self.login(self.customer_a.email)

        pdf_receipt = (io.BytesIO(b"%PDF-1.4 Invoice Document Sample Content"), "receipt.pdf")
        png_damage = (io.BytesIO(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR PNG Content"), "defect.png")
        jpg_warranty = (io.BytesIO(b"\xff\xd8\xff\xe0\x00\x10JFIF JPEG Content"), "warranty_card.jpg")
        webp_serial = (io.BytesIO(b"RIFF\x00\x00\x00\x00WEBPVP8 WEBP Content"), "serial.webp")

        res = self.client.post("/api/claims", data={
            "product_id": self.product_a.id,
            "fault_date": (date.today() - timedelta(days=1)).isoformat(),
            "fault_description": "Laptop battery swollen and won't hold charge for more than 5 minutes.",
            "damage_type": "Power / Battery Failure",
            "receipt_file": pdf_receipt,
            "damage_photo_file": png_damage,
            "warranty_card_file": jpg_warranty,
            "serial_photo_file": webp_serial
        }, content_type="multipart/form-data")

        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertEqual(len(data["documents"]), 4)
        extensions = {d["file_extension"] for d in data["documents"]}
        self.assertEqual(extensions, {"pdf", "png", "jpg", "webp"})

    # Test 9: Invalid file type is rejected
    def test_invalid_file_type_rejected(self):
        """Test 9: Dangerous or unsupported executable extensions (.exe, .sh) are rejected."""
        self.login(self.customer_a.email)

        exe_file = (io.BytesIO(b"MZ\x90\x00 executable binary payload"), "malware.exe")
        png_damage = (io.BytesIO(b"\x89PNG\r\n\x1a\n valid png"), "damage.png")

        res = self.client.post("/api/claims", data={
            "product_id": self.product_a.id,
            "fault_date": date.today().isoformat(),
            "fault_description": "Device motherboard burned out and emitted electrical smoke.",
            "damage_type": "Motherboard / Circuitry Failure",
            "receipt_file": exe_file,
            "damage_photo_file": png_damage
        }, content_type="multipart/form-data")

        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertTrue(any("Executable and script files (.exe) are strictly forbidden" in e or "Invalid file format" in e for e in data["errors"]))

    # Test 10: Oversized file is rejected
    def test_oversized_file_rejected(self):
        """Test 10: Files exceeding 10 MB limit are rejected."""
        self.login(self.customer_a.email)

        # Create a mock file stream larger than 10 MB (10.5 MB)
        oversized_data = b"0" * (11 * 1024 * 1024)
        large_pdf = (io.BytesIO(oversized_data), "huge_receipt.pdf")
        png_damage = (io.BytesIO(b"\x89PNG\r\n valid png"), "damage.png")

        res = self.client.post("/api/claims", data={
            "product_id": self.product_a.id,
            "fault_date": date.today().isoformat(),
            "fault_description": "Audio output distorted and speaker crackles at all volumes.",
            "damage_type": "Speaker / Audio Malfunction",
            "receipt_file": large_pdf,
            "damage_photo_file": png_damage
        }, content_type="multipart/form-data")

        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertTrue(any("exceeds maximum allowed size" in e for e in data["errors"]))

    # Test 11: Missing required document is detected
    def test_missing_required_document_detected(self):
        """Test 11: Submitting claim without mandatory receipt or damage photo is rejected."""
        self.login(self.customer_a.email)

        # Provide only receipt but NO damage photo
        pdf_receipt = (io.BytesIO(b"%PDF-1.4 receipt"), "receipt.pdf")

        res = self.client.post("/api/claims", data={
            "product_id": self.product_a.id,
            "fault_date": date.today().isoformat(),
            "fault_description": "Keyboard spacebar is stuck and does not register keystrokes.",
            "damage_type": "Keyboard / Button Failure",
            "receipt_file": pdf_receipt
            # damage_photo_file omitted
        }, content_type="multipart/form-data")

        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertTrue(any("Damage or fault photo evidence is required" in e for e in data["errors"]))

    # Test 12: Unauthorized user cannot access another user's claim (IDOR protection)
    def test_unauthorized_user_cannot_access_other_claim(self):
        """Test 12: Customer B cannot view or modify Customer A's claim."""
        # Create claim under Customer A
        claim = Claim(
            user_id=self.customer_a.id,
            product_id=self.product_a.id,
            warranty_id=self.warranty_a.id,
            fault_date=date.today() - timedelta(days=3),
            fault_description="Liquid spilled on keyboard causing short circuit.",
            damage_type="Water / Liquid Ingress",
            claim_status=CLAIM_STATUS_SUBMITTED
        )
        db.session.add(claim)
        db.session.commit()

        # Login as Customer B
        self.login(self.customer_b.email)

        # Customer B tries to view Customer A's claim via API -> 403
        res = self.client.get(f"/api/claims/{claim.id}")
        self.assertEqual(res.status_code, 403)
        self.assertFalse(res.get_json()["success"])

        # Customer B tries to view Customer A's claim via UID -> 403
        res_uid = self.client.get(f"/api/claims/by-uid/{claim.claim_uid}")
        self.assertEqual(res_uid.status_code, 403)

        # Customer B tries to file a claim against Customer A's product -> 403
        res_forgery = self.client.post("/api/claims", data={
            "product_id": self.product_a.id,  # Product A belongs to Customer A
            "fault_date": date.today().isoformat(),
            "fault_description": "Malicious attempt to create claim on another customer's asset.",
            "damage_type": "Other Hardware Malfunction"
        }, content_type="multipart/form-data")
        self.assertEqual(res_forgery.status_code, 403)

    # Test 13: Unauthorized user cannot access another user's document (IDOR protection)
    def test_unauthorized_user_cannot_access_other_document(self):
        """Test 13: Customer B cannot access or download Customer A's uploaded evidence document."""
        claim = Claim(
            user_id=self.customer_a.id,
            product_id=self.product_a.id,
            warranty_id=self.warranty_a.id,
            fault_date=date.today() - timedelta(days=2),
            fault_description="Screen cracked.",
            damage_type="Physical Impact / Casing Damage"
        )
        db.session.add(claim)
        db.session.flush()

        doc = Document(
            claim_id=claim.id,
            product_id=self.product_a.id,
            user_id=self.customer_a.id,
            document_type=DOC_TYPE_RECEIPT,
            original_filename="confidential_receipt.pdf",
            stored_filename="DOC_secret_receipt.pdf",
            stored_path="claims/test/DOC_secret_receipt.pdf",
            file_extension="pdf",
            mime_type="application/pdf",
            file_size=1024,
            file_hash="abc123hash"
        )
        db.session.add(doc)
        db.session.commit()

        # Login as Customer B
        self.login(self.customer_b.email)

        # Metadata endpoint IDOR check
        res = self.client.get(f"/api/documents/{doc.id}")
        self.assertEqual(res.status_code, 403)

        # Download endpoint IDOR check
        res_dl = self.client.get(f"/api/documents/{doc.id}/download")
        self.assertEqual(res_dl.status_code, 403)

    # Test 14: Duplicate Claim ID cannot be created
    def test_duplicate_claim_id_cannot_be_created(self):
        """Test 14: Database enforces uniqueness of claim_uid."""
        claim_1 = Claim(
            claim_uid="CLM-DUPLICATE-TEST",
            user_id=self.customer_a.id,
            product_id=self.product_a.id,
            fault_date=date.today(),
            fault_description="First claim.",
            damage_type="Power / Battery Failure"
        )
        db.session.add(claim_1)
        db.session.commit()

        # Attempt to insert identical claim_uid
        claim_2 = Claim(
            claim_uid="CLM-DUPLICATE-TEST",
            user_id=self.customer_a.id,
            product_id=self.product_a.id,
            fault_date=date.today(),
            fault_description="Duplicate claim.",
            damage_type="Power / Battery Failure"
        )
        db.session.add(claim_2)
        with self.assertRaises(Exception):
            db.session.commit()
        db.session.rollback()

    # Test 15: Claim details display correctly
    def test_claim_details_display_correctly(self):
        """Test 15: Claim details page renders and JSON API returns expected fields."""
        claim = Claim(
            user_id=self.customer_a.id,
            product_id=self.product_a.id,
            warranty_id=self.warranty_a.id,
            fault_date=date.today() - timedelta(days=5),
            fault_description="Wi-Fi antenna fails to connect to any network.",
            damage_type="Connectivity / Network Failure",
            purchase_reference="ORDER-REF-9988",
            claim_status=CLAIM_STATUS_SUBMITTED
        )
        db.session.add(claim)
        db.session.commit()

        self.login(self.customer_a.email)

        # Test HTML View
        res_html = self.client.get(f"/claims/{claim.id}")
        self.assertEqual(res_html.status_code, 200)
        html_text = res_html.data.decode("utf-8")
        self.assertIn(claim.claim_uid, html_text)
        self.assertIn("Wi-Fi antenna fails", html_text)
        self.assertIn("Connectivity / Network Failure", html_text)

        # Test JSON API
        res_json = self.client.get(f"/api/claims/{claim.id}")
        self.assertEqual(res_json.status_code, 200)
        data = res_json.get_json()
        self.assertEqual(data["claim"]["claim_uid"], claim.claim_uid)
        self.assertEqual(data["product"]["serial_number"], self.product_a.serial_number)
        self.assertEqual(data["warranty"]["warranty_uid"], self.warranty_a.warranty_uid)

    # Test 16: Existing Step 1-4 functionality still works
    def test_existing_step_1_to_4_functionality_intact(self):
        """Test 16: Verify products listing, warranty listing, and customer dashboard continue to work."""
        self.login(self.customer_a.email)

        # Products API
        res_prod = self.client.get("/api/products")
        self.assertEqual(res_prod.status_code, 200)
        self.assertEqual(res_prod.get_json()["count"], 1)

        # Warranties API
        res_war = self.client.get("/api/warranties")
        self.assertEqual(res_war.status_code, 200)
        self.assertEqual(res_war.get_json()["count"], 1)

        # Customer Dashboard HTML
        res_dash = self.client.get("/dashboard")
        self.assertEqual(res_dash.status_code, 200)
        self.assertIn("Customer Portal", res_dash.data.decode("utf-8"))
        self.assertIn("Warranty Claims", res_dash.data.decode("utf-8"))

    # Test 17: Service-Centre Employee can create claim on behalf of customer
    def test_service_centre_employee_can_create_claim_on_behalf_of_customer(self):
        """Test 17: Service-Centre Employee can file a claim on behalf of Customer A."""
        self.login(self.service_emp.email)

        receipt = (io.BytesIO(b"%PDF-1.4 receipt"), "receipt.pdf")
        damage = (io.BytesIO(b"\x89PNG\r\n damage"), "damage.png")

        res = self.client.post("/api/claims", data={
            "product_id": self.product_a.id,  # Customer A's product
            "fault_date": (date.today() - timedelta(days=1)).isoformat(),
            "fault_description": "Customer dropped off device at service centre with failed charging port.",
            "damage_type": "Power / Battery Failure",
            "receipt_file": receipt,
            "damage_photo_file": damage
        }, content_type="multipart/form-data")

        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertTrue(data["success"])
        # The claimant is the product owner (Customer A)
        self.assertEqual(data["claim"]["user_id"], self.customer_a.id)

    # Test 18: Adding additional document to existing claim
    def test_attach_additional_document_to_claim(self):
        """Test 18: Customer can upload additional supporting documents to their existing claim."""
        claim = Claim(
            user_id=self.customer_a.id,
            product_id=self.product_a.id,
            fault_date=date.today(),
            fault_description="Initial claim with standard evidence.",
            damage_type="Screen / Display Defect"
        )
        db.session.add(claim)
        db.session.commit()

        self.login(self.customer_a.email)

        extra_file = (io.BytesIO(b"%PDF-1.4 diagnostic report"), "diagnostic_report.pdf")
        res = self.client.post(f"/api/claims/{claim.id}/documents", data={
            "document": extra_file,
            "document_type": "Diagnostic Report"
        }, content_type="multipart/form-data")

        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["document"]["document_type"], "Diagnostic Report")
        self.assertEqual(data["document"]["claim_id"], claim.id)


if __name__ == "__main__":
    unittest.main()
