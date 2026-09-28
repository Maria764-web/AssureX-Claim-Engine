"""
AssureX Database Configuration
Provides database connection utilities and SQLite initialization helpers.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB_FILE = BASE_DIR / "assurex.db"


def get_database_uri() -> str:
    """Return the SQLAlchemy database URI from environment or default SQLite path."""
    return os.environ.get("DATABASE_URL", f"sqlite:///{DEFAULT_DB_FILE.as_posix()}")


def ensure_db_directory_exists(db_uri: str) -> None:
    """Ensure that the parent directory for a SQLite database file exists."""
    if db_uri.startswith("sqlite:///"):
        db_path = db_uri.replace("sqlite:///", "")
        if db_path != ":memory:":
            parent_dir = Path(db_path).parent
            parent_dir.mkdir(parents=True, exist_ok=True)
