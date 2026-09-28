"""
AssureX Document Viewer UX Tests (Step 5A)
Tests the dedicated document preview interface, Close (×) button accessibility,
safe return/fallback navigation, multi-format rendering (JPG, PNG, WEBP, PDF),
and IDOR security.
"""

import io
import unittest
from datetime import date
from pathlib import Path
from backend.app import create_app
from backend.extensions import db
from backend.models import (
    User,
    Product,
    Warranty,
    Claim,
    Document,
    CLAIM_STATUS_SUBMITTED,
    DOC_TYPE_RECEIPT,
    DOC_TYPE_DAMAGE_PHOTO
)
from backend.utils.security import ROLE_CUSTOMER


class DocumentViewerTestCase(unittest.TestCase):
    """Test suite for the Document & Image Viewer UX and Close button functionality."""

    def setUp(self):
        """Set up test environment and test fixtures."""
        self.app = create_app("testing")
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

        # Create two test customers
        self.customer_a = User(
            user_uid="USR-TEST-CUSTA",
            name="Alice Customer",
            email="alice@test.com",
            role=ROLE_CUSTOMER,
            is_active=True
        )
        self.customer_a.set_password("SecurePass123!")

        self.customer_b = User(
            user_uid="USR-TEST-CUSTB",
            name="Bob Customer",
            email="bob@test.com",
            role=ROLE_CUSTOMER,
            is_active=True
        )
        self.customer_b.set_password("SecurePass123!")

        db.session.add_all([self.customer_a, self.customer_b])
        db.session.commit()

        # Create product & warranty for Customer A
        self.product = Product(
            product_uid="PRD-VIEW-001",
            user_id=self.customer_a.id,
            product_name="UltraBook Pro 15",
            brand="AssureTech",
            model="UB-15X",
            serial_number="UB15-SN-998877",
            purchase_date=date(2025, 1, 10),
            purchase_price=1200.0,
            retailer="TechHub",
            warranty_length=12
        )
        db.session.add(self.product)
        db.session.commit()

        self.claim = Claim(
            claim_uid="CLM-VIEW-001",
            user_id=self.customer_a.id,
            product_id=self.product.id,
            fault_date=date(2026, 2, 1),
            fault_description="Display flickers then goes black under load.",
            damage_type="Screen / Display Damage",
            claim_status=CLAIM_STATUS_SUBMITTED
        )
        db.session.add(self.claim)
        db.session.commit()

        # Create test upload files in uploads directory
        self.upload_dir = Path(self.app.config.get("UPLOAD_FOLDER", "uploads")) / "claims" / self.claim.claim_uid
        self.upload_dir.mkdir(parents=True, exist_ok=True)

        # 1. JPEG document
        self.jpg_path = self.upload_dir / "evidence_photo.jpg"
        self.jpg_path.write_bytes(b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xFF\xDB")

        self.doc_jpg = Document(
            document_uid="DOC-JPG-001",
            user_id=self.customer_a.id,
            claim_id=self.claim.id,
            product_id=self.product.id,
            document_type=DOC_TYPE_DAMAGE_PHOTO,
            original_filename="screen_damage.jpg",
            stored_filename="evidence_photo.jpg",
            stored_path=f"claims/{self.claim.claim_uid}/evidence_photo.jpg",
            file_extension="jpg",
            mime_type="image/jpeg",
            file_size=len(self.jpg_path.read_bytes()),
            file_hash="fakejpghash123"
        )

        # 2. PNG document
        self.png_path = self.upload_dir / "invoice_receipt.png"
        self.png_path.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")

        self.doc_png = Document(
            document_uid="DOC-PNG-001",
            user_id=self.customer_a.id,
            claim_id=self.claim.id,
            product_id=self.product.id,
            document_type=DOC_TYPE_RECEIPT,
            original_filename="receipt_store.png",
            stored_filename="invoice_receipt.png",
            stored_path=f"claims/{self.claim.claim_uid}/invoice_receipt.png",
            file_extension="png",
            mime_type="image/png",
            file_size=len(self.png_path.read_bytes()),
            file_hash="fakepnghash123"
        )

        # 3. PDF document
        self.pdf_path = self.upload_dir / "tax_invoice.pdf"
        self.pdf_path.write_bytes(b"%PDF-1.4 dummy invoice content")

        self.doc_pdf = Document(
            document_uid="DOC-PDF-001",
            user_id=self.customer_a.id,
            claim_id=self.claim.id,
            product_id=self.product.id,
            document_type=DOC_TYPE_RECEIPT,
            original_filename="official_tax_invoice.pdf",
            stored_filename="tax_invoice.pdf",
            stored_path=f"claims/{self.claim.claim_uid}/tax_invoice.pdf",
            file_extension="pdf",
            mime_type="application/pdf",
            file_size=len(self.pdf_path.read_bytes()),
            file_hash="fakepdfhash123"
        )

        # 4. WEBP document
        self.webp_path = self.upload_dir / "component_snap.webp"
        self.webp_path.write_bytes(b"RIFF\x00\x00\x00\x00WEBPVP8 ")

        self.doc_webp = Document(
            document_uid="DOC-WEBP-001",
            user_id=self.customer_a.id,
            claim_id=self.claim.id,
            product_id=self.product.id,
            document_type=DOC_TYPE_DAMAGE_PHOTO,
            original_filename="component_snap.webp",
            stored_filename="component_snap.webp",
            stored_path=f"claims/{self.claim.claim_uid}/component_snap.webp",
            file_extension="webp",
            mime_type="image/webp",
            file_size=len(self.webp_path.read_bytes()),
            file_hash="fakewebphash123"
        )

        db.session.add_all([self.doc_jpg, self.doc_png, self.doc_pdf, self.doc_webp])
        db.session.commit()

    def tearDown(self):
        """Clean up test resources."""
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def login(self, email: str, password: str = "SecurePass123!"):
        """Helper to log in a test user."""
        self.client.get("/auth/logout")
        return self.client.post("/auth/login", data={
            "email": email,
            "password": password
        }, follow_redirects=True)

    def test_unauthenticated_viewer_redirects_to_login(self):
        """Unauthenticated user cannot access document viewer."""
        res = self.client.get(f"/documents/{self.doc_jpg.id}/view")
        self.assertEqual(res.status_code, 302)
        self.assertIn("/auth/login", res.headers.get("Location", ""))

    def test_image_viewer_renders_header_and_close_button(self):
        """Customer viewing JPG gets dedicated preview page with Close (×) button and fallback."""
        self.login(self.customer_a.email)

        res = self.client.get(f"/documents/{self.doc_jpg.id}/view")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")

        # 1. Close (×) button must be present with required attributes
        self.assertIn('id="btn-close-viewer"', html)
        self.assertIn('aria-label="Close document preview"', html)
        self.assertIn('&times;', html)
        self.assertIn('close-label', html)

        # 2. Document Preview header label & metadata
        self.assertIn('Document Preview', html)
        self.assertIn('screen_damage.jpg', html)
        self.assertIn(DOC_TYPE_DAMAGE_PHOTO, html)

        # 3. Safe fallback URL pointing to the relevant Claim Details page
        expected_fallback = f"/claims/{self.claim.id}"
        self.assertIn(expected_fallback, html)

        # 4. Image canvas rendered with raw source URL
        expected_raw_url = f"/documents/{self.doc_jpg.id}/raw"
        self.assertIn(expected_raw_url, html)
        self.assertIn('id="preview-img"', html)

        # 5. Download button available
        expected_dl_url = f"/documents/{self.doc_jpg.id}/download"
        self.assertIn(expected_dl_url, html)

    def test_pdf_viewer_renders_iframe_and_close_button(self):
        """Customer viewing PDF gets dedicated preview with iframe and Close (×) button."""
        self.login(self.customer_a.email)

        res = self.client.get(f"/documents/{self.doc_pdf.id}/view")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")

        # 1. Close button in header
        self.assertIn('id="btn-close-viewer"', html)
        self.assertIn('aria-label="Close document preview"', html)

        # 2. Document Preview label and filename
        self.assertIn('Document Preview', html)
        self.assertIn('official_tax_invoice.pdf', html)

        # 3. PDF iframe canvas rendered
        self.assertIn('class="pdf-frame"', html)
        expected_raw_url = f"/documents/{self.doc_pdf.id}/raw"
        self.assertIn(expected_raw_url, html)

    def test_webp_and_png_image_viewers(self):
        """Viewer correctly identifies and displays PNG and WEBP formats."""
        self.login(self.customer_a.email)

        # PNG
        res_png = self.client.get(f"/documents/{self.doc_png.id}/view")
        self.assertEqual(res_png.status_code, 200)
        self.assertIn("receipt_store.png", res_png.data.decode("utf-8"))
        self.assertIn('id="btn-close-viewer"', res_png.data.decode("utf-8"))

        # WEBP
        res_webp = self.client.get(f"/documents/{self.doc_webp.id}/view")
        self.assertEqual(res_webp.status_code, 200)
        self.assertIn("component_snap.webp", res_webp.data.decode("utf-8"))
        self.assertIn('id="btn-close-viewer"', res_webp.data.decode("utf-8"))

    def test_raw_content_endpoint_serves_bytes(self):
        """Raw content endpoint streams image bytes with correct MIME type."""
        self.login(self.customer_a.email)

        res = self.client.get(f"/documents/{self.doc_jpg.id}/raw")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.content_type, "image/jpeg")
        self.assertEqual(res.data, self.jpg_path.read_bytes())

    def test_idor_protection_on_view_and_raw(self):
        """Customer B cannot view or access Customer A's document (IDOR protection)."""
        # Login as Customer B
        self.login(self.customer_b.email)

        # HTML Viewer access forbidden
        res_view = self.client.get(f"/documents/{self.doc_jpg.id}/view")
        self.assertEqual(res_view.status_code, 403)

        # Raw binary content access forbidden
        res_raw = self.client.get(f"/documents/{self.doc_jpg.id}/raw")
        self.assertEqual(res_raw.status_code, 403)


if __name__ == "__main__":
    unittest.main()
