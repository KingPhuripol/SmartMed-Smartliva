# 🗄️ SmartLiva Clinical Data & Flywheel Directory

This directory stores clinical dataset structures, zero-leakage patient split definitions, and the SQLite Data Flywheel database for clinician feedback collection.

---

## 🔒 Data Privacy & PDPA Notice

* **Patient Confidentiality (PDPA)**: Raw patient ultrasound images and identifiable DICOM metadata must never be committed to public repositories.
* Demonstration samples for testing and UI evaluation are stored safely in `public/samples/` with full pseudonymization and de-identification.

---

## 📁 Directory Structure

```text
data/
├── flywheel/                            <- Clinical Data Flywheel & SQLite DB
│   └── flywheel.db                      <- Stores doctor reviews, audits & manual overrides
├── patient_split.json                   <- Zero-leakage patient-level stratified split
├── 7272660/                             <- Multi-class liver lesion dataset
│   ├── Benign/                          <- Benign liver lesions
│   ├── Malignant/                       <- Malignant liver lesions (HCC, CCA)
│   ├── Normal/                          <- Normal liver parenchyma
│   └── dataset.csv                      <- Case metadata
├── Fatty/                               <- Hepatic Steatosis dataset (IJCARS)
│   ├── extracted/                       <- Extracted S0, S1, S2, S3 B-mode frames
│   ├── dataset_liver_bmodes_*.mat       <- Raw MATLAB dataset
│   └── yolo_cls_dataset/                <- YOLO format classification split
├── liver-fibrosis-severity-prediction/  <- Liver Fibrosis dataset (F0–F4)
│   ├── images/                          <- B-mode ultrasound frames
│   ├── liver_masks/                     <- Ground-truth segmentation masks
│   ├── liver-lesion/                    <- Paired lesion images and YOLO annotations
│   └── train.csv                        <- Patient stiffness (kPa) & METAVIR labels
├── lesion_yolo_train/                   <- 7-Class Focal Lesion YOLO training split
├── yolo_liver_dataset/                  <- Anatomical Liver Bounding Box dataset
└── README.md                            <- This file
```

---

## 📊 Dataset Splits

The zero-leakage patient-stratified split is defined in [`data/patient_split.json`](file:///Users/king_phuripol/AI-Engineer/01_Projects/Aong-Task/SmartMed/New-SmartLiva/data/patient_split.json). All frames from the same patient are strictly partitioned into either `train`, `val`, or `test` to prevent cross-frame data leakage.
