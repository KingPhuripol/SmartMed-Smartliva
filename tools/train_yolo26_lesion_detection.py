"""Train YOLO26s 7-Class Focal Liver Lesion Detector.

Supported Classes:
0: Hemangioma, 1: Cyst, 2: Calcification, 3: Metastasis, 4: HCC, 5: CCA, 6: FFC
"""

import os
import shutil
from pathlib import Path
import yaml
from ultralytics import YOLO

BASE_DIR = Path(__file__).resolve().parent.parent
YAML_PATH = BASE_DIR / "data" / "lesion_yolo_train" / "dataset.yaml"
OUTPUT_WEIGHTS_DIR = BASE_DIR / "weights" / "lesion"


def train_lesion_detector(epochs: int = 40, imgsz: int = 512, batch: int = 32):
    print("=" * 65)
    print(" 🏥 SMARTLIVA: TRAINING YOLO26s FOCAL LESION DETECTOR (7 CLASSES)")
    print("=" * 65)

    last_ckpt = BASE_DIR / "runs" / "lesion_train" / "yolo26s_lesion_local" / "weights" / "last.pt"
    if last_ckpt.exists():
        print(f"🔄 Resuming training from checkpoint: {last_ckpt}")
        model = YOLO(str(last_ckpt))
        results = model.train(resume=True)
    else:
        # 1. Load pretrained YOLO26s
        pretrained_pt = BASE_DIR / "weights" / "pretrained" / "yolo26s.pt"
        base_weights = str(pretrained_pt) if pretrained_pt.exists() else "yolo26s.pt"
        model = YOLO(base_weights)

        # 2. Train on paired lesion ultrasound dataset
        results = model.train(
            data=str(YAML_PATH),
            epochs=epochs,
            imgsz=imgsz,
            batch=batch,
            device="mps",
            project=str(BASE_DIR / "runs" / "lesion_train"),
            name="yolo26s_lesion_local",
            degrees=10.0,
            translate=0.10,
            scale=0.15,
            fliplr=0.5,
            flipud=0.0,
            mosaic=0.5,
            mixup=0.1,
            hsv_h=0.015,
            hsv_s=0.2,
            hsv_v=0.3,
            patience=15,
            exist_ok=True,
            verbose=True,
        )

    # 3. Export best model
    best_pt = BASE_DIR / "runs" / "lesion_train" / "yolo26s_lesion_local" / "weights" / "best.pt"
    if best_pt.exists():
        OUTPUT_WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
        dest_yolo26 = OUTPUT_WEIGHTS_DIR / "yolo26s_lesion_best.pt"
        dest_legacy = OUTPUT_WEIGHTS_DIR / "yolov8_lesion_best.pt"
        shutil.copy(best_pt, dest_yolo26)
        shutil.copy(best_pt, dest_legacy)
        print(f"\n🎉 Successfully trained & deployed YOLO26s Lesion Detector to:")
        print(f"   -> {dest_yolo26}")
        print(f"   -> {dest_legacy} (legacy fallback copy)")
    else:
        print(f"⚠️ Warning: {best_pt} not found.")


if __name__ == "__main__":
    train_lesion_detector()
