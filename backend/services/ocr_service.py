"""
AssureX OCR Service
Handles OCR text extraction from PDF and image documents.
Uses pypdf for text-based PDFs and RapidOCR (ONNX-based) for images and scanned PDFs.
No generative AI is used. All text comes from actual uploaded documents.
"""

import io
import logging
import os
from pathlib import Path
from typing import Tuple, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# PDF text extraction via pypdf
# ---------------------------------------------------------------------------
def _extract_pdf_text(file_path: str) -> Tuple[str, str]:
    """
    Attempt to extract selectable text from a PDF using pypdf.
    Returns (text, engine_name). Raises on failure.
    """
    try:
        from pypdf import PdfReader
        reader = PdfReader(file_path)
        pages_text = []
        for page in reader.pages:
            try:
                t = page.extract_text() or ""
                if t.strip():
                    pages_text.append(t.strip())
            except Exception:
                pass
        return "\n".join(pages_text), "pypdf"
    except ImportError:
        raise RuntimeError("pypdf not available")


# ---------------------------------------------------------------------------
# Image OCR via RapidOCR
# ---------------------------------------------------------------------------
def _extract_image_text_rapidocr(file_path: str) -> Tuple[str, str]:
    """
    Perform OCR on an image file using RapidOCR (ONNX-based, no Tesseract needed).
    Returns (text, engine_name).
    """
    try:
        from rapidocr_onnxruntime import RapidOCR
        import numpy as np
        from PIL import Image

        engine = RapidOCR()
        img = Image.open(file_path).convert("RGB")
        img_array = np.array(img)
        result, _ = engine(img_array)
        if not result:
            return "", "rapidocr"
        lines = [item[1] for item in result if item and len(item) >= 2]
        return "\n".join(lines), "rapidocr"
    except ImportError:
        raise RuntimeError("rapidocr-onnxruntime not available")
    except Exception as e:
        raise RuntimeError(f"RapidOCR image extraction failed: {e}")


# ---------------------------------------------------------------------------
# PDF-as-image fallback (render first page as image, then OCR)
# ---------------------------------------------------------------------------
def _pdf_image_ocr_fallback(file_path: str) -> Tuple[str, str]:
    """
    Render each PDF page to a raster image using PyMuPDF (fitz), then run
    RapidOCR on each rendered page.  Works for both image-only and mixed PDFs.
    Falls back to the older pypdf embedded-image approach if PyMuPDF is absent.
    """
    # --- Primary: PyMuPDF page render → RapidOCR ---
    try:
        import pymupdf as fitz  # PyMuPDF ≥ 1.24 preferred name
    except ImportError:
        try:
            import fitz  # older alias still works
        except ImportError:
            fitz = None

    if fitz is not None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            import numpy as np

            engine = RapidOCR()
            doc = fitz.open(file_path)
            texts = []
            mat = fitz.Matrix(2.0, 2.0)  # 2× zoom → sharper OCR
            for page in doc:
                pix = page.get_pixmap(matrix=mat)
                img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                    pix.height, pix.width, pix.n
                )
                if pix.n == 4:
                    img_array = img_array[:, :, :3]
                result, _ = engine(img_array)
                if result:
                    texts.extend(item[1] for item in result if item and len(item) >= 2)
            doc.close()
            if texts:
                return "\n".join(texts), "rapidocr+pymupdf"
        except Exception as e:
            logger.debug("PyMuPDF+RapidOCR fallback failed: %s", e)

    # --- Secondary: pypdf embedded-image extraction → RapidOCR ---
    try:
        from pypdf import PdfReader
        import io as _io
        from PIL import Image
        import numpy as np
        from rapidocr_onnxruntime import RapidOCR

        reader = PdfReader(file_path)
        engine = RapidOCR()
        texts = []
        for page in reader.pages:
            for img_obj in page.images:
                try:
                    img = Image.open(_io.BytesIO(img_obj.data)).convert("RGB")
                    result, _ = engine(np.array(img))
                    if result:
                        texts.extend(item[1] for item in result if item and len(item) >= 2)
                except Exception:
                    continue
        return "\n".join(texts), "rapidocr+pypdf-images"
    except Exception as e:
        raise RuntimeError(f"PDF image OCR fallback failed: {e}")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def extract_text_from_document(file_path: str, file_extension: str) -> dict:
    """
    Primary OCR dispatcher. Determines document type and applies the appropriate
    extraction strategy.

    Returns:
        {
            "success": bool,
            "raw_text": str or None,
            "engine": str or None,
            "error": str or None,
            "is_empty": bool
        }
    """
    ext = (file_extension or "").lower().lstrip(".")

    if not os.path.exists(file_path):
        return {
            "success": False, "raw_text": None,
            "engine": None, "error": "File not found on storage.",
            "is_empty": True
        }

    try:
        if ext == "pdf":
            # Step 1: Try selectable text extraction
            try:
                text, engine = _extract_pdf_text(file_path)
                if text.strip():
                    return {"success": True, "raw_text": text, "engine": engine, "error": None, "is_empty": False}
            except Exception as e:
                logger.debug("PDF text extraction failed: %s", e)

            # Step 2: PDF contains images — run OCR on embedded images
            try:
                text, engine = _pdf_image_ocr_fallback(file_path)
                if text.strip():
                    return {"success": True, "raw_text": text, "engine": engine, "error": None, "is_empty": False}
            except Exception as e:
                logger.debug("PDF image OCR fallback failed: %s", e)

            # Step 3: Return empty result for PDFs with no extractable content
            return {"success": True, "raw_text": "", "engine": "pypdf", "error": None, "is_empty": True}

        elif ext in ("png", "jpg", "jpeg", "webp"):
            try:
                text, engine = _extract_image_text_rapidocr(file_path)
                is_empty = not bool(text.strip())
                return {"success": True, "raw_text": text, "engine": engine, "error": None, "is_empty": is_empty}
            except Exception as e:
                logger.warning("Image OCR failed for %s: %s", file_path, e)
                return {"success": False, "raw_text": None, "engine": None, "error": str(e), "is_empty": True}

        else:
            return {
                "success": False, "raw_text": None,
                "engine": None,
                "error": f"Unsupported file type for OCR: .{ext}",
                "is_empty": True
            }

    except Exception as exc:
        logger.exception("Unexpected OCR error for %s", file_path)
        return {
            "success": False, "raw_text": None,
            "engine": None, "error": f"OCR processing error: {exc}",
            "is_empty": True
        }
