# 🏥 SmartLiva AI Model Weights Catalog

This directory stores deep learning checkpoints and base pretrained models for the SmartLiva clinical ultrasound AI pipeline.

---

## 🗂️ Checkpoint Organization

```text
weights/
├── pretrained/          <- Pretrained base models for training initialization
│   ├── yolo26n.pt       <- YOLO26 Nano base weights
│   ├── yolo26s.pt       <- YOLO26 Small base detection weights
│   ├── yolo26s-cls.pt   <- YOLO26 Small base classification weights
│   ├── yolo26s-seg.pt   <- YOLO26 Small base instance segmentation weights
│   └── yolov8n.pt       <- YOLOv8 Nano base weights
├── organ_gate/          <- Organ Gatekeeper (10-Class Organ Classifier)
│   ├── organ_best.pt    <- ResNet-18 10-Class Organ Classifier weights
│   ├── labels.json      <- Class mapping index
│   └── metrics_organ.json <- Validation metrics & per-class F1 scores
├── liver_prompt/        <- Anatomical Liver Bounding Box Prompter
│   ├── yolo26n_liver.pt <- YOLO26n fine-tuned liver bounding box prompter
│   └── yolov8n_liver.pt <- YOLOv8n liver bounding box prompter
├── medsam2/             <- MedSAM2 Foundation Segmenter
│   └── MedSAM2_latest.pt <- Segment Anything 2 (SAM2) ViT adapted for medical ultrasound
├── multiorgan/          <- Multi-Organ UNet
│   └── multiorgan_best.pt <- 4-level UNet for simultaneous Liver & Gallbladder segmentation
├── fibrosis/            <- Liver Fibrosis Staging (F0–F4)
│   ├── fibrosis_ensemble.pt <- 5-Fold ResNet-18 / ConvNeXt grouped ensemble
│   └── yolo26s_fibrosis_cls_best.pt <- YOLO26s-cls 5-stage METAVIR classifier
├── steatosis/           <- Hepatic Steatosis Staging (S0–S3)
│   └── yolo26s_steatosis_cls_best.pt <- YOLO26s-cls 4-stage fatty liver classifier
├── lesion/              <- Focal Liver Lesion Analytics
│   ├── yolov8_lesion_best.pt <- YOLO 7-class focal lesion detector
│   └── yolo26s_mass_seg_best.pt <- YOLO26s-seg tumor instance segmentation
└── archive/             <- Bundled archive distribution packages
    └── smartliva_weights.zip <- Full weights bundle archive
```

---

## 📊 Model Specifications

| Subfolder | Model Name | Architecture | Input Size | Task / Output Classes | Checkpoint File |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`organ_gate/`** | Organ Gatekeeper | ResNet-18 | 224x224 | 10 Organs (Liver, Gallbladder, Kidney, Spleen, Heart, Thyroid, Breast, Bladder, Non-US, etc.) | `organ_best.pt` |
| **`liver_prompt/`** | Liver Prompter | YOLO26n / YOLOv8n | 640x640 | Anatomical Liver Bounding Box | `yolo26n_liver.pt` / `yolov8n_liver.pt` |
| **`medsam2/`** | MedSAM2 | SAM2 Hiera-T | 512x512 | Zero-shot / Few-shot Pixel-level Liver Contour | `MedSAM2_latest.pt` |
| **`multiorgan/`** | Multi-Organ UNet | 4-Level UNet | 256x256 | Dual Mask (Liver tissue + Gallbladder) with mutual exclusion | `multiorgan_best.pt` |
| **`fibrosis/`** | FibrosisNet Ensemble | 5-Fold ResNet18 | 224x224 | METAVIR Staging (F0, F1, F2, F3, F4) + kPa Stiffness | `fibrosis_ensemble.pt` |
| **`steatosis/`** | Steatosis Classifier | YOLO26s-cls | 448x448 | Fatty Liver Staging (S0: Normal, S1: Mild, S2: Moderate, S3: Severe) | `yolo26s_steatosis_cls_best.pt` |
| **`lesion/`** | Lesion Detector | YOLOv8 / YOLO26s | 512x512 | 7 Focal Lesions (Hemangioma, Cyst, Calcification, Metastasis, HCC, CCA, FFC) | `yolov8_lesion_best.pt` |
| **`lesion/`** | Mass Segmenter | YOLO26s-seg | 512x512 | Pixel-accurate tumor boundary instance segmentation | `yolo26s_mass_seg_best.pt` |

---

## 🔒 Security & Deployment Notes

* Checkpoints are automatically loaded on server boot via [`src/config.py`](file:///Users/king_phuripol/AI-Engineer/01_Projects/Aong-Task/SmartMed/New-SmartLiva/src/config.py) and [`src/api/server.py`](file:///Users/king_phuripol/AI-Engineer/01_Projects/Aong-Task/SmartMed/New-SmartLiva/src/api/server.py).
* In containerized / cloud deployment (Docker, GCP Cloud Run), weights can be mounted via persistent volume or pulled from secure object storage during startup.
