"""
AssureX File Handler Utility
Handles file validation, hashing (SHA-256), and safe file storage.
"""

import hashlib
import os
from pathlib import Path
from typing import Optional, Set
from werkzeug.utils import secure_filename
from backend.utils.helpers import generate_uid


DEFAULT_ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "webp", "mp4", "doc", "docx"}
CLAIM_ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "webp"}
DANGEROUS_EXTENSIONS = {"exe", "bat", "cmd", "sh", "php", "js", "py", "vbs", "ps1", "jar", "bin", "com", "msi"}
MAX_CLAIM_FILE_SIZE = 10 * 1024 * 1024  # 10 MB per file

CLAIM_MIME_TYPES = {
    "pdf": {"application/pdf", "application/x-pdf"},
    "png": {"image/png", "image/x-png"},
    "jpg": {"image/jpeg", "image/pjpeg"},
    "jpeg": {"image/jpeg", "image/pjpeg"},
    "webp": {"image/webp"}
}


def get_file_extension(filename: str) -> str:
    """Extract lowercase file extension without the dot."""
    if "." in filename:
        return filename.rsplit(".", 1)[1].lower()
    return ""


def allowed_file(filename: str, allowed_extensions: Optional[Set[str]] = None) -> bool:
    """Check if file extension is allowed."""
    if not filename or "." not in filename:
        return False
    ext = get_file_extension(filename)
    allowed = allowed_extensions if allowed_extensions is not None else DEFAULT_ALLOWED_EXTENSIONS
    return ext in allowed


def is_safe_path(base_dir: str, target_path: str) -> bool:
    """Prevent path traversal by verifying target_path is within base_dir."""
    try:
        base = Path(base_dir).resolve()
        target = Path(target_path).resolve()
        return base in target.parents or base == target
    except Exception:
        return False


def validate_claim_file(file_storage, max_size: int = MAX_CLAIM_FILE_SIZE) -> tuple[bool, Optional[str]]:
    """
    Strictly validate uploaded claim evidence file:
    - Must have a filename
    - Extension must be in CLAIM_ALLOWED_EXTENSIONS (pdf, png, jpg, jpeg, webp)
    - Must not be an executable or dangerous file
    - File size must be within max_size limit
    - File must not be empty
    """
    if not file_storage or not getattr(file_storage, "filename", None):
        return False, "No file was selected or uploaded."

    filename = file_storage.filename.strip()
    if not filename or "." not in filename:
        return False, "File must have a valid extension."

    ext = get_file_extension(filename)

    if ext in DANGEROUS_EXTENSIONS:
        return False, f"Executable and script files (.{ext}) are strictly forbidden."

    if ext not in CLAIM_ALLOWED_EXTENSIONS:
        allowed_list = ", ".join(sorted(CLAIM_ALLOWED_EXTENSIONS)).upper()
        return False, f"Invalid file format '.{ext}'. Supported formats: {allowed_list}."

    # Check file size without permanently consuming stream
    file_storage.stream.seek(0, os.SEEK_END)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)

    if size <= 0:
        return False, "Uploaded file is empty (0 bytes)."

    if size > max_size:
        max_mb = max_size / (1024 * 1024)
        return False, f"File exceeds maximum allowed size of {max_mb:.0f} MB."

    return True, None


def calculate_file_hash(file_stream) -> str:
    """
    Calculate SHA-256 hash of a file stream without consuming it permanently.
    """
    hasher = hashlib.sha256()
    pos = file_stream.tell()
    file_stream.seek(0)
    for chunk in iter(lambda: file_stream.read(8192), b""):
        hasher.update(chunk)
    file_stream.seek(pos)
    return hasher.hexdigest()


def save_uploaded_file(file_storage, upload_root: str, subfolder: str = "documents") -> dict:
    """
    Save an uploaded file safely with a unique filename and return metadata.

    Returns:
        dict with original_filename, stored_filename, relative_path, file_extension,
        file_size, mime_type, file_hash.
    """
    original_filename = secure_filename(file_storage.filename or "unnamed_file")
    ext = get_file_extension(original_filename)
    file_hash = calculate_file_hash(file_storage.stream)

    target_dir = Path(upload_root) / subfolder
    target_dir.mkdir(parents=True, exist_ok=True)

    unique_prefix = generate_uid("DOC", length=6)
    stored_filename = f"{unique_prefix}_{original_filename}"
    target_path = target_dir / stored_filename

    file_storage.save(str(target_path))
    file_size = os.path.getsize(target_path)
    relative_path = (Path(subfolder) / stored_filename).as_posix()

    return {
        "original_filename": original_filename,
        "stored_filename": stored_filename,
        "relative_path": relative_path,
        "absolute_path": str(target_path),
        "file_extension": ext,
        "file_size": file_size,
        "mime_type": file_storage.mimetype,
        "file_hash": file_hash
    }


def save_claim_document(file_storage, upload_root: str, claim_uid: str, doc_uid: Optional[str] = None) -> dict:
    """
    Safely store a claim evidence document organized by claim directory:
    <upload_root>/claims/<claim_uid>/<doc_uid>_<secure_filename>

    Enforces safe unique filenames, prevents path traversal, and returns metadata.
    """
    clean_claim_uid = secure_filename(claim_uid)
    subfolder = Path("claims") / clean_claim_uid

    target_dir = Path(upload_root) / subfolder
    target_dir.mkdir(parents=True, exist_ok=True)

    raw_original = file_storage.filename or "evidence"
    original_filename = secure_filename(raw_original)
    if not original_filename:
        original_filename = "document"

    ext = get_file_extension(original_filename)
    if not ext:
        ext = get_file_extension(raw_original) or "bin"

    doc_prefix = doc_uid or generate_uid("DOC", length=8)
    stored_filename = f"{doc_prefix}_{original_filename}"
    target_path = target_dir / stored_filename

    # Prevent path traversal
    if not is_safe_path(str(Path(upload_root) / "claims"), str(target_path)):
        raise ValueError("Invalid storage path: traversal detected.")

    file_hash = calculate_file_hash(file_storage.stream)
    file_storage.save(str(target_path))
    file_size = os.path.getsize(target_path)
    relative_path = (subfolder / stored_filename).as_posix()

    # Determine safe MIME type
    mime = file_storage.mimetype
    if not mime or mime == "application/octet-stream":
        if ext == "pdf":
            mime = "application/pdf"
        elif ext in ("jpg", "jpeg"):
            mime = "image/jpeg"
        elif ext == "png":
            mime = "image/png"
        elif ext == "webp":
            mime = "image/webp"

    return {
        "original_filename": raw_original,
        "stored_filename": stored_filename,
        "relative_path": relative_path,
        "absolute_path": str(target_path),
        "file_extension": ext,
        "file_size": file_size,
        "mime_type": mime,
        "file_hash": file_hash
    }
