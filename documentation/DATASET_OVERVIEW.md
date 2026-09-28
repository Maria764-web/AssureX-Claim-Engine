# AssureX Dataset — Overview & Split Documentation

**Project:** AssureX Claim Engine  
**Dataset Type:** Warranty Claim Records (Structured / Tabular)  
**Total Records:** 1,500  
**Total Features:** 17 columns  

---

## Dataset Description

The AssureX dataset contains synthetic warranty claim records for consumer electronics. Each record represents one claim filed by a customer, with features covering product details, document availability, AI model scores, and the final claim decision.

This dataset is used to train and evaluate the AI-based claim validation model.

---

## Features (Columns)

| Column | Type | Description |
|--------|------|-------------|
| Claim_ID | String | Unique identifier for each claim |
| Product_Category | Categorical | Type of product (Mobile, Laptop, TV, Camera, Washing Machine, Refrigerator) |
| Product_Age_Months | Integer | Age of product in months at time of claim |
| Warranty_Duration_Months | Integer | Warranty period in months |
| Warranty_Status | Categorical | Active / Expired / Inactive / Unknown |
| Receipt_Available | Boolean | Whether purchase receipt was submitted |
| Warranty_Card_Available | Boolean | Whether warranty card was submitted |
| Damage_Photo_Available | Boolean | Whether damage photo was submitted |
| Serial_Number_Status | Categorical | Match / Mismatch / Unknown |
| Damage_Covered | Categorical | Yes / No / Unknown |
| Contradiction_Detected | Boolean | Whether contradictions were found in documents |
| Missing_Document | Boolean | Whether any required document is missing |
| Document_Quality_Score | Integer (0–100) | OCR/quality score of uploaded documents |
| Damage_Severity_Score | Integer (0–100) | Estimated damage severity score |
| Previous_Repair_Count | Integer | Number of prior repairs on record |
| Claim_Amount | Float | Claimed amount in currency units |
| Claim_Decision | Categorical | **Target variable** — Valid / Invalid / Manual Review |

---

## Dataset Split

| Split | File | Records | Percentage |
|-------|------|---------|------------|
| Training | dataset/train/train.csv | 1,049 | ~70% |
| Validation | dataset/validation/validation.csv | 226 | ~15% |
| Test | dataset/test/test.csv | 225 | ~15% |
| **Total** | | **1,500** | **100%** |

---

## Target Variable Distribution (Claim_Decision)

| Decision | Description |
|----------|-------------|
| Valid | Claim meets all warranty rules and is approved |
| Invalid | Claim fails one or more validation checks |
| Manual Review | Claim requires human reviewer due to ambiguity |

---

## Sample Data (Training Set — First 5 Rows)

| Claim_ID | Product_Category | Product_Age_Months | Warranty_Status | Claim_Decision |
|----------|-----------------|-------------------|-----------------|----------------|
| CLM-01270 | Mobile | 23 | Expired | Manual Review |
| CLM-00303 | Camera | 11 | Active | Manual Review |
| CLM-00295 | Washing Machine | 70 | Inactive | Invalid |
| CLM-01037 | TV | 20 | Inactive | Invalid |
| CLM-00728 | Laptop | 39 | Active | Manual Review |

---

## File Locations (in GitHub Repository)

```
dataset/
├── train/
│   └── train.csv          (1,049 records)
├── validation/
│   └── validation.csv     (226 records)
├── test/
│   └── test.csv           (225 records)
├── metadata/
│   └── dataset_metadata.json
└── split_dataset.py       (script used to generate the split)
```

---

*Dataset generated for AssureX Claim Engine — Competition Submission 2026*
