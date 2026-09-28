"""
AssureX TM Model Retrainer
Generates realistic claim summary card images (matching generate_claim_summary_card
output exactly) and retrains the RandomForest on them.

Root cause of bug: training images were 1000x700 near-white images, but real
runtime cards are 480x320 colored cards — model never saw real cards.

Run from repo root:
  python ai_models/teachable_machine/training_data/retrain_on_real_cards.py
"""

import os, sys, random
import numpy as np
import joblib
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report

# ── paths ────────────────────────────────────────────────────────────────────
REPO_ROOT  = Path(__file__).resolve().parent.parent.parent.parent
TRAIN_DIR  = REPO_ROOT / "ai_models" / "teachable_machine" / "training_images"
OUTPUT_PKL = REPO_ROOT / "ai_models" / "teachable_machine" / "exported_model" / "assurex_image_model.pkl"

# Exactly mirrors generate_claim_summary_card constants
CARD_W, CARD_H = 480, 320
BG_COLOR     = (245, 247, 252)
HEADER_COLOR = (30,  41,  59)
ACCENT_COLOR = (56, 189, 248)
TEXT_DARK    = (15,  23,  42)
TEXT_MID     = (71,  85, 105)
BORDER_COLOR = (203, 213, 225)

STATUS_COLORS = {
    "Active":         (34, 197,  94),
    "Expired":        (239,  68,  68),
    "Nearing Expiry": (234, 179,   8),
    "Inactive":       (148, 163, 184),
    "Unknown":        (148, 163, 184),
}
DOC_COLORS = {"Yes": (34, 197, 94), "No": (239, 68, 68)}

IMG_SIZE = (64, 64)
IMAGES_PER_CLASS = 350   # 350 images per class → balanced dataset


# ── font helper ──────────────────────────────────────────────────────────────
def _try_font(size: int):
    for path in ["C:/Windows/Fonts/segoeui.ttf",
                 "C:/Windows/Fonts/arial.ttf",
                 "C:/Windows/Fonts/calibri.ttf"]:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _dot(draw, x, y, color, r=5):
    draw.ellipse([x - r, y - r, x + r, y + r], fill=color)


# ── card generator (mirrors generate_claim_summary_card exactly) ──────────────
def make_card(
    claim_uid:       str,
    product_name:    str,
    damage_type:     str,
    product_age:     int,
    fault_desc:      str,
    claim_status:    str,
    warranty_status: str,
    warranty_dur:    int,
    has_receipt:     str,  # "Yes" / "No"
    has_warranty_card: str,
    has_damage_photo:  str,
    doc_count:       int,
) -> Image.Image:
    img  = Image.new("RGB", (CARD_W, CARD_H), BG_COLOR)
    draw = ImageDraw.Draw(img)

    font_title = _try_font(13)
    font_label = _try_font(10)
    font_value = _try_font(11)
    font_small = _try_font(9)
    font_uid   = _try_font(9)

    # header
    draw.rectangle([0, 0, CARD_W, 44], fill=HEADER_COLOR)
    draw.rectangle([0, 44, CARD_W, 48], fill=ACCENT_COLOR)
    draw.text((14, 10), "AssureX  Claim Summary Card", font=font_title, fill=(255, 255, 255))
    draw.text((14, 30), f"Claim ID: {claim_uid}", font=font_uid, fill=(148, 163, 184))
    draw.text((CARD_W - 120, 30), f"Status: {claim_status}", font=font_uid, fill=(148, 163, 184))

    y = 62
    def row(label, value, dot_color=None):
        nonlocal y
        draw.text((14, y), label.upper(), font=font_label, fill=TEXT_MID)
        if dot_color:
            _dot(draw, 14, y + 18, dot_color, r=4)
            draw.text((26, y + 10), value, font=font_value, fill=TEXT_DARK)
        else:
            draw.text((14, y + 10), value, font=font_value, fill=TEXT_DARK)
        draw.line([14, y + 28, 225, y + 28], fill=BORDER_COLOR, width=1)
        y += 36

    row("Product",           product_name[:28])
    row("Damage Type",       damage_type[:28])
    row("Product Age",       f"{product_age} months")
    row("Fault Description", (fault_desc[:28] + "…") if len(fault_desc) > 28 else fault_desc or "—")
    ws_color = STATUS_COLORS.get(warranty_status, (148, 163, 184))
    row("Warranty Status",   f"{warranty_status}  ({warranty_dur}m)", dot_color=ws_color)

    # right column
    rx, ry = 248, 62
    draw.text((rx, ry), "DOCUMENTS", font=font_label, fill=TEXT_MID)
    ry += 16

    def doc_row(label, present):
        nonlocal ry
        color = DOC_COLORS.get(present, (148, 163, 184))
        _dot(draw, rx + 6, ry + 6, color, r=5)
        draw.text((rx + 18, ry),      label,   font=font_value, fill=TEXT_DARK)
        draw.text((rx + 18, ry + 13), present, font=font_small, fill=color)
        ry += 32

    doc_row("Receipt / Invoice", has_receipt)
    doc_row("Warranty Card",     has_warranty_card)
    doc_row("Damage Photo",      has_damage_photo)

    ry += 8
    draw.text((rx, ry),      "TOTALS",                          font=font_label, fill=TEXT_MID)
    ry += 14
    draw.text((rx, ry), f"{doc_count} document(s) uploaded",    font=font_value, fill=TEXT_DARK)

    # footer
    draw.rectangle([0, CARD_H - 24, CARD_W, CARD_H], fill=HEADER_COLOR)
    draw.text((14, CARD_H - 16),
              "AssureX Claim Engine  ·  Auto-generated  ·  For image-model evaluation only",
              font=font_small, fill=(148, 163, 184))

    draw.rectangle([0, 0, CARD_W - 1, CARD_H - 1], outline=BORDER_COLOR, width=2)
    return img


# ── scenario generators ───────────────────────────────────────────────────────
PRODUCTS = [
    "Samsung Galaxy A54", "HP Laptop 15s", "LG Smart TV 43",
    "Dell XPS 15",        "Apple iPhone 14", "Sony Bravia 55",
    "Huawei P50",         "Xiaomi Note 12",  "Lenovo IdeaPad",
    "Canon EOS 2000D",    "Bosch Washing Machine", "Haier Fridge",
    "Orient Air Conditioner", "Dawlance Microwave", "TCL Monitor 27",
    "OnePlus Nord CE3",   "Vivo Y22",        "Oppo Reno 9",
    "Nokia G60",          "Motorola Edge 40",
]
DAMAGE_TYPES = [
    "Screen Damage", "Water Damage", "Battery Fault", "Charging Port",
    "Speaker Issue", "Overheating",  "Physical Damage", "Software Bug",
    "Camera Fault",  "Keyboard Issue",
]
FAULT_DESCS = [
    "Device not powering on",
    "Screen cracked after drop",
    "Battery draining fast",
    "Charging port not working",
    "Speaker distorted sound",
    "Device overheating rapidly",
    "Camera not focusing properly",
    "WiFi connectivity issues",
    "Keyboard keys not responding",
    "Device randomly restarting",
]
STATUSES = ["Submitted", "Under Review", "Approved", "Rejected", "Pending"]


def rand_uid(prefix="CLM"):
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ0123456789"
    return prefix + "-" + "".join(random.choices(chars, k=8))


def gen_valid() -> dict:
    """Active warranty + all 3 docs present → should be Valid."""
    age = random.randint(1, 18)
    dur = random.randint(age + 2, 36)
    return dict(
        claim_uid=rand_uid(),
        product_name=random.choice(PRODUCTS),
        damage_type=random.choice(DAMAGE_TYPES),
        product_age=age,
        fault_desc=random.choice(FAULT_DESCS),
        claim_status=random.choice(["Submitted", "Under Review"]),
        warranty_status="Active",
        warranty_dur=dur,
        has_receipt="Yes",
        has_warranty_card="Yes",
        has_damage_photo="Yes",
        doc_count=random.randint(3, 5),
    )


def gen_invalid() -> dict:
    """Expired warranty + missing key docs → should be Invalid."""
    age = random.randint(13, 36)
    dur = random.randint(6, age - 1)
    receipt = random.choice(["No", "No", "Yes"])
    wcard   = "No"
    return dict(
        claim_uid=rand_uid(),
        product_name=random.choice(PRODUCTS),
        damage_type=random.choice(DAMAGE_TYPES),
        product_age=age,
        fault_desc=random.choice(FAULT_DESCS),
        claim_status=random.choice(["Rejected", "Submitted"]),
        warranty_status="Expired",
        warranty_dur=dur,
        has_receipt=receipt,
        has_warranty_card=wcard,
        has_damage_photo=random.choice(["Yes", "No"]),
        doc_count=random.randint(0, 2),
    )


def gen_manual() -> dict:
    """Nearing Expiry or Inactive warranty + mixed docs → Manual Review."""
    ws = random.choice(["Nearing Expiry", "Nearing Expiry", "Inactive"])
    age = random.randint(8, 20)
    dur = random.randint(12, 24)
    return dict(
        claim_uid=rand_uid(),
        product_name=random.choice(PRODUCTS),
        damage_type=random.choice(DAMAGE_TYPES),
        product_age=age,
        fault_desc=random.choice(FAULT_DESCS),
        claim_status=random.choice(STATUSES),
        warranty_status=ws,
        warranty_dur=dur,
        has_receipt=random.choice(["Yes", "No"]),
        has_warranty_card=random.choice(["Yes", "No"]),
        has_damage_photo=random.choice(["Yes", "Yes", "No"]),
        doc_count=random.randint(1, 3),
    )


# ── feature extraction (identical to service) ─────────────────────────────────
def extract_features(img: Image.Image) -> np.ndarray:
    img_r = img.convert("RGB").resize(IMG_SIZE)
    arr   = np.array(img_r, dtype=np.float32) / 255.0
    pixels = arr.flatten()
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    stats = np.array([
        r.mean(), r.std(), r.min(), r.max(),
        g.mean(), g.std(), g.min(), g.max(),
        b.mean(), b.std(), b.min(), b.max(),
        arr.mean(), arr.std(),
        arr.max() - arr.min(),
    ])
    return np.concatenate([pixels, stats])


# ── main ──────────────────────────────────────────────────────────────────────
def main():
    random.seed(42)
    np.random.seed(42)

    CLASS_CONFIG = [
        ("Valid",         gen_valid,   TRAIN_DIR / "Valid"),
        ("Invalid",       gen_invalid, TRAIN_DIR / "Invalid"),
        ("Manual Review", gen_manual,  TRAIN_DIR / "Manual_Review"),
    ]

    X, y = [], []

    for label, gen_fn, out_dir in CLASS_CONFIG:
        out_dir.mkdir(parents=True, exist_ok=True)
        print(f"\nGenerating {IMAGES_PER_CLASS} cards for class '{label}' → {out_dir}")

        for i in range(IMAGES_PER_CLASS):
            params = gen_fn()
            card   = make_card(**params)

            # Save card PNG to training folder (replaces old white images)
            fname = f"generated_{i+1:04d}.png"
            card.save(str(out_dir / fname), "PNG")

            feat = extract_features(card)
            X.append(feat)
            y.append(label)

            if (i + 1) % 50 == 0:
                print(f"  {i+1}/{IMAGES_PER_CLASS}")

    X = np.array(X)
    y = np.array(y)
    print(f"\nDataset: {X.shape[0]} images, {X.shape[1]} features each")
    print(f"Classes: {np.unique(y)}")

    # ── train ─────────────────────────────────────────────────────────────────
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    print(f"\nTrain: {len(X_train)}, Test: {len(X_test)}")
    print("Training RandomForest…")

    model = RandomForestClassifier(
        n_estimators=200,
        max_depth=20,
        min_samples_leaf=2,
        random_state=42,
        class_weight="balanced",
        n_jobs=-1,
    )
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    acc    = accuracy_score(y_test, y_pred)
    print(f"\nTest Accuracy: {acc:.4f}")
    print(classification_report(y_test, y_pred))

    avg_conf = float(np.mean(np.max(model.predict_proba(X_test), axis=1)))
    print(f"Avg Confidence: {avg_conf:.4f}")

    # ── save ──────────────────────────────────────────────────────────────────
    package = {
        "model":            model,
        "classes":          list(model.classes_),
        "img_size":         list(IMG_SIZE),
        "model_name":       "AssureX-ImageClassifier-v2",
        "model_version":    "2.0.0",
        "test_accuracy":    acc,
        "average_confidence": avg_conf,
    }
    joblib.dump(package, str(OUTPUT_PKL))
    print(f"\nModel saved to: {OUTPUT_PKL}")

    # ── quick smoke test on real cards ────────────────────────────────────────
    real_cards = list((REPO_ROOT / "claim_summary_cards").glob("CLM-*.png"))
    if real_cards:
        print("\n--- Smoke test on real claim cards ---")
        for card_path in real_cards:
            img  = Image.open(card_path)
            feat = extract_features(img).reshape(1, -1)
            pred = str(model.predict(feat)[0])
            prob = dict(zip([str(c) for c in model.classes_],
                            [round(p, 3) for p in model.predict_proba(feat)[0]]))
            print(f"  {card_path.name} → {pred}  {prob}")

    print("\nDone! Restart the Flask server to load the new model.")


if __name__ == "__main__":
    main()
