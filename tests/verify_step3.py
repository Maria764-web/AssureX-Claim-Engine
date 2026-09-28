"""
AssureX Step 3 Manual & Browser End-to-End Verification Script
Runs through every scenario outlined in the user instructions:
1. Customer Registration & Login
2. Product listing & UI verification
3. Product registration with valid data
4. Public Product ID format, database persistence, and linkage verification
5. Product detail view & Warranty verification
6. Invalid inputs (empty fields, future date, negative price, invalid serial, duplicate serial)
7. Security & IDOR checks (Customer A vs Customer B)
8. Unauthorized tampering and ownership protection
"""

import os
import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from datetime import date, timedelta
from backend.app import create_app
from backend.extensions import db
from backend.models import User, Product, Warranty, AuditLog
from backend.utils.security import ROLE_CUSTOMER


def run_verification():
    app = create_app("testing")
    client = app.test_client()

    results = []

    def record(name, passed, message=""):
        status = "PASSED" if passed else "FAILED"
        print(f"[{status}] {name} - {message}")
        results.append({"name": name, "passed": passed, "message": message})

    with app.app_context():
        db.create_all()

        # =====================================================================
        # 1. Customer Registration & Login
        # =====================================================================
        reg_resp = client.post("/auth/register", json={
            "name": "Sarah Connor",
            "email": "sarah@cyberdyne.com",
            "phone": "+1 555-0199",
            "password": "SecurePassword123!",
            "confirm_password": "SecurePassword123!"
        })
        record("1. Customer Registration", reg_resp.status_code == 201, f"Status: {reg_resp.status_code}")

        login_resp = client.post("/auth/login", json={
            "email": "sarah@cyberdyne.com",
            "password": "SecurePassword123!"
        })
        record("2. Customer Login", login_resp.status_code == 200, f"Status: {login_resp.status_code}")

        # =====================================================================
        # 2. Open Customer Products Page (Empty State Check)
        # =====================================================================
        list_html = client.get("/products")
        record("3. View Products Page (Empty State)", list_html.status_code == 200 and b"No Products Registered Yet" in list_html.data, "Rendered successfully")

        # =====================================================================
        # 3. Product Registration with Valid Data
        # =====================================================================
        valid_payload = {
            "product_name": "Smart QLED 4K TV 75-Inch",
            "brand": "Samsung",
            "model": "QN75Q80C",
            "serial_number": "SN-SAM-75Q-998811",
            "purchase_date": (date.today() - timedelta(days=45)).isoformat(),
            "purchase_price": 1999.99,
            "retailer": "BestBuy Electronics",
            "warranty_length": 24
        }
        create_resp = client.post("/api/products", json=valid_payload)
        create_data = create_resp.get_json() if create_resp.status_code == 201 else {}
        prod_data = create_data.get("product", {})
        war_data = create_data.get("warranty", {})

        is_uid_valid = prod_data.get("product_uid", "").startswith("PRD-")
        record("4. Product Registration (Valid)", create_resp.status_code == 201 and is_uid_valid, f"Generated UID: {prod_data.get('product_uid')}")

        # =====================================================================
        # 4. Verify Linkage & Warranty Calculation
        # =====================================================================
        db_user = User.query.filter_by(email="sarah@cyberdyne.com").first()
        db_prod = Product.query.filter_by(product_uid=prod_data.get("product_uid")).first()
        is_linked = db_prod and db_prod.user_id == db_user.id
        record("5. Product Linkage to Customer", is_linked, f"Owner User ID: {db_prod.user_id if db_prod else 'N/A'}")

        is_war_valid = (
            war_data.get("warranty_status") == "Active"
            and war_data.get("warranty_provider") == "Samsung Manufacturer Warranty"
            and war_data.get("warranty_uid", "").startswith("WAR-")
        )
        record("6. Automatic Initial Warranty", is_war_valid, f"Warranty UID: {war_data.get('warranty_uid')}, Status: {war_data.get('warranty_status')}")

        # =====================================================================
        # 5. Product Listing & Detail HTML Page View
        # =====================================================================
        list_html_after = client.get("/products")
        record("7. Products Page (Populated List)", b"Smart QLED 4K TV 75-Inch" in list_html_after.data and b"SN-SAM-75Q-998811" in list_html_after.data, "Card displayed on page")

        detail_html = client.get(f"/products/{db_prod.id}")
        record("8. Product Detail Page View", detail_html.status_code == 200 and b"Device Specifications" in detail_html.data and b"Warranty Status" in detail_html.data, "Detail page rendered")

        # =====================================================================
        # 6. Invalid Input Tests
        # =====================================================================
        # Missing fields
        bad_resp1 = client.post("/api/products", json={})
        record("9. Validation: Empty Payload", bad_resp1.status_code == 400, "Rejected with 400")

        # Future date
        future_date = (date.today() + timedelta(days=15)).isoformat()
        bad_resp2 = client.post("/api/products", json={**valid_payload, "serial_number": "SN-NEW-1", "purchase_date": future_date})
        record("10. Validation: Future Purchase Date", bad_resp2.status_code == 400, "Rejected with 400")

        # Negative price
        bad_resp3 = client.post("/api/products", json={**valid_payload, "serial_number": "SN-NEW-2", "purchase_price": -100})
        record("11. Validation: Negative Price", bad_resp3.status_code == 400, "Rejected with 400")

        # Invalid serial characters
        bad_resp4 = client.post("/api/products", json={**valid_payload, "serial_number": "SN ??? @@@ ///"})
        record("12. Validation: Invalid Serial Number", bad_resp4.status_code == 400, "Rejected with 400")

        # Duplicate serial number
        bad_resp5 = client.post("/api/products", json=valid_payload)
        record("13. Validation: Duplicate Serial Number", bad_resp5.status_code == 400, "Rejected with 400")

        # Invalid warranty length (> 120 months)
        bad_resp6 = client.post("/api/products", json={**valid_payload, "serial_number": "SN-NEW-3", "warranty_length": 500})
        record("14. Validation: Excessive Warranty Length", bad_resp6.status_code == 400, "Rejected with 400")

        # =====================================================================
        # 7. Security & IDOR Protection (Customer A vs Customer B)
        # =====================================================================
        # Logout Sarah first
        client.get("/auth/logout")

        # Register and Login as Customer B (John)
        client.post("/auth/register", json={
            "name": "John Connor",
            "email": "john@resistance.com",
            "password": "SecurePassword123!",
            "confirm_password": "SecurePassword123!"
        })
        client.post("/auth/login", json={
            "email": "john@resistance.com",
            "password": "SecurePassword123!"
        })

        # John tries to view Sarah's product by numeric ID
        idor_id_resp = client.get(f"/api/products/{db_prod.id}")
        record("15. IDOR: Cross-User Numeric ID Rejection", idor_id_resp.status_code == 403, "Rejected with 403 Forbidden")

        # John tries to view Sarah's product by public UID
        idor_uid_resp = client.get(f"/api/products/by-uid/{db_prod.product_uid}")
        record("16. IDOR: Cross-User Public UID Rejection", idor_uid_resp.status_code == 403, "Rejected with 403 Forbidden")

        # John checks his product list (must NOT see Sarah's TV)
        john_list = client.get("/api/products")
        john_prods = john_list.get_json().get("products", [])
        record("17. Security: Customer Product Isolation", len(john_prods) == 0, "Sarah's product is invisible to John")

        # John attempts owner spoofing
        spoof_resp = client.post("/api/products", json={
            "user_id": db_user.id,  # Attempting to assign to Sarah
            "product_name": "John Laptop",
            "brand": "Dell",
            "model": "XPS 13",
            "serial_number": "SN-DELL-JOHN-1",
            "purchase_date": date.today().isoformat(),
            "purchase_price": 1200.00,
            "retailer": "Dell Direct",
            "warranty_length": 12
        })
        john_created = spoof_resp.get_json().get("product", {})
        record("18. Security: Owner Spoofing Prevented", spoof_resp.status_code == 201 and john_created.get("user_id") != db_user.id, f"Product assigned to logged-in user {john_created.get('user_id')}")

        # =====================================================================
        # 8. Audit Log Verification
        # =====================================================================
        logs = AuditLog.query.filter_by(action="PRODUCT_REGISTERED").all()
        record("19. Audit Logging of Product Registrations", len(logs) >= 2, f"Total product audit logs: {len(logs)}")

    all_passed = all(r["passed"] for r in results)
    print("\n" + "=" * 60)
    print(f"VERIFICATION SUMMARY: {sum(1 for r in results if r['passed'])}/{len(results)} Checks Passed.")
    print("=" * 60)
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(run_verification())
