"""
Step 5B Database Migration
Creates document_extractions table for OCR extraction storage.
Safe to run multiple times (checks for existing table).
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from backend.app import create_app
from backend.extensions import db
from sqlalchemy import inspect

def migrate_step5b():
    app = create_app('development')
    with app.app_context():
        inspector = inspect(db.engine)
        existing = inspector.get_table_names()

        if 'document_extractions' in existing:
            print('[SKIP] document_extractions table already exists.')
            return

        from backend.models.document_extraction import DocumentExtraction
        DocumentExtraction.__table__.create(db.engine, checkfirst=True)
        print('[OK] document_extractions table created.')

if __name__ == '__main__':
    migrate_step5b()
