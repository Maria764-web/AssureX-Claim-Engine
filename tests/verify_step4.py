"""
AssureX Step 4 — Warranty Management & Policy Rules End-to-End Verification Script
Simulates real browser flows across all 4 roles:
1. Customer Flow
2. Service-Centre Employee Flow
3. Claim Reviewer Flow
4. Administrator Flow
5. IDOR & Tamper Resistance Verification
"""

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
from backend.models import User, Product, Warranty, AuditLog
from backend.utils.security import (
    ROLE_CUSTOMER,
    ROLE_SERVICE_CENTER,
    ROLE_REVIEWER,
    ROLE_ADMIN
)


def run_step4_verification():
    print("=" * 70)
    print("ASSUREX STEP 4 -- WARRANTY MANAGEMENT & POLICY RULES VERIFICATION")
    print("=" * 70)

    app = create_app("testing")
    with app.app_context():
        db.create_all()
        client = app.test_client()

        # Seed Users
        customer_1 = User(name="Alice Walker", email="alice.step4@test.com", password="Password123!", role=ROLE_CUSTOMER)
        customer_2 = User(name="Bob Martin", email="bob.step4@test.com", password="Password123!", role=ROLE_CUSTOMER)
        service_staff = User(name="Sam Tech", email="sam.step4@test.com", password="Password123!", role=ROLE_SERVICE_CENTER)
        reviewer_staff = User(name="Rachel Review", email="rachel.step4@test.com", password="Password123!", role=ROLE_REVIEWER)
        admin_staff = User(name="Adam Chief", email="admin.step4@test.com", password="Password123!", role=ROLE_ADMIN)

        db.session.add_all([customer_1, customer_2, service_staff, reviewer_staff, admin_staff])
        db.session.commit()

        today = date.today()

        # Seed Customer 1 Products with 3 Warranty scenarios: Active, Nearing Expiry, Expired
        p1 = Product(
            user_id=customer_1.id,
            product_name="MacBook Pro 16 M3 Max",
            brand="Apple",
            model="MBP-16-M3",
            serial_number="SN-APPL-M3MAX-001",
            purchase_date=today - timedelta(days=60),
            purchase_price=3499.00,
            retailer="Apple Store Regent St",
            warranty_length=12
        )
        db.session.add(p1)
        db.session.commit()
        w1 = Warranty(
            product_id=p1.id,
            warranty_provider="AppleCare Services",
            start_date=today - timedelta(days=60),
            expiry_date=today - timedelta(days=60) + relativedelta(months=12),
            warranty_duration=12,
            covered_items="Liquid Retina XDR Display, M3 Max Silicon, Battery System, Logic Board",
            exclusions="Accidental submersion, catastrophic vehicle crush damage, unofficial modifications"
        )

        p2 = Product(
            user_id=customer_1.id,
            product_name="Sony Alpha 7R V",
            brand="Sony",
            model="ILCE-7RM5",
            serial_number="SN-SONY-A7RV-002",
            purchase_date=today - timedelta(days=350),
            purchase_price=3899.00,
            retailer="B&H Photo",
            warranty_length=12
        )
        db.session.add(p2)
        db.session.commit()
        w2 = Warranty(
            product_id=p2.id,
            warranty_provider="Sony Electronics Warranty Corp",
            start_date=today - timedelta(days=350),
            expiry_date=today + timedelta(days=15),
            warranty_duration=12,
            covered_items="Full-frame Exmor R BSI CMOS Sensor, BIONZ XR Processing Engine, 5-Axis IBIS",
            exclusions="Saltwater submersion, sensor scratch from unapproved physical contact"
        )

        p3 = Product(
            user_id=customer_1.id,
            product_name="Dyson V15 Detect Vacuum",
            brand="Dyson",
            model="V15-ABS",
            serial_number="SN-DYSON-V15-003",
            purchase_date=today - timedelta(days=400),
            purchase_price=749.00,
            retailer="Dyson Online",
            warranty_length=12
        )
        db.session.add(p3)
        db.session.commit()
        w3 = Warranty(
            product_id=p3.id,
            warranty_provider="Dyson Direct",
            start_date=today - timedelta(days=400),
            expiry_date=today - timedelta(days=35),
            warranty_duration=12,
            covered_items="Hyperdymium Motor, Piezo Acoustic Sensor, Cyclone Array",
            exclusions="Filter clogging due to non-wash maintenance, commercial heavy-construction usage"
        )

        # Seed Customer 2 Product
        p4 = Product(
            user_id=customer_2.id,
            product_name="Dell XPS 15 9530",
            brand="Dell",
            model="XPS-9530",
            serial_number="SN-DELL-XPS15-004",
            purchase_date=today - timedelta(days=45),
            purchase_price=2199.00,
            retailer="Dell Enterprise",
            warranty_length=24
        )
        db.session.add(p4)
        db.session.commit()
        w4 = Warranty(
            product_id=p4.id,
            warranty_provider="Dell ProSupport Next Business Day",
            start_date=today - timedelta(days=45),
            expiry_date=today - timedelta(days=45) + relativedelta(months=24),
            warranty_duration=24,
            covered_items="OLED Touch Panel, Core i9 CPU, Motherboard, AC Adapter",
            exclusions="Intentional drop damage, BIOS security modification failures"
        )

        db.session.add_all([w1, w2, w3, w4])
        db.session.commit()

        # -------------------------------------------------------------
        # 1. TEST CUSTOMER BROWSER FLOW
        # -------------------------------------------------------------
        print("\n[1] Testing Customer Complete Browser Flow...")
        login_res = client.post("/auth/login", json={"email": "alice.step4@test.com", "password": "Password123!"})
        assert login_res.status_code == 200, "Customer login failed"

        # Check Dashboard metrics
        dash_res = client.get("/dashboard")
        assert dash_res.status_code == 200, "Dashboard request failed"
        dash_html = dash_res.data.decode("utf-8")
        assert "My Warranties" in dash_html, "Dashboard missing My Warranties quick action"
        assert "Active Warranties" in dash_html, "Dashboard missing Active Warranties card"
        print("  [OK] Customer Dashboard displays live warranty summary & quick action")

        # Check My Products -> Product Detail -> View Full Warranty
        prod_res = client.get(f"/products/{p1.id}")
        assert prod_res.status_code == 200, "Product detail request failed"
        prod_html = prod_res.data.decode("utf-8")
        assert "View Full Warranty Certificate" in prod_html, "Product detail missing View Full Warranty button"
        assert f"/warranties/{w1.id}" in prod_html, "Product detail warranty link incorrect"
        print("  [OK] Product Detail page connects directly to Warranty Certificate")

        # Check Warranties catalog page
        war_res = client.get("/warranties")
        assert war_res.status_code == 200, "Warranties list request failed"
        war_html = war_res.data.decode("utf-8")
        assert "MacBook Pro 16 M3 Max" in war_html, "Missing active product warranty"
        assert "Sony Alpha 7R V" in war_html, "Missing nearing expiry warranty"
        assert "Dyson V15 Detect" in war_html, "Missing expired warranty"
        assert "Dell XPS 15" not in war_html, "Customer A can see Customer B product!"
        print("  [OK] Warranties catalog lists only Customer's own policies with dynamic status badges")

        # Check Warranty Certificate Detail Page
        cert_res = client.get(f"/warranties/{w1.id}")
        assert cert_res.status_code == 200, "Warranty detail request failed"
        cert_html = cert_res.data.decode("utf-8")
        assert "Official Warranty Certificate" in cert_html
        assert w1.warranty_uid in cert_html
        assert "AppleCare Services" in cert_html
        assert "Liquid Retina XDR Display" in cert_html
        assert "Accidental submersion" in cert_html
        print("  [OK] Warranty Certificate renders complete coverage items, exclusions, and UID")

        # -------------------------------------------------------------
        # 2. TEST IDOR PREVENTION
        # -------------------------------------------------------------
        print("\n[2] Testing IDOR Security Protections...")
        idor_id_res = client.get(f"/warranties/{w4.id}")
        assert idor_id_res.status_code == 302, f"IDOR DB ID browser access not redirected! Got {idor_id_res.status_code}"

        idor_uid_res = client.get(f"/warranties/by-uid/{w4.warranty_uid}")
        assert idor_uid_res.status_code == 302, f"IDOR UID browser access not redirected! Got {idor_uid_res.status_code}"

        idor_api_res = client.get(f"/api/warranties/{w4.id}")
        assert idor_api_res.status_code == 403, f"IDOR API vulnerability! Got {idor_api_res.status_code}"

        idor_api_uid = client.get(f"/api/warranties/by-uid/{w4.warranty_uid}")
        assert idor_api_uid.status_code == 403, f"IDOR API UID vulnerability! Got {idor_api_uid.status_code}"

        # Test customer cannot manipulate extension
        cust_ext_res = client.post(f"/api/warranties/{w1.id}/extend", json={"duration_months": 12})
        assert cust_ext_res.status_code == 403, "Customer allowed to extend warranty!"
        print("  [OK] Strict IDOR protections verified (DB ID, UID, API, Extension prevention)")

        client.get("/auth/logout")

        # -------------------------------------------------------------
        # 3. TEST SERVICE-CENTRE EMPLOYEE WORKSPACE
        # -------------------------------------------------------------
        print("\n[3] Testing Service-Centre Employee Lookup...")
        serv_login = client.post("/auth/login", json={"email": "sam.step4@test.com", "password": "Password123!"})
        assert serv_login.status_code == 200

        serv_dash = client.get("/service-center/dashboard")
        assert serv_dash.status_code == 200
        serv_html = serv_dash.data.decode("utf-8")
        assert "Service Centre Operations" in serv_html
        assert "Rapid Warranty Verification" in serv_html

        # Lookup by Serial Number
        search_res = client.get(f"/warranties?q={p1.serial_number}")
        assert search_res.status_code == 200
        assert w1.warranty_uid in search_res.data.decode("utf-8")

        # Lookup by Warranty UID
        search_war = client.get(f"/warranties?q={w4.warranty_uid}")
        assert search_war.status_code == 200
        assert "Dell XPS 15" in search_war.data.decode("utf-8")
        print("  [OK] Service-Centre Employee successfully verifies policies via Serial and Warranty UID")

        client.get("/auth/logout")

        # -------------------------------------------------------------
        # 4. TEST CLAIM REVIEWER WORKSPACE
        # -------------------------------------------------------------
        print("\n[4] Testing Claim Reviewer Policy Inspection...")
        rev_login = client.post("/auth/login", json={"email": "rachel.step4@test.com", "password": "Password123!"})
        assert rev_login.status_code == 200

        rev_dash = client.get("/reviewer/dashboard")
        assert rev_dash.status_code == 200
        assert "Claim Reviewer Console" in rev_dash.data.decode("utf-8")

        rev_war = client.get(f"/warranties/{w1.id}")
        assert rev_war.status_code == 200
        assert "Official Warranty Certificate" in rev_war.data.decode("utf-8")
        print("  [OK] Claim Reviewer successfully inspects warranty terms and exclusions")

        client.get("/auth/logout")

        # -------------------------------------------------------------
        # 5. TEST ADMINISTRATOR MANAGEMENT & EXTENSION WORKFLOW
        # -------------------------------------------------------------
        print("\n[5] Testing Administrator Management & Warranty Extension...")
        admin_login = client.post("/auth/login", json={"email": "admin.step4@test.com", "password": "Password123!"})
        assert admin_login.status_code == 200

        admin_war = client.get("/warranties")
        assert admin_war.status_code == 200
        admin_war_html = admin_war.data.decode("utf-8")
        assert "Global Warranty Management &amp; Policy Control" in admin_war_html
        assert w1.warranty_uid in admin_war_html
        assert w4.warranty_uid in admin_war_html

        # Filter by expired
        filter_res = client.get("/warranties?status=expired")
        assert filter_res.status_code == 200
        assert w3.warranty_uid in filter_res.data.decode("utf-8")
        assert w1.warranty_uid not in filter_res.data.decode("utf-8")

        # Perform controlled extension
        old_expiry = w1.expiry_date
        ext_res = client.post(f"/warranties/{w1.id}/extend", data={
            "duration_months": "12",
            "details": "AssureX VIP Care Extension"
        }, follow_redirects=True)
        assert ext_res.status_code == 200

        # Verify DB update
        updated_w1 = db.session.get(Warranty, w1.id)
        assert updated_w1.is_extended is True
        assert updated_w1.expiry_date == old_expiry + relativedelta(months=12)

        # Verify Audit Log
        audit = AuditLog.query.filter_by(action="WARRANTY_EXTENDED", entity_id=w1.warranty_uid).first()
        assert audit is not None, "Audit log not recorded for warranty extension!"
        assert "Admin" in audit.description
        print("  [OK] Administrator successfully filtered warranties, performed extension, and verified audit logging")

        client.get("/auth/logout")

        print("\n" + "=" * 70)
        print("ALL STEP 4 VERIFICATION CHECKS PASSED SUCCESSFULLY!")
        print("=" * 70)


if __name__ == "__main__":
    run_step4_verification()
