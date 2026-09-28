"""
AssureX Duplicate Document Detection Service
Uses SHA-256 digital fingerprints (file_hash) stored on the Document model
to detect when the same physical file is uploaded more than once — either
within the same claim or across different claims by the same user.
"""

import hashlib
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Hash utility
# ---------------------------------------------------------------------------

def compute_sha256(file_path: str) -> Optional[str]:
    """
    Compute the SHA-256 hash of a file on disk.
    Returns the hex-digest string, or None on failure.
    """
    try:
        sha = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha.update(chunk)
        return sha.hexdigest()
    except Exception as e:
        logger.error("SHA-256 computation failed for %s: %s", file_path, e)
        return None


# ---------------------------------------------------------------------------
# Duplicate detection against the database
# ---------------------------------------------------------------------------

def find_duplicate_documents(
    file_hash: str,
    exclude_document_id: Optional[int] = None,
    user_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Search the documents table for existing records with the same file_hash.

    Args:
        file_hash:           SHA-256 hex digest to look up.
        exclude_document_id: Document ID to ignore (skip the document being
                             checked — avoids self-match after upload).
        user_id:             When provided, only searches documents owned by
                             this user (for per-user duplicate scope).

    Returns:
        List of dicts, each representing a matching duplicate document.
    """
    from backend.models.document import Document

    query = Document.query.filter_by(file_hash=file_hash)

    if exclude_document_id is not None:
        query = query.filter(Document.id != exclude_document_id)

    if user_id is not None:
        query = query.filter_by(user_id=user_id)

    matches = query.all()

    result = []
    for doc in matches:
        result.append({
            "document_id":   doc.id,
            "document_uid":  doc.document_uid,
            "document_type": doc.document_type,
            "filename":      doc.original_filename,
            "file_hash":     doc.file_hash,
            "claim_id":      doc.claim_id,
            "uploaded_at":   doc.upload_timestamp.isoformat() if doc.upload_timestamp else None,
        })

    return result


def check_document_duplicate(
    file_hash: str,
    exclude_document_id: Optional[int] = None,
    user_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Public entry point — check whether a file (identified by its SHA-256 hash)
    has already been uploaded.

    Returns a structured result dict:
        - is_duplicate (bool): True if at least one matching document found
        - duplicate_count (int): number of matching documents
        - duplicates (list): detail of each match
        - details (str): human-readable summary
    """
    try:
        duplicates = find_duplicate_documents(
            file_hash=file_hash,
            exclude_document_id=exclude_document_id,
            user_id=user_id
        )
    except Exception as e:
        logger.error("Duplicate document detection error: %s", e, exc_info=True)
        return {
            "is_duplicate": False,
            "duplicate_count": 0,
            "duplicates": [],
            "details": f"Duplicate check could not complete: {e}"
        }

    is_dup = len(duplicates) > 0

    if is_dup:
        uids = [d["document_uid"] for d in duplicates]
        details = (
            f"This file has already been uploaded "
            f"({len(duplicates)} existing record(s): {', '.join(uids)})."
        )
    else:
        details = "No duplicate document found — file hash is unique."

    return {
        "is_duplicate": is_dup,
        "duplicate_count": len(duplicates),
        "duplicates": duplicates,
        "details": details
    }


def check_document_duplicate_from_path(
    file_path: str,
    exclude_document_id: Optional[int] = None,
    user_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Convenience wrapper: compute SHA-256 from a file path, then run the
    duplicate check.  Returns the same dict as check_document_duplicate(),
    plus the computed hash under the key 'file_hash'.
    """
    file_hash = compute_sha256(file_path)

    if not file_hash:
        return {
            "is_duplicate": False,
            "duplicate_count": 0,
            "duplicates": [],
            "file_hash": None,
            "details": "Could not compute file hash — duplicate check skipped."
        }

    result = check_document_duplicate(
        file_hash=file_hash,
        exclude_document_id=exclude_document_id,
        user_id=user_id
    )
    result["file_hash"] = file_hash
    return result
