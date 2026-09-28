"""
AssureX Helper Utilities
Provides identifier generation, timestamp utilities, response formatters, and request detection.
"""

import secrets
import string
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from flask import request


def generate_uid(prefix: str = "UID", length: int = 8) -> str:
    """
    Generate a cryptographically secure, collision-resistant public identifier.
    Example: USR-9A3F1B2C, PRD-4E8D2A1F, CLM-7B3A9C1D.

    Args:
        prefix: 3-letter or descriptive entity prefix (e.g. USR, PRD, CLM, WAR, DOC)
        length: Length of random hex/alphanumeric suffix (default: 8)

    Returns:
        Formatted string like PREFIX-XXXXXXXX
    """
    charset = string.ascii_uppercase + string.digits
    suffix = "".join(secrets.choice(charset) for _ in range(length))
    return f"{prefix.upper()}-{suffix}"


def utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(timezone.utc)


def format_iso(dt: Optional[datetime]) -> Optional[str]:
    """Format datetime object to ISO-8601 string."""
    if dt is None:
        return None
    return dt.isoformat()


def is_api_request() -> bool:
    """Check if the current Flask request expects a JSON/API response."""
    if not request:
        return False
    if request.path.startswith("/api/") or request.path.startswith("/auth/me"):
        return True
    if request.is_json:
        return True
    # If client explicitly specifies application/json preferring over text/html
    try:
        if (
            request.accept_mimetypes["application/json"]
            > request.accept_mimetypes["text/html"]
        ):
            return True
    except Exception:
        pass
    return False


def api_response(
    success: bool = True,
    message: str = "",
    data: Optional[Any] = None,
    errors: Optional[Any] = None,
    status_code: int = 200
) -> tuple[Dict[str, Any], int]:
    """
    Standardized API response dictionary with HTTP status code.

    Returns:
        Tuple of (response_dict, status_code)
    """
    payload = {
        "success": success,
        "message": message,
        "timestamp": utc_now().isoformat()
    }
    if data is not None:
        payload["data"] = data
    if errors is not None:
        payload["errors"] = errors

    return payload, status_code
