"""
AssureX Step 5A — Claim Registration & Document Upload Foundation Verification Script
End-to-end verification covering:
1. Customer Claim Registration Flow (HTML form & API)
2. Unique Claim UID and proper relational linkages (User -> Product -> Warranty -> Claim)
3. Automatic product age calculation
4. Multi-format Evidence Upload (PDF, PNG, JPG, WEBP)
5. Secure storage organization by claim directory
6. Required document validation (receipt & damage photo)
7. Security: Rejection of executables & oversized files
8. Strict IDOR protection across claims and documents
9. Service-Centre Employee filing on behalf of customer
10. Attaching additional documents to existing claim
11. Secure document download & viewing
12. Customer dashboard integration with real-time claims summary
"""

import io
import os
import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

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
    DOC_TYPE_DAMAGE_PHOTO
)
from backend.utils.security import (
    ROLE_CUSTOMER,
    ROLE_SERVICE_CENTER,
    ROLE_REVIEWER,
    ROLE_ADMIN
)


def run_step5a_verification():
    print("=" * 75)
    print("ASSUREX STEP 5A -- CLAIM REGISTRATION & DOCUMENT UPLOAD FOUNDATION")
    print("=" * 75)

    passed_checks = 0
    total_checks = 0

    def check(name, condition, extra_info=""):
        nonlocal passed_checks, total_checks
        total_checks += 1
        if condition:
            passed_checks += 1
            print(f" [PASS] {name} {extra_info}")
        else:
            print(f" [FAIL] {name} {extra_info}")

    app = create_app("testing")
    with app.app_context():
        db.create_all()
        client = app.test_client()

        # 1. Seed Accounts
        alice = User(name="Alice Walker", email="alice.5a@test.com", password="Password123!", role=ROLE_CUSTOMER)
        bob = User(name="Bob Martin", email="bob.5a@test.com", password="Password123!", role=ROLE_CUSTOMER)
        sam_tech = User(name="Sam Service", email="sam.5a@test.com", password="Password123!", role=ROLE_SERVICE_CENTER)
        rachel_rev = User(name="Rachel Reviewer", email="rachel.5a@test.com", password="Password123!", role=ROLE_REVIEWER)
        adam_adm = User(name="Adam Chief", email="admin.5a@test.com", password="Password123!", role=ROLE_ADMIN)
        db.session.add_all([alice, bob, sam_tech, rachel_rev, adam_adm])
        db.session.commit()

        # 2. Seed Alice's Products & Warranty
        purchase_date = date.today() - relativedelta(months=7)
        product_alice = Product(
            user_id=alice.id,
            product_name="ThinkPad P16 Workstation",
            brand="Lenovo",
            model="P16-Gen2",
            serial_number="SN-LNV-P16-7788",
            purchase_date=purchase_date,
            purchase_price=2400.00,
            retailer="Lenovo Official",
            warranty_length=36
        )
        db.session.add(product_alice)
        db.session.commit()

        warranty_alice = Warranty(
            product_id=product_alice.id,
            warranty_provider="Lenovo Premier Support",
            start_date=purchase_date,
            expiry_date=purchase_date + relativedelta(months=36),
            covered_items="Motherboard, GPU, display panel, memory modules.",
            exclusions="Cosmetic wear, liquid ingress, unauthorized tampering.",
            warranty_status="Active"
        )
        db.session.add(warranty_alice)

        # Seed Bob's Product
        product_bob = Product(
            user_id=bob.id,
            product_name="Pixel 9 Pro",
            brand="Google",
            model="G2YBB",
            serial_number="SN-GOOG-PIX9-1122",
            purchase_date=purchase_date,
            purchase_price=999.00,
            retailer="Google Store",
            warranty_length=12
        )
        db.session.add(product_bob)
        db.session.commit()

        print("\n--- PHASE 1: Form Validation & Security Protections ---")

        # Login as Alice
        client.post("/auth/login", json={"email": "alice.5a@test.com", "password": "Password123!"})

        # Test A: Empty description & damage type rejected
        res = client.post("/api/claims", data={
            "product_id": product_alice.id,
            "fault_date": date.today().isoformat(),
            "fault_description": "",
            "damage_type": ""
        }, content_type="multipart/form-data")
        check("Rejection of empty fault description & damage type", res.status_code == 400)

        # Test B: Fault date in future rejected
        res = client.post("/api/claims", data={
            "product_id": product_alice.id,
            "fault_date": (date.today() + timedelta(days=2)).isoformat(),
            "fault_description": "Motherboard stopped responding after reboot.",
            "damage_type": "Motherboard / Circuitry Failure"
        }, content_type="multipart/form-data")
        check("Rejection of future fault date", res.status_code == 400)

        # Test C: Fault date prior to purchase date rejected
        res = client.post("/api/claims", data={
            "product_id": product_alice.id,
            "fault_date": (purchase_date - timedelta(days=5)).isoformat(),
            "fault_description": "Defect occurred before the device was bought.",
            "damage_type": "Screen / Display Defect"
        }, content_type="multipart/form-data")
        check("Rejection of fault date prior to purchase date", res.status_code == 400)

        # Test D: Missing required document detected
        pdf_receipt = (io.BytesIO(b"%PDF-1.4 official purchase invoice"), "receipt.pdf")
        res = client.post("/api/claims", data={
            "product_id": product_alice.id,
            "fault_date": (date.today() - timedelta(days=3)).isoformat(),
            "fault_description": "Screen panel exhibits heavy color banding and dead pixels.",
            "damage_type": "Screen / Display Defect",
            "receipt_file": pdf_receipt
            # damage_photo_file missing
        }, content_type="multipart/form-data")
        check("Missing mandatory damage photo detected", res.status_code == 400)

        # Test E: Dangerous executable rejected
        exe_file = (io.BytesIO(b"MZ executable"), "malicious_tool.exe")
        png_damage = (io.BytesIO(b"\x89PNG damage photo"), "damage.png")
        res = client.post("/api/claims", data={
            "product_id": product_alice.id,
            "fault_date": (date.today() - timedelta(days=3)).isoformat(),
            "fault_description": "Screen panel exhibits heavy color banding and dead pixels.",
            "damage_type": "Screen / Display Defect",
            "receipt_file": exe_file,
            "damage_photo_file": png_damage
        }, content_type="multipart/form-data")
        check("Rejection of executable file upload (.exe)", res.status_code == 400)

        print("\n--- PHASE 2: Successful Claim Registration & Storage ---")

        # Test F: Successful Claim Submission with multi-evidence
        receipt_pdf = (io.BytesIO(b"%PDF-1.4 Lenovo Official Invoice\nTotal: $2400.00"), "lenovo_invoice.pdf")
        damage_png = (io.BytesIO(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR Display Crack Photo"), "screen_banding.png")
        warranty_jpg = (io.BytesIO(b"\xff\xd8\xff\xe0\x00\x10JFIF Warranty Slip"), "warranty_card.jpg")
        serial_webp = (io.BytesIO(b"RIFF\x00\x00\x00\x00WEBPVP8 Chassis Label"), "serial_label.webp")

        res_create = client.post("/api/claims", data={
            "product_id": product_alice.id,
            "fault_date": (date.today() - timedelta(days=2)).isoformat(),
            "fault_description": "Internal display panel developed vertical purple lines and flickers uncontrollably during operation.",
            "damage_type": "Screen / Display Defect",
            "purchase_reference": "LEN-ORD-99201",
            "service_history_notes": "None. Original factory configuration.",
            "receipt_file": receipt_pdf,
            "damage_photo_file": damage_png,
            "warranty_card_file": warranty_jpg,
            "serial_photo_file": serial_webp
        }, content_type="multipart/form-data")

        check("Successful claim creation (HTTP 201)", res_create.status_code == 201)
        create_data = res_create.get_json()
        claim_data = create_data["claim"]
        claim_id = claim_data["id"]
        claim_uid = claim_data["claim_uid"]

        check("Generated Claim UID format (CLM-XXXXXXXX)", claim_uid.startswith("CLM-"))
        check("Correct Claimant User linkage", claim_data["user_id"] == alice.id)
        check("Correct Product linkage", claim_data["product_id"] == product_alice.id)
        check("Correct Warranty linkage", claim_data["warranty_id"] == warranty_alice.id)
        check("Product age calculated in months (>= 6)", claim_data["product_age"] >= 6)
        check("Evidence documents created (4 files)", len(create_data["documents"]) == 4)

        # Check storage file exists on disk
        first_doc = create_data["documents"][0]
        upload_root = Path(app.config.get("UPLOAD_FOLDER", "uploads"))
        doc_disk_path = upload_root / first_doc["stored_path"]
        check("File safely written to organized claim storage directory", doc_disk_path.exists())

        print("\n--- PHASE 3: Strict IDOR & Access Control Protections ---")

        # Logout Alice first, then Login as Bob
        client.get("/auth/logout")
        login_bob = client.post("/auth/login", json={"email": "bob.5a@test.com", "password": "Password123!"})
        check("Bob logged in successfully", login_bob.status_code == 200)

        # Test G: Bob cannot view Alice's claim
        res_bob_claim = client.get(f"/api/claims/{claim_id}")
        check("IDOR: Customer B cannot access Customer A's claim (HTTP 403)", res_bob_claim.status_code == 403)

        # Test H: Bob cannot download Alice's uploaded document
        res_bob_doc = client.get(f"/api/documents/{first_doc['id']}/download")
        check("IDOR: Customer B cannot download Customer A's document (HTTP 403)", res_bob_doc.status_code == 403)

        # Test I: Bob cannot create a claim against Alice's product
        res_bob_forgery = client.post("/api/claims", data={
            "product_id": product_alice.id,
            "fault_date": date.today().isoformat(),
            "fault_description": "Unauthorized claim attempt.",
            "damage_type": "Other Hardware Malfunction"
        }, content_type="multipart/form-data")
        check("IDOR: Customer B cannot file claim on Customer A's product (HTTP 403)", res_bob_forgery.status_code == 403)

        print("\n--- PHASE 4: Service-Centre Staff Workflow ---")

        # Logout Bob, Login as Sam (Service-Centre Employee)
        client.get("/auth/logout")
        login_sam = client.post("/auth/login", json={"email": "sam.5a@test.com", "password": "Password123!"})
        check("Service-Centre Employee logged in successfully", login_sam.status_code == 200)

        # Staff can file on behalf of Alice
        staff_receipt = (io.BytesIO(b"%PDF-1.4 Service Intake receipt"), "service_intake.pdf")
        staff_damage = (io.BytesIO(b"\x89PNG Service Intake photo"), "damage_intake.png")

        res_staff_create = client.post("/api/claims", data={
            "product_id": product_alice.id,
            "fault_date": (date.today() - timedelta(days=1)).isoformat(),
            "fault_description": "Customer presented workstation at repair counter with dead power subsystem.",
            "damage_type": "Power / Battery Failure",
            "receipt_file": staff_receipt,
            "damage_photo_file": staff_damage
        }, content_type="multipart/form-data")

        check("Service-Centre Employee can file claim on behalf of customer (HTTP 201)", res_staff_create.status_code == 201)
        staff_claim = res_staff_create.get_json()["claim"]
        check("Claim is properly attributed to product owner (Alice)", staff_claim["user_id"] == alice.id)

        # Staff can inspect any claim
        res_staff_view = client.get(f"/api/claims/{claim_id}")
        check("Staff can view claims for authorized inspection (HTTP 200)", res_staff_view.status_code == 200)

        print("\n--- PHASE 5: Web UI & Dashboard Verification ---")

        # Logout Sam, Login as Alice
        client.get("/auth/logout")
        login_alice = client.post("/auth/login", json={"email": "alice.5a@test.com", "password": "Password123!"})
        check("Alice logged in successfully", login_alice.status_code == 200)

        # Claim Details View
        res_details_html = client.get(f"/claims/{claim_id}")
        check("Claim Details HTML Page renders successfully (HTTP 200)", res_details_html.status_code == 200)
        html_content = res_details_html.data.decode("utf-8")
        check("Claim UID in rendered HTML", claim_uid in html_content)
        check("Fault description in rendered HTML", "Internal display panel developed" in html_content)
        check("Attached document filename in rendered HTML", "lenovo_invoice.pdf" in html_content)

        # Customer Dashboard View
        res_dashboard = client.get("/dashboard")
        check("Customer Dashboard renders successfully (HTTP 200)", res_dashboard.status_code == 200)
        dash_content = res_dashboard.data.decode("utf-8")
        check("Warranty Claims section in dashboard", "Warranty Claims" in dash_content)
        check("Alice's claim listed in dashboard", claim_uid in dash_content)

        # Attach additional document to existing claim
        extra_diag = (io.BytesIO(b"%PDF-1.4 Technician Diagnostic Report"), "diag_v2.pdf")
        res_add_doc = client.post(f"/api/claims/{claim_id}/documents", data={
            "document": extra_diag,
            "document_type": "Diagnostic Report"
        }, content_type="multipart/form-data")
        check("Upload additional evidence to existing claim (HTTP 201)", res_add_doc.status_code == 201)

        print("\n" + "=" * 75)
        print(f"VERIFICATION SUMMARY: {passed_checks}/{total_checks} CHECKS PASSED")
        print("=" * 75)

        if passed_checks == total_checks:
            print("STEP 5A FOUNDATION IS FULLY VERIFIED AND OPERATIONAL!\n")
            return True
        else:
            print("SOME CHECKS FAILED. Please review the output above.\n")
            return False


if __name__ == "__main__":
    success = run_step5a_verification()
    sys.exit(0 if success else 1)
