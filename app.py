"""
AssureX Claim Engine - Root Entrypoint
Allows running the application directly from the project root directory via `python app.py` or `python run.py`.
"""

import sys
from pathlib import Path

# Add root directory to python path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from backend.app import app, db

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        try:
            from database.migrate_step5a import run_all_migrations
            run_all_migrations()
        except Exception as e:
            print(f"[Warning] Auto-migration check: {e}")
        try:
            from database.migrations.migrate_step5b import migrate_step5b
            migrate_step5b()
        except Exception as e:
            print(f"[Warning] Step 5B migration check: {e}")
    print("=" * 65)
    print("  AssureX Claim Engine - Server Starting")
    print("  Access web portal at: http://127.0.0.1:5000")
    print("  Health check at:      http://127.0.0.1:5000/health")
    print("=" * 65)
    app.run(host="127.0.0.1", port=5000, debug=True)
