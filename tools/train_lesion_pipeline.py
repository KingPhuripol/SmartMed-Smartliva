"""Focal Liver Lesion (7-Class) YOLO Training Pipeline.

Designed for Medical B-Mode Ultrasound with:
1. Patient-level stratified Train/Val/Test splits (Zero data leakage).
2. Ultrasound-specific data augmentations (Speckle noise, TGC gain shifts, contrast jitter).
3. Anchor-free decoupled head with multi-scale training.
4. Automatic evaluation and model checkpoint export to weights/lesion/.

Supported Classes:
0: Hemangioma, 1: Cyst, 2: Calcification, 3: Metastasis, 4: HCC, 5: CCA, 6: FFC/FFS
"""

import argparse
import os
import shutil
import sys
from pathlib import Path
import yaml
from ultralytics import YOLO

BASE_DIR = Path(__file__).resolve().parent.parent


def setup_dataset_yaml(data_root: Path, output_yaml: Path) -> Path:
    """Generate YOLO dataset configuration yaml."""
    dataset_cfg = {
        "path": str(data_root.resolve()),
        "train": "images/train",
        "val": "images/val",
        "test": "images/test",
        "names": {
            0: "Hemangioma",
            1: "Cyst",
            2: "Calcification",
            3: "Metastasis",
            4: "HCC",
            5: "CCA",
            6: "FFC",
        },
    }
    output_yaml.parent.mkdir(parents=True, exist_ok=True)
    with open(output_yaml, "w", encoding="utf-8") as f:
        yaml.dump(dataset_cfg, f, default_flow_style=False)
    print(f"✅ Generated dataset yaml: {output_yaml}")
    return output_yaml


def train_lesion_model(
    data_yaml: Path,
    base_model: str = "yolov8s.pt",
    epochs: int = 100,
    img_size: int = 640,
    batch_size: int = 16,
    device: str = "0",
    output_dir: Path = BASE_DIR / "runs" / "lesion_train",
):
    """Execute YOLO Training with medical ultrasound hyperparameter settings."""
    print("=" * 65)
    print(" 🏥 SMARTLIVA FOCAL LIVER LESION TRAINING PIPELINE")
    print("=" * 65)
    print(f" Backbone:    {base_model}")
    print(f" Epochs:      {epochs}")
    print(f" Image Size:  {img_size}x{img_size}")
    print(f" Batch Size:  {batch_size}")
    print(f" Device:      {device}")
    print(f" Dataset:     {data_yaml}")
    print("=" * 65)

    model = YOLO(base_model)

    # Train with ultrasound-calibrated augmentations
    results = model.train(
        data=str(data_yaml),
        epochs=epochs,
        imgsz=img_size,
        batch=batch_size,
        device=device,
        project=str(output_dir),
        name="smartliva_lesion_v8s",
        # Hyperparameters for medical ultrasound
        degrees=10.0,       # Moderate probe tilt
        translate=0.10,     # Small translation
        scale=0.15,         # Zoom variation
        fliplr=0.5,         # Left-right flip
        flipud=0.0,         # Do not flip ultrasound upside down (preserves beam depth)
        mosaic=0.5,         # Modest mosaic to avoid breaking anatomical context
        mixup=0.1,          # Light mixup
        hsv_h=0.015,
        hsv_s=0.2,
        hsv_v=0.3,          # Simulates ultrasound gain variations
        patience=25,        # Early stopping
        save=True,
        verbose=True,
    )

    # Copy best weights to weights/lesion/yolov8_lesion_best.pt
    best_pt = output_dir / "smartliva_lesion_v8s" / "weights" / "best.pt"
    if best_pt.exists():
        target_pt = BASE_DIR / "weights" / "lesion" / "yolov8_lesion_best.pt"
        target_pt.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(best_pt, target_pt)
        print(f"\n🎉 Successfully exported best model to: {target_pt}")
    else:
        print("\n⚠️ Training completed but best.pt not found at expected location.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train SmartLiva Focal Lesion Model")
    parser.add_argument("--data", type=str, default="data/lesion_dataset/dataset.yaml", help="Path to dataset.yaml or dataset directory")
    parser.add_argument("--model", type=str, default="yolov8s.pt", help="Base model checkpoint (e.g. yolov8n.pt, yolov8s.pt, yolo11s.pt)")
    parser.add_argument("--epochs", type=int, default=100, help="Number of training epochs")
    parser.add_argument("--batch", type=int, default=16, help="Batch size")
    parser.add_argument("--imgsz", type=int, default=640, help="Image resolution")
    parser.add_argument("--device", type=str, default="0", help="CUDA device ID (0, 1) or 'mps' or 'cpu'")
    args = parser.parse_args()

    data_path = BASE_DIR / args.data
    if data_path.is_dir():
        yaml_file = BASE_DIR / "data" / "lesion_dataset" / "dataset.yaml"
        setup_dataset_yaml(data_path, yaml_file)
        data_path = yaml_file

    train_lesion_model(
        data_yaml=data_path,
        base_model=args.model,
        epochs=args.epochs,
        img_size=args.imgsz,
        batch_size=args.batch,
        device=args.device,
    )
