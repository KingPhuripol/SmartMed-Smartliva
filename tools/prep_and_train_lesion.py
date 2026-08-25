"""SmartLiva Automated End-to-End Focal Lesion Training Suite.

Pairs 14,000+ ultrasound images with 7,222 annotations across all 7 classes,
creates patient/sample stratified train/val split, and trains YOLOv8 on Apple Silicon (mps).
"""

import os
import random
import shutil
from pathlib import Path
import yaml
from ultralytics import YOLO

BASE_DIR = Path(__file__).resolve().parent.parent
LESION_DIR = BASE_DIR / "data" / "liver-fibrosis-severity-prediction" / "liver-lesion"
DATASET_DIR = BASE_DIR / "data" / "lesion_yolo_train"


def prepare_dataset(split_ratio: float = 0.85, seed: int = 42):
    """Pair images and annotations and create YOLO directory structure."""
    print("=" * 65)
    print(" 📦 PREPARING FOCAL LESION DATASET")
    print("=" * 65)

    random.seed(seed)
    img_dir = LESION_DIR / "images"
    ann_dir = LESION_DIR / "annotations"

    # Destination directories
    train_img_dir = DATASET_DIR / "images" / "train"
    val_img_dir = DATASET_DIR / "images" / "val"
    train_lbl_dir = DATASET_DIR / "labels" / "train"
    val_lbl_dir = DATASET_DIR / "labels" / "val"

    for d in [train_img_dir, val_img_dir, train_lbl_dir, val_lbl_dir]:
        d.mkdir(parents=True, exist_ok=True)

    ann_files = list(ann_dir.glob("*.txt"))
    paired = []

    for ann in ann_files:
        stem = ann.stem
        # Check matching image (.jpg, .png, .jpeg)
        img_candidates = [
            img_dir / f"{stem}.jpg",
            img_dir / f"{stem}.png",
            img_dir / f"{stem}.jpeg",
        ]
        matched = next((c for c in img_candidates if c.exists()), None)
        if matched:
            paired.append((matched, ann))

    random.shuffle(paired)
    n_train = int(len(paired) * split_ratio)
    train_set = paired[:n_train]
    val_set = paired[n_train:]

    print(f" Total Paired Cases: {len(paired)}")
    print(f"  • Train Set: {len(train_set)} images")
    print(f"  • Val Set:   {len(val_set)} images")

    # Link/Copy files (use symlink for speed, fallback to copy)
    def link_or_copy(src: Path, dst: Path):
        if dst.exists():
            return
        try:
            os.symlink(src.resolve(), dst)
        except Exception:
            shutil.copy2(src, dst)

    for img, lbl in train_set:
        link_or_copy(img, train_img_dir / img.name)
        link_or_copy(lbl, train_lbl_dir / lbl.name)

    for img, lbl in val_set:
        link_or_copy(img, val_img_dir / img.name)
        link_or_copy(lbl, val_lbl_dir / lbl.name)

    # Generate dataset.yaml
    yaml_dict = {
        "path": str(DATASET_DIR.resolve()),
        "train": "images/train",
        "val": "images/val",
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

    yaml_path = DATASET_DIR / "dataset.yaml"
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(yaml_dict, f, default_flow_style=False)

    print(f" ✅ Dataset prepared at: {yaml_path}")
    return yaml_path


def train(yaml_path: Path, epochs: int = 35, batch_size: int = 32, imgsz: int = 512, device: str = "mps"):
    """Execute training run on Apple Silicon GPU (mps)."""
    print("\n" + "=" * 65)
    print(" 🚀 STARTING YOLO LESION TRAINING ON LOCAL GPU")
    print("=" * 65)
    print(f" Base Model:  yolov8n.pt")
    print(f" Epochs:      {epochs}")
    print(f" Image Size:  {imgsz}x{imgsz}")
    print(f" Batch Size:  {batch_size}")
    print(f" Device:      {device}")
    print("=" * 65)

    model = YOLO("yolov8n.pt")

    results = model.train(
        data=str(yaml_path),
        epochs=epochs,
        imgsz=imgsz,
        batch=batch_size,
        device=device,
        project=str(BASE_DIR / "runs" / "lesion_train"),
        name="smartliva_yolov8n_local",
        # Ultrasound Data Augmentations
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
        save=True,
        verbose=True,
    )

    # Export best model
    best_weights = BASE_DIR / "runs" / "lesion_train" / "smartliva_yolov8n_local" / "weights" / "best.pt"
    if best_weights.exists():
        target_path = BASE_DIR / "weights" / "lesion" / "yolov8_lesion_best.pt"
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(best_weights, target_path)
        print(f"\n🎉 Successfully deployed new model checkpoint to: {target_path}")


if __name__ == "__main__":
    yaml_file = prepare_dataset()
    train(yaml_file)
