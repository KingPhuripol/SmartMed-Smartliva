# SmartLiva AI Model Weights Directory

This directory stores the trained deep learning checkpoints for the SmartLiva clinical ultrasound AI pipeline.

---

## 🗂️ Model Structure

| Directory | Model Name | Architecture | Purpose | Checkpoint File |
| :--- | :--- | :--- | :--- | :--- |
| **`organ_gate/`** | Organ Gatekeeper | ResNet-18 (10 Classes) | B-mode physics validation & 10-organ classification | `organ_best.pt` |
| **`liver_prompt/`** | Liver BBox Prompter | YOLOv8n | Generates anatomical liver bounding box for MedSAM2 | `yolov8n_liver.pt` |
| **`medsam2/`** | MedSAM2 | SAM2 ViT | High-precision pixel-level Liver Segmentation | `MedSAM2_latest.pt` |
| **`multiorgan/`** | Multi-Organ UNet | 4-Level UNet | Dual Liver & Gallbladder Segmentation with mutual exclusion | `multiorgan_best.pt` |
| **`fibrosis/`** | FibrosisNet Ensemble | 5-Fold ResNet-18 / ConvNeXt | Liver Fibrosis Staging (F0–F4) & kPa estimation | `fibrosis_ensemble.pt` |
| **`lesion/`** | Lesion Detector | YOLOv8 (7 Classes) | Focal liver lesion detection (HCC, CCA, Hemangioma, Cyst, etc.) | `yolov8_lesion_best.pt` |

---

## 📥 Checkpoint Storage & Deployment Notes

* Large model weights (`*.pt`, `*.pth`) are tracked out-of-band to adhere to GitHub file size limits and security practices.
* In production deployment (Docker / Cloud Run / Kubernetes), weights are mounted via volume or downloaded automatically from cloud model registries during container bootstrap.
