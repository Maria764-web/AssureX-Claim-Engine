"""
AssureX Claim Summary Card Generator
Generates a standardised visual card image from claim data.
This image is fed to the Teachable Machine image classifier.
The card never shows the Python model's own prediction (SRS requirement).
"""

import os
import logging
from pathlib import Path
from typing import Optional, Any

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

CARDS_DIR = Path(__file__).resolve().parent.parent.parent / "claim_summary_cards"
CARDS_DIR.mkdir(exist_ok=True)

CARD_W, CARD_H = 480, 320
BG_COLOR     = (245, 247, 252)
HEADER_COLOR = (30,  41,  59)
ACCENT_COLOR = (56, 189, 248)
TEXT_DARK    = (15,  23,  42)
TEXT_MID     = (71,  85, 105)
BORDER_COLOR = (203, 213, 225)

STATUS_COLORS = {
    "Active":          (34, 197,  94),
    "Expired":         (239,  68,  68),
    "Nearing Expiry":  (234, 179,   8),
    "Inactive":        (148, 163, 184),
    "Unknown":         (148, 163, 184),
}

DOC_COLORS = {
    "Yes": (34, 197, 94),
    "No":  (239, 68, 68),
}


def _try_font(size: int) -> ImageFont.FreeTypeFont:
    """Load a system font, fall back to default."""
    candidates = [
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibri.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _dot(draw: ImageDraw.ImageDraw, x: int, y: int, color: tuple, r: int = 5) -> None:
    draw.ellipse([x - r, y - r, x + r, y + r], fill=color)


def generate_claim_summary_card(claim: Any) -> Optional[str]:
    """
    Generate a Claim Summary Card PNG for a given Claim object.
    Saves to claim_summary_cards/<claim_uid>.png and returns the file path.
    Returns None on failure.
    """
    try:
        # ── gather data ─────────────────────────────────────────────────────
        product   = getattr(claim, "product", None)
        warranty  = getattr(claim, "warranty", None)
        documents = getattr(claim, "documents", []) or []

        claim_uid     = getattr(claim, "claim_uid",   "UNKNOWN")
        product_name  = "Unknown"
        if product:
            brand = getattr(product, "brand", "") or ""
            model = getattr(product, "model", "") or ""
            category = getattr(product, "category", "") or ""
            product_name = f"{brand} {model}".strip() or category or "Unknown"

        product_age   = getattr(claim, "product_age", 0) or 0
        damage_type   = getattr(claim, "damage_type", "Not specified") or "Not specified"
        fault_desc    = getattr(claim, "fault_description", "") or ""
        claim_status  = getattr(claim, "claim_status", "Submitted") or "Submitted"

        warranty_status = "Unknown"
        warranty_duration = 0
        if warranty:
            try:
                warranty_status = warranty.calculate_status()
            except Exception:
                warranty_status = getattr(warranty, "warranty_status", "Unknown")
            warranty_duration = getattr(warranty, "duration_months", 0) or 0

        doc_types = {(getattr(d, "document_type", "") or "").lower() for d in documents}
        has_receipt = "Yes" if any("receipt" in t or "invoice" in t for t in doc_types) else "No"
        has_warranty_card = "Yes" if any("warranty" in t or "card" in t for t in doc_types) else "No"
        has_damage_photo = "Yes" if any("photo" in t or "damage" in t or "image" in t for t in doc_types) else "No"
        doc_count = len(documents)

        # ── create canvas ───────────────────────────────────────────────────
        img  = Image.new("RGB", (CARD_W, CARD_H), BG_COLOR)
        draw = ImageDraw.Draw(img)

        font_title  = _try_font(13)
        font_label  = _try_font(10)
        font_value  = _try_font(11)
        font_small  = _try_font(9)
        font_uid    = _try_font(9)

        # ── header bar ──────────────────────────────────────────────────────
        draw.rectangle([0, 0, CARD_W, 44], fill=HEADER_COLOR)
        draw.rectangle([0, 44, CARD_W, 48], fill=ACCENT_COLOR)
        draw.text((14, 10), "AssureX  Claim Summary Card", font=font_title, fill=(255, 255, 255))
        draw.text((14, 30), f"Claim ID: {claim_uid}", font=font_uid, fill=(148, 163, 184))
        draw.text((CARD_W - 120, 30), f"Status: {claim_status}", font=font_uid, fill=(148, 163, 184))

        # ── left column ─────────────────────────────────────────────────────
        y = 62
        def row(label: str, value: str, dot_color: tuple = None):
            nonlocal y
            draw.text((14, y), label.upper(), font=font_label, fill=TEXT_MID)
            if dot_color:
                _dot(draw, 14, y + 18, dot_color, r=4)
                draw.text((26, y + 10), value, font=font_value, fill=TEXT_DARK)
            else:
                draw.text((14, y + 10), value, font=font_value, fill=TEXT_DARK)
            draw.line([14, y + 28, 225, y + 28], fill=BORDER_COLOR, width=1)
            y += 36

        row("Product", product_name[:28])
        row("Damage Type", damage_type[:28])
        row("Product Age", f"{product_age} months")
        row("Fault Description", (fault_desc[:28] + "…") if len(fault_desc) > 28 else fault_desc or "—")

        # warranty status with colour dot
        ws_color = STATUS_COLORS.get(warranty_status, (148, 163, 184))
        row("Warranty Status", f"{warranty_status}  ({warranty_duration}m)", dot_color=ws_color)

        # ── right column — documents ─────────────────────────────────────────
        rx = 248
        ry = 62
        draw.text((rx, ry), "DOCUMENTS", font=font_label, fill=TEXT_MID)
        ry += 16

        def doc_row(label: str, present: str):
            nonlocal ry
            color = DOC_COLORS.get(present, (148, 163, 184))
            _dot(draw, rx + 6, ry + 6, color, r=5)
            draw.text((rx + 18, ry), label, font=font_value, fill=TEXT_DARK)
            draw.text((rx + 18, ry + 13), present, font=font_small, fill=color)
            ry += 32

        doc_row("Receipt / Invoice", has_receipt)
        doc_row("Warranty Card",     has_warranty_card)
        doc_row("Damage Photo",      has_damage_photo)

        ry += 8
        draw.text((rx, ry), "TOTALS", font=font_label, fill=TEXT_MID)
        ry += 14
        draw.text((rx, ry), f"{doc_count} document(s) uploaded", font=font_value, fill=TEXT_DARK)

        # ── footer ──────────────────────────────────────────────────────────
        draw.rectangle([0, CARD_H - 24, CARD_W, CARD_H], fill=HEADER_COLOR)
        draw.text((14, CARD_H - 16),
                  "AssureX Claim Engine  ·  Auto-generated  ·  For image-model evaluation only",
                  font=font_small, fill=(148, 163, 184))

        # ── outer border ────────────────────────────────────────────────────
        draw.rectangle([0, 0, CARD_W - 1, CARD_H - 1], outline=BORDER_COLOR, width=2)

        # ── save ────────────────────────────────────────────────────────────
        out_path = str(CARDS_DIR / f"{claim_uid}.png")
        img.save(out_path, "PNG")
        logger.info("Claim summary card saved: %s", out_path)
        return out_path

    except Exception as e:
        logger.error("Failed to generate claim summary card for claim %s: %s",
                     getattr(claim, "claim_uid", "?"), e, exc_info=True)
        return None
