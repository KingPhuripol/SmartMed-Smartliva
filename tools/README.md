# 🛠️ SmartLiva Tooling & Engineering Suite

Comprehensive collection of scripts and utilities for data preparation, multi-organ model training, clinical benchmarking, test suites, and report generation.

---

## 📑 Table of Contents

1. [🚀 Training Pipelines](#1-training-pipelines)
2. [📦 Dataset Preparation & Export](#2-dataset-preparation--export)
3. [🧪 Evaluation & Clinical Benchmarks](#3-evaluation--clinical-benchmarks)
4. [📄 Clinical & IP Report Generators](#4-clinical--ip-report-generators)

---

## 1. 🚀 Training Pipelines

| Script | Model / Task | Architecture / Approach | Output Path |
| :--- | :--- | :--- | :--- |
| [`train_yolo26_lesion_detection.py`](file:///Users/king_phuripol/AI-Engineer/01_Projects/Aong-Task/SmartMed/New-SmartLiva/tools/train_yolo26_lesion_detection.py) | Focal Lesion Detection (7 classes) | YOLO26s (Hemangioma, Cyst, Calcification, Metastasis, HCC, CCA, FFC) | `weights/lesion/yolo26s_lesion_best.pt` |
| [`train_yolo26_mass_instance_seg.py`](file:///Users/king_phuripol/AI-Engineer/01_Projects/Aong-Task/SmartMed/New-SmartLiva/tools/train_yolo26_mass_instance_seg.py) | Tumor / Mass Instance Segmentation | YOLO26s-seg (Pixel-accurate tumor boundaries) | `weights/lesion/yolo26s_mass_seg_best.pt` |
| [`train_yolo26_fibrosis_cls.py`](file:///Users/king_phuripol/AI-Engineer/01_Projects/Aong-Task/SmartMed/New-SmartLiva/tools/train_yolo26_fibrosis_cls.py) | Liver Fibrosis Staging (F0–F4) | YOLO26s-cls (5-stage METAVIR classification) | `weights/fibrosis/yolo26s_fibrosis_cls_best.pt` |
| [`train_yolo26_steatosis_cls.py`](file:///Users/king_phuripol/AI-Engineer/01_Projects/Aong-Task/SmartMed/New-SmartLiva/tools/train_yolo26_steatosis_cls.py) | Hepatic Steatosis Staging (S0–S3) | YOLO26s-cls (4-stage fatty liver classification) | `weights/steatosis/yolo26s_steatosis_cls_best.pt` |
| [`train_yolo26_liver_prompt.py`](file:///Users/king_phuripol/AI-Engineer/01_Projects/Aong-Task/SmartMed/New-SmartLiva/tools/train_yolo26_liver_prompt.py) | Anatomical Liver Prompter | YOLO26n (Generates Bounding Box prompt for MedSAM2) | `weights/liver_prompt/yolo26n_liver.pt` |
| [`train_fibrosis_ensemble.py`](file:///Users/king_phuripol/AI-Engineer/01_Projects/Aong-Task/SmartMed/New-SmartLiva/tools/train_fibrosis_ensemble.py) | FibrosisNet 5-Fold Ensemble | ResNet-18 / ConvNeXt with grouped cross-validation | `weights/fibrosis/fibrosis_ensemble.pt` |
| [`train_medsam2.py`](file:///Users/king_phuripol/AI-Engineer/01_Projects/Aong-Task/SmartMed/New-SmartLiva/tools/train_medsam2.py) | MedSAM2 Fine-Tuning | Fine-tunes MedSAM2 decoder with bounding box prompts | `weights/medsam2/MedSAM2_latest.pt` |
| [`train_lesion_pipeline.py`](file:///Users/king_phuripol/AI-Engineer/01_Projects/Aong-Task/SmartMed/New-SmartLiva/tools/train_lesion_pipeline.py) | End-to-End Lesion Pipeline | Orchestrates dataset preparation and lesion model training | `weights/lesion/` |
| [`train_yolo_liver.py`](file:///Users/king_phuripol/AI-Engineer/01_Projects/Aong-Task/SmartMed/New-SmartLiva/tools/train_yolo_liver.py) | YOLOv8 Liver Detection | YOLOv8n Bounding Box Prompter | `weights/liver_prompt/` |
| [`SmartLiva_YOLO26_Training_Colab.ipynb`](file:///Users/king_phuripol/AI-Engineer/01_Projects/Aong-Task/SmartMed/New-SmartLiva/tools/SmartLiva_YOLO26_Training_Colab.ipynb) | Google Colab Free GPU Notebook | Free T4/A100 training script for YOLO26 models | Export zip packages |

### Example Execution
```bash
# Train YOLO26s Focal Lesion Detector on Apple Silicon GPU
python tools/train_yolo26_lesion_detection.py

# Train YOLO26s Steatosis Classifier (S0–S3)
python tools/train_yolo26_steatosis_cls.py
```

---

## 2. 📦 Dataset Preparation & Export

| Script | Purpose |
| :--- | :--- |
| [`export_colab_datasets.py`](file:///Users/king_phuripol/AI-Engineer/01_Projects/Aong-Task/SmartMed/New-SmartLiva/tools/export_colab_datasets.py) | Packages and exports dataset zips (`lesion_yolo_train.zip`, `fibrosis_yolo_cls.zip`) for Google Colab training |
| [`extract_fatty_dataset.py`](file:///Users/king_phuripol/AI-Engineer/01_Projects/Aong-Task/SmartMed/New-SmartLiva/tools/extract_fatty_dataset.py) | Extracts MATLAB B-mode ultrasound (.mat) into S0–S3 PNG frames with patient metadata |
| [`prep_and_train_lesion.py`](file:///Users/king_phuripol/AI-Engineer/01_Projects/Aong-Task/SmartMed/New-SmartLiva/tools/prep_and_train_lesion.py) | Pairs 14,000+ raw ultrasound images with annotations and sets up YOLO directory structure |
| [`prep_yolo_liver.py`](file:///Users/king_phuripol/AI-Engineer/01_Projects/Aong-Task/SmartMed/New-SmartLiva/tools/prep_yolo_liver.py) | Generates bounding boxes from liver segmentation masks for prompt training |
| [`patient_split_auditor.py`](file:///Users/king_phuripol/AI-Engineer/01_Projects/Aong-Task/SmartMed/New-SmartLiva/tools/patient_split_auditor.py) | Audits zero-leakage patient-stratified partitions (saves to `data/patient_split.json`) |
| [`download_medsam2.py`](file:///Users/king_phuripol/AI-Engineer/01_Projects/Aong-Task/SmartMed/New-SmartLiva/tools/download_medsam2.py) | Downloads MedSAM2 model checkpoints from official Hugging Face / GitHub release |

---

## 3. 🧪 Evaluation & Clinical Benchmarks

| Script | Purpose |
| :--- | :--- |
| [`test_integration.py`](file:///Users/king_phuripol/AI-Engineer/01_Projects/Aong-Task/SmartMed/New-SmartLiva/tools/test_integration.py) | **Full System Integration Test Suite** (14 automated tests verifying all endpoints and guardrails) |
| [`test_gatekeeper_harness.py`](file:///Users/king_phuripol/AI-Engineer/01_Projects/Aong-Task/SmartMed/New-SmartLiva/tools/test_gatekeeper_harness.py) | Tests 10-class Organ Gatekeeper & non-ultrasound rejection accuracy |
| [`build_clinical_benchmarks.py`](file:///Users/king_phuripol/AI-Engineer/01_Projects/Aong-Task/SmartMed/New-SmartLiva/tools/build_clinical_benchmarks.py) | Generates standardized benchmark cases with ground-truth clinical data |
| [`eval_comprehensive_all_diseases.py`](file:///Users/king_phuripol/AI-Engineer/01_Projects/Aong-Task/SmartMed/New-SmartLiva/tools/eval_comprehensive_all_diseases.py) | Evaluates end-to-end performance across Normal, Fatty Liver, Fibrosis, and Lesions |
| [`eval_medsam2.py`](file:///Users/king_phuripol/AI-Engineer/01_Projects/Aong-Task/SmartMed/New-SmartLiva/tools/eval_medsam2.py) | Computes Dice score, IoU, and boundary accuracy for MedSAM2 liver segmentation |
| [`eval_multiview.py`](file:///Users/king_phuripol/AI-Engineer/01_Projects/Aong-Task/SmartMed/New-SmartLiva/tools/eval_multiview.py) | Multi-view ultrasound evaluation (Subcostal, Intercostal, Sagittal, Oblique) |
| [`eval_cases.py`](file:///Users/king_phuripol/AI-Engineer/01_Projects/Aong-Task/SmartMed/New-SmartLiva/tools/eval_cases.py) | Evaluates single and batch test cases with visual outputs |
| [`compare_models.py`](file:///Users/king_phuripol/AI-Engineer/01_Projects/Aong-Task/SmartMed/New-SmartLiva/tools/compare_models.py) | Side-by-side benchmark comparison (YOLO26 vs. UNet vs. MedSAM2) |
| [`test_medsam2_inference.py`](file:///Users/king_phuripol/AI-Engineer/01_Projects/Aong-Task/SmartMed/New-SmartLiva/tools/test_medsam2_inference.py) | Quick sanity test for MedSAM2 standalone inference |
| [`test_real_dataset.py`](file:///Users/king_phuripol/AI-Engineer/01_Projects/Aong-Task/SmartMed/New-SmartLiva/tools/test_real_dataset.py) | Runs inference on local real-world ultrasound datasets |
| [`run_full_clinical_test_suite.py`](file:///Users/king_phuripol/AI-Engineer/01_Projects/Aong-Task/SmartMed/New-SmartLiva/tools/run_full_clinical_test_suite.py) | Comprehensive clinical acceptance testing across all test cases |
| [`batch_infer.py`](file:///Users/king_phuripol/AI-Engineer/01_Projects/Aong-Task/SmartMed/New-SmartLiva/tools/batch_infer.py) | High-throughput batch inference utility for directory of images |
| [`shadow_study_manager.py`](file:///Users/king_phuripol/AI-Engineer/01_Projects/Aong-Task/SmartMed/New-SmartLiva/tools/shadow_study_manager.py) | Manages clinical shadow study workflows and feedback collection metrics |

### Run Integration Tests
```bash
python tools/test_integration.py
```

---

## 4. 📄 Clinical & IP Report Generators

| Script | Purpose | Output File |
| :--- | :--- | :--- |
| [`generate_ip_disclosure_report.py`](file:///Users/king_phuripol/AI-Engineer/01_Projects/Aong-Task/SmartMed/New-SmartLiva/tools/generate_ip_disclosure_report.py) | Generates Intellectual Property (IP) & Patent Technical Disclosure in Thai | `reports/SmartLiva_IP_Technical_Disclosure_TH.docx` |
| [`generate_training_progress_report.py`](file:///Users/king_phuripol/AI-Engineer/01_Projects/Aong-Task/SmartMed/New-SmartLiva/tools/generate_training_progress_report.py) | Generates comprehensive model training and clinical validation progress report | `reports/SmartLiva_Dataset_Training_Report_TH_Final.docx` |
| [`add_steatosis_to_progress_report.py`](file:///Users/king_phuripol/AI-Engineer/01_Projects/Aong-Task/SmartMed/New-SmartLiva/tools/add_steatosis_to_progress_report.py) | Appends Steatosis (S0–S3) experimental metrics to clinical report | `reports/SmartLiva_Dataset_Training_Report_TH_Updated.docx` |
