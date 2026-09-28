"""
AssureX Dataset Split Script
Splits claims_data.csv into Train (70%) / Validation (15%) / Test (15%)
and saves each split to dataset/train/, dataset/validation/, dataset/test/

Run from project root:
    python dataset/split_dataset.py
"""

import os
import sys
from pathlib import Path

import pandas as pd
from sklearn.model_selection import train_test_split

# ── Paths ──────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CSV_IN       = PROJECT_ROOT / "ai_models" / "python_model" / "training_data" / "claims_data.csv"
EXCEL_IN     = PROJECT_ROOT / "ai_models" / "python_model" / "training_data" / "claims_data.xlsx"
OUT_TRAIN    = PROJECT_ROOT / "dataset" / "train"
OUT_VAL      = PROJECT_ROOT / "dataset" / "validation"
OUT_TEST     = PROJECT_ROOT / "dataset" / "test"
OUT_META     = PROJECT_ROOT / "dataset" / "metadata"

TARGET = "Claim_Decision"
RANDOM_STATE = 42

def main():
    # ── Load ──────────────────────────────────────────────────────────────
    print("Loading dataset...")
    if CSV_IN.exists():
        df = pd.read_csv(CSV_IN)
        print(f"Loaded CSV: {CSV_IN.name}  ({len(df)} rows)")
    elif EXCEL_IN.exists():
        df = pd.read_excel(EXCEL_IN)
        print(f"Loaded Excel: {EXCEL_IN.name}  ({len(df)} rows)")
    else:
        print(f"ERROR: Dataset not found at:\n  {CSV_IN}\n  {EXCEL_IN}")
        sys.exit(1)

    if TARGET not in df.columns:
        print(f"ERROR: Column '{TARGET}' not found. Columns: {list(df.columns)}")
        sys.exit(1)

    print(f"\nClass distribution (full):\n{df[TARGET].value_counts().to_string()}")

    # ── Split: 70 / 15 / 15 ───────────────────────────────────────────────
    # Step 1: 85% trainval  +  15% test
    df_trainval, df_test = train_test_split(
        df,
        test_size=0.15,
        random_state=RANDOM_STATE,
        stratify=df[TARGET]
    )
    # Step 2: of 85%, take ~17.6% as validation → gives 15% of total
    df_train, df_val = train_test_split(
        df_trainval,
        test_size=0.1765,
        random_state=RANDOM_STATE,
        stratify=df_trainval[TARGET]
    )

    print(f"\nSplit results (70 / 15 / 15):")
    print(f"  Training:   {len(df_train):>5} rows  ({len(df_train)/len(df)*100:.1f}%)")
    print(f"  Validation: {len(df_val):>5} rows  ({len(df_val)/len(df)*100:.1f}%)")
    print(f"  Testing:    {len(df_test):>5} rows  ({len(df_test)/len(df)*100:.1f}%)")
    print(f"  Total:      {len(df_train)+len(df_val)+len(df_test):>5} rows")

    # ── Save splits ───────────────────────────────────────────────────────
    for folder in (OUT_TRAIN, OUT_VAL, OUT_TEST, OUT_META):
        folder.mkdir(parents=True, exist_ok=True)

    df_train.to_csv(OUT_TRAIN / "train.csv", index=False)
    df_val.to_csv(OUT_VAL / "validation.csv", index=False)
    df_test.to_csv(OUT_TEST / "test.csv", index=False)

    print(f"\nFiles saved:")
    print(f"  {OUT_TRAIN / 'train.csv'}")
    print(f"  {OUT_VAL / 'validation.csv'}")
    print(f"  {OUT_TEST / 'test.csv'}")

    # ── Save metadata ─────────────────────────────────────────────────────
    meta = {
        "total_records": len(df),
        "train_records": len(df_train),
        "validation_records": len(df_val),
        "test_records": len(df_test),
        "split_ratio": "70/15/15",
        "random_state": RANDOM_STATE,
        "target_column": TARGET,
        "features": [c for c in df.columns if c != TARGET],
        "classes": sorted(df[TARGET].unique().tolist()),
        "class_distribution_full": df[TARGET].value_counts().to_dict(),
        "class_distribution_train": df_train[TARGET].value_counts().to_dict(),
        "class_distribution_val": df_val[TARGET].value_counts().to_dict(),
        "class_distribution_test": df_test[TARGET].value_counts().to_dict(),
    }

    import json
    meta_path = OUT_META / "dataset_metadata.json"
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)
    print(f"  {meta_path}")

    print("\nDataset split complete.")


if __name__ == "__main__":
    main()
