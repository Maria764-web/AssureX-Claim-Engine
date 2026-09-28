"""
Verification of live customer dashboard and claims workflow on the actual database.
"""

import sys
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from backend.app import app, db
from backend.models import User, Product, Claim

def test_live_dashboard():
    with app.app_context():
        client = app.test_client()
        customer = User.query.filter_by(role='Customer').first()
        print(f"Testing with live customer: {customer.name} ({customer.email})")

        # Simulate authenticated session
        with client.session_transaction() as sess:
            sess['_user_id'] = str(customer.id)
            sess['_fresh'] = True

        # 1. Test Customer Dashboard
        res = client.get('/dashboard')
        print(f"Customer Dashboard Response: HTTP {res.status_code}")
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
        html = res.data.decode('utf-8')
        assert "Warranty Claims" in html
        assert "no such column" not in html.lower()
        print("  [PASS] Dashboard rendered successfully without any operational error!")

        # 2. Test Claim Creation View
        res_create = client.get('/claims/create')
        print(f"Claim Creation View Response: HTTP {res_create.status_code}")
        assert res_create.status_code == 200
        html_create = res_create.data.decode('utf-8')
        assert "File a Warranty Claim" in html_create
        assert "no such column" not in html_create.lower()
        print("  [PASS] Claim creation page rendered successfully!")

        # 3. Test Claims API
        res_api = client.get('/api/claims')
        print(f"Claims API Response: HTTP {res_api.status_code}")
        assert res_api.status_code == 200
        data = res_api.get_json()
        assert data["success"] is True
        print(f"  [PASS] Claims API returned successfully (count: {data['count']})")

        print("\nALL LIVE DASHBOARD AND CLAIM ROUTE CHECKS PASSED ON ACTUAL DB!")

if __name__ == '__main__':
    test_live_dashboard()
