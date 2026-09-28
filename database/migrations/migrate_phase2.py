"""
Phase 2 Database Migration
Adds decision_reasoning and reviewer_notes columns to claims table.
Safe to run multiple times (checks before adding columns).
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from backend.app import create_app
from backend.extensions import db
from sqlalchemy import inspect, text


def migrate_phase2():
    app = create_app('development')
    with app.app_context():
        inspector = inspect(db.engine)
        columns = [col["name"] for col in inspector.get_columns("claims")]

        added = []

        if "decision_reasoning" not in columns:
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE claims ADD COLUMN decision_reasoning TEXT"))
                conn.commit()
            added.append("decision_reasoning")
            print("[OK] Added column: claims.decision_reasoning")
        else:
            print("[SKIP] claims.decision_reasoning already exists.")

        if "reviewer_notes" not in columns:
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE claims ADD COLUMN reviewer_notes TEXT"))
                conn.commit()
            added.append("reviewer_notes")
            print("[OK] Added column: claims.reviewer_notes")
        else:
            print("[SKIP] claims.reviewer_notes already exists.")

        if added:
            print(f"\nMigration complete. Added: {', '.join(added)}")
        else:
            print("\nNothing to migrate — all columns already exist.")


if __name__ == '__main__':
    migrate_phase2()
