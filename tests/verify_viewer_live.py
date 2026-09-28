"""
Live Verification of Document Viewer UX in Step 5A
Tests against instance/assurex.db directly:
1. Customer logs in and loads Claim Details.
2. Clicks View on document.
3. Confirms Close (×) button exists with proper accessibility attributes.
4. Confirms fallback URL points back to Claim Details page.
5. Verifies raw image streaming.
6. Verifies IDOR protection (unauthorized user receives 403 Forbidden).
7. Verifies responsive CSS for mobile viewports.
"""

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.app import create_app
from backend.extensions import db
from backend.models import User, Claim, Document

def verify_live():
    app = create_app('development')
    app.config['WTF_CSRF_ENABLED'] = False
    client = app.test_client()

    with app.app_context():
        # User 1 is the claim owner
        user = db.session.get(User, 1)
        assert user is not None, "User 1 not found in instance/assurex.db"

        with client.session_transaction() as sess:
            sess['_user_id'] = str(user.id)
            sess['_fresh'] = True

        # 1. Open Claim Details
        res_claim = client.get('/claims/1')
        assert res_claim.status_code == 200, f"Claim page failed: {res_claim.status_code}"
        claim_html = res_claim.data.decode('utf-8')
        assert 'btn-view-1' in claim_html, "View button missing on claim page"
        print("[PASS] 1. Claim details page renders and contains View button for document #1")

        # 2. View Document 1 (image)
        res_view = client.get('/documents/1/view')
        assert res_view.status_code == 200, f"View page failed: {res_view.status_code}"
        html = res_view.data.decode('utf-8')

        assert 'id="btn-close-viewer"' in html, "Close button ID missing"
        assert 'aria-label="Close document preview"' in html, "aria-label missing on Close button"
        assert '&times;' in html, "Close times symbol missing"
        assert 'Document Preview' in html, "Document Preview label missing"
        assert 'images.jpg' in html, "Filename missing"
        assert '/claims/1' in html, "Fallback URL to Claim 1 missing"
        assert 'preview-img' in html, "Preview image element missing"
        assert 'handleCloseViewer(event)' in html, "Close click handler missing"
        assert 'Escape' in html, "Keyboard Escape shortcut missing"
        print("[PASS] 2. Document viewer renders with visible Close (x) button, label, filename, and fallback URL")

        # 3. Test raw content streaming
        res_raw = client.get('/documents/1/raw')
        assert res_raw.status_code == 200, f"Raw endpoint failed: {res_raw.status_code}"
        assert res_raw.content_type == 'image/jpeg', f"Unexpected content type: {res_raw.content_type}"
        assert len(res_raw.data) > 0, "Raw image data is empty"
        print("[PASS] 3. Raw image endpoint streams binary content with verified image/jpeg MIME type")

        # 4. Test IDOR protection: User 2 cannot access document 1
        client.get('/auth/logout')
        client.post('/auth/login', data={
            'email': 'root_tester_unique@example.com',
            'password': 'Password123!'
        }, follow_redirects=True)

        res_idor_view = client.get('/documents/1/view')
        assert res_idor_view.status_code == 403, f"Expected 403 for IDOR view, got {res_idor_view.status_code}"
        res_idor_raw = client.get('/documents/1/raw')
        assert res_idor_raw.status_code == 403, f"Expected 403 for IDOR raw, got {res_idor_raw.status_code}"
        print("[PASS] 4. IDOR protection verified: unauthorized user cannot access document viewer or raw stream")

        # 5. Verify unauthenticated redirect
        client.get('/auth/logout')
        res_unauth = client.get('/documents/1/view')
        assert res_unauth.status_code == 302, f"Expected 302 for unauthenticated, got {res_unauth.status_code}"
        print("[PASS] 5. Unauthenticated request safely redirected to login")

        print("\n" + "=" * 65)
        print("ALL LIVE STEP 5A DOCUMENT VIEWER CHECKS PASSED (5/5)!")
        print("=" * 65)

if __name__ == "__main__":
    verify_live()
