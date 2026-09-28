"""
AssureX Step 5A — Safe Database Schema Migration Script
Safely applies missing Step 5A columns to existing SQLite database:
- claims: purchase_reference, service_history_notes
- documents: user_id (and index ix_documents_user_id)
Preserves 100% of existing data without deleting, recreating, or dropping any tables.
"""

import os
import sys
import sqlite3
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))


def find_db_paths():
    """Locate all relevant AssureX SQLite database files in the workspace."""
    paths = []
    
    # 1. Check Flask app config
    try:
        from backend.app import create_app
        app = create_app()
        db_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
        if db_uri.startswith("sqlite:///"):
            clean_path = db_uri.replace("sqlite:///", "")
            # Flask-SQLAlchemy resolves relative SQLite URIs against instance_path
            p1 = Path(clean_path)
            if not p1.is_absolute():
                instance_p = Path(app.instance_path) / clean_path
                if instance_p.exists():
                    paths.append(instance_p)
                root_p = BASE_DIR / clean_path
                if root_p.exists():
                    paths.append(root_p)
            else:
                if p1.exists():
                    paths.append(p1)
    except Exception as e:
        print(f"[Warning] Could not inspect Flask app config: {e}")

    # 2. Standard location: instance/assurex.db
    instance_db = BASE_DIR / "instance" / "assurex.db"
    if instance_db.exists() and instance_db not in paths:
        paths.append(instance_db)

    # 3. Root location: assurex.db
    root_db = BASE_DIR / "assurex.db"
    if root_db.exists() and root_db not in paths:
        paths.append(root_db)

    return paths


def get_table_columns(conn: sqlite3.Connection, table_name: str) -> dict:
    """Return dictionary of column_name -> info from PRAGMA table_info."""
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table_name});")
    rows = cur.fetchall()
    # row format: (cid, name, type, notnull, dflt_value, pk)
    return {r[1]: {"type": r[2], "notnull": r[3], "dflt": r[4], "pk": r[5]} for r in rows}


def get_table_indexes(conn: sqlite3.Connection, table_name: str) -> set:
    """Return set of index names for a table."""
    cur = conn.cursor()
    cur.execute(f"PRAGMA index_list({table_name});")
    return {r[1] for r in cur.fetchall()}


def migrate_database(db_path: Path) -> dict:
    """
    Safely apply missing Step 5A columns to an existing SQLite database.
    Idempotent: checks for column presence before attempting ALTER TABLE.
    """
    print(f"\nTarget Database: {db_path.resolve()}")
    if not db_path.exists():
        print(f"Error: Database file not found at {db_path}")
        return {"success": False, "error": "File not found"}

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    # Enable foreign keys
    cur.execute("PRAGMA foreign_keys = ON;")

    # Record initial counts to verify data preservation
    counts_before = {}
    for table in ["users", "products", "warranties", "claims", "documents", "audit_logs"]:
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table};")
            counts_before[table] = cur.fetchone()[0]
        except Exception:
            counts_before[table] = 0

    print("Existing Record Counts Before Migration:")
    for tbl, cnt in counts_before.items():
        print(f"  - {tbl}: {cnt} records")

    changes_applied = []

    # -------------------------------------------------------------------------
    # 1. CLAIMS TABLE MIGRATION
    # -------------------------------------------------------------------------
    claim_cols = get_table_columns(conn, "claims")
    if not claim_cols:
        print("[!] Table 'claims' does not exist yet; will be created on initial startup.")
    else:
        print(f"\nCurrent 'claims' columns ({len(claim_cols)}): {list(claim_cols.keys())}")

        # Check and add 'purchase_reference'
        if "purchase_reference" not in claim_cols:
            print("  -> Adding missing column: claims.purchase_reference (VARCHAR(150))")
            cur.execute("ALTER TABLE claims ADD COLUMN purchase_reference VARCHAR(150) DEFAULT NULL;")
            changes_applied.append("claims.purchase_reference")
        else:
            print("  [OK] Column claims.purchase_reference already present.")

        # Check and add 'service_history_notes'
        if "service_history_notes" not in claim_cols:
            print("  -> Adding missing column: claims.service_history_notes (TEXT)")
            cur.execute("ALTER TABLE claims ADD COLUMN service_history_notes TEXT DEFAULT NULL;")
            changes_applied.append("claims.service_history_notes")
        else:
            print("  [OK] Column claims.service_history_notes already present.")

        # Verify other required Step 5A columns exist
        required_claim_columns = [
            "claim_uid", "user_id", "product_id", "warranty_id",
            "fault_date", "fault_description", "damage_type",
            "product_age", "submission_date", "claim_status",
            "final_decision", "created_at", "updated_at"
        ]
        for col in required_claim_columns:
            if col not in claim_cols:
                print(f"  -> Adding missing core column: claims.{col}")
                if col in ("created_at", "updated_at", "submission_date"):
                    cur.execute(f"ALTER TABLE claims ADD COLUMN {col} DATETIME;")
                elif col in ("product_age", "warranty_id"):
                    cur.execute(f"ALTER TABLE claims ADD COLUMN {col} INTEGER DEFAULT NULL;")
                else:
                    cur.execute(f"ALTER TABLE claims ADD COLUMN {col} TEXT DEFAULT NULL;")
                changes_applied.append(f"claims.{col}")

    # -------------------------------------------------------------------------
    # 2. DOCUMENTS TABLE MIGRATION
    # -------------------------------------------------------------------------
    doc_cols = get_table_columns(conn, "documents")
    if not doc_cols:
        print("[!] Table 'documents' does not exist yet; will be created on initial startup.")
    else:
        print(f"\nCurrent 'documents' columns ({len(doc_cols)}): {list(doc_cols.keys())}")

        # Check and add 'user_id'
        if "user_id" not in doc_cols:
            print("  -> Adding missing column: documents.user_id (INTEGER REFERENCES users(id))")
            cur.execute("ALTER TABLE documents ADD COLUMN user_id INTEGER DEFAULT NULL REFERENCES users(id) ON DELETE SET NULL;")
            changes_applied.append("documents.user_id")
        else:
            print("  [OK] Column documents.user_id already present.")

        # Ensure index on documents.user_id exists
        doc_indexes = get_table_indexes(conn, "documents")
        if "ix_documents_user_id" not in doc_indexes:
            print("  -> Creating index: ix_documents_user_id")
            cur.execute("CREATE INDEX IF NOT EXISTS ix_documents_user_id ON documents (user_id);")
            changes_applied.append("index:ix_documents_user_id")

        # Verify other core document columns
        required_doc_columns = [
            "document_uid", "claim_id", "product_id", "document_type",
            "original_filename", "stored_filename", "stored_path",
            "file_extension", "mime_type", "file_size", "file_hash",
            "upload_timestamp", "ocr_status", "verification_status"
        ]
        for col in required_doc_columns:
            if col not in doc_cols:
                print(f"  -> Adding missing column: documents.{col}")
                if col in ("file_size", "claim_id", "product_id"):
                    cur.execute(f"ALTER TABLE documents ADD COLUMN {col} INTEGER DEFAULT NULL;")
                elif col == "upload_timestamp":
                    cur.execute(f"ALTER TABLE documents ADD COLUMN {col} DATETIME;")
                else:
                    cur.execute(f"ALTER TABLE documents ADD COLUMN {col} VARCHAR(255) DEFAULT NULL;")
                changes_applied.append(f"documents.{col}")

    # Commit all changes safely
    conn.commit()

    # -------------------------------------------------------------------------
    # 3. VERIFY SCHEMA AND RECORD PRESERVATION
    # -------------------------------------------------------------------------
    counts_after = {}
    for table in ["users", "products", "warranties", "claims", "documents", "audit_logs"]:
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table};")
            counts_after[table] = cur.fetchone()[0]
        except Exception:
            counts_after[table] = 0

    print("\nRecord Counts After Migration (Data Integrity Verification):")
    preserved = True
    for tbl, cnt in counts_after.items():
        before = counts_before.get(tbl, 0)
        match = (cnt == before)
        if not match:
            preserved = False
        status_str = "[PRESERVED]" if match else "[CHANGED]"
        print(f"  {status_str} {tbl}: {cnt} records (was {before})")

    # Final columns inspection
    final_claim_cols = get_table_columns(conn, "claims")
    final_doc_cols = get_table_columns(conn, "documents")

    conn.close()

    print(f"\nFinal 'claims' columns ({len(final_claim_cols)}):")
    print(f"  {list(final_claim_cols.keys())}")
    print(f"\nFinal 'documents' columns ({len(final_doc_cols)}):")
    print(f"  {list(final_doc_cols.keys())}")

    return {
        "success": True,
        "db_path": str(db_path),
        "changes_applied": changes_applied,
        "data_preserved": preserved,
        "claims_columns": list(final_claim_cols.keys()),
        "documents_columns": list(final_doc_cols.keys()),
        "counts": counts_after
    }


def run_all_migrations():
    """Run migration across all discovered databases."""
    db_paths = find_db_paths()
    if not db_paths:
        print("[!] No SQLite database files found.")
        return False

    print("=" * 70)
    print("ASSUREX STEP 5A DATABASE SCHEMA MIGRATION")
    print("=" * 70)
    print(f"Found {len(db_paths)} database location(s): {[str(p) for p in db_paths]}")

    all_ok = True
    for p in db_paths:
        res = migrate_database(p)
        if not res.get("success"):
            all_ok = False

    print("\n" + "=" * 70)
    if all_ok:
        print("ALL STEP 5A SCHEMA MIGRATIONS APPLIED SUCCESSFULLY.")
    else:
        print("MIGRATION ENCOUNTERED ISSUES.")
    print("=" * 70)
    return all_ok


if __name__ == "__main__":
    success = run_all_migrations()
    sys.exit(0 if success else 1)
