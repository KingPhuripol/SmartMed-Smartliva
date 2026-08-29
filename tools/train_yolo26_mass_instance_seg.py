"""Train YOLO26s-seg Tumor / Mass Instance Segmentation Model.

Reads ground-truth tumor polygon coordinates from data/7272660 JSON annotations
and trains YOLO26s-seg for pixel-accurate tumor boundary segmentation.
"""

import json
import os
import shutil
import random
from pathlib import Path
import cv2
import yaml
from ultralytics import YOLO

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DATA_DIR = BASE_DIR / "data" / "7272660"
SEG_DATASET_DIR = RAW_DATA_DIR / "yolo_seg_dataset"
OUTPUT_WEIGHTS_DIR = BASE_DIR / "weights" / "lesion"


def prepare_seg_dataset(split_ratio: float = 0.80, seed: int = 42) -> Path:
    print("📁 Preparing YOLO26-seg Mass Instance Segmentation Dataset...")
    random.seed(seed)

    categories = [
        ("Benign", 0, RAW_DATA_DIR / "Benign" / "Benign"),
        ("Malignant", 1, RAW_DATA_DIR / "Malignant" / "Malignant"),
    ]

    all_samples = []

    for cat_name, class_id, base_cat_dir in categories:
        img_dir = base_cat_dir / "image"
        mask_dir = base_cat_dir / "segmentation" / "mass"

        if not img_dir.exists() or not mask_dir.exists():
            print(f"⚠️ Warning: Missing directory for {cat_name}: {base_cat_dir}")
            continue

        for json_path in sorted(mask_dir.glob("*.json")):
            img_path = img_dir / f"{json_path.stem}.jpg"
            if not img_path.exists():
                img_candidates = list(img_dir.glob(f"{json_path.stem}.*"))
                if img_candidates:
                    img_path = img_candidates[0]
                else:
                    continue

            try:
                img = cv2.imread(str(img_path))
                if img is None:
                    continue
                h, w = img.shape[:2]

                with open(json_path, "r", encoding="utf-8") as f:
                    pts = json.load(f)

                if not isinstance(pts, list) or len(pts) < 3:
                    continue

                norm_pts = []
                for pt in pts:
                    if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                        x, y = pt[0], pt[1]
                        norm_pts.extend([round(x / w, 5), round(y / h, 5)])

                if len(norm_pts) >= 6:
                    all_samples.append((img_path, class_id, norm_pts))
            except Exception as err:
                print(f"Error reading {json_path}: {err}")

    random.shuffle(all_samples)
    n_train = int(len(all_samples) * split_ratio)
    train_samples = all_samples[:n_train]
    val_samples = all_samples[n_train:]

    print(f"   Total Mass Cases with Polygons: {len(all_samples)}")
    print(f"   • Train: {len(train_samples)}")
    print(f"   • Val:   {len(val_samples)}")

    # Prepare directories
    if SEG_DATASET_DIR.exists():
        shutil.rmtree(SEG_DATASET_DIR)

    for split in ["train", "val"]:
        (SEG_DATASET_DIR / "images" / split).mkdir(parents=True, exist_ok=True)
        (SEG_DATASET_DIR / "labels" / split).mkdir(parents=True, exist_ok=True)

    def write_split(samples, split_name):
        for img_p, cls_id, poly in samples:
            dst_img = SEG_DATASET_DIR / "images" / split_name / img_p.name
            dst_lbl = SEG_DATASET_DIR / "labels" / split_name / f"{img_p.stem}.txt"
            shutil.copy(img_p, dst_img)

            with open(dst_lbl, "w", encoding="utf-8") as f:
                line = f"{cls_id} " + " ".join(map(str, poly)) + "\n"
                f.write(line)

    write_split(train_samples, "train")
    write_split(val_samples, "val")

    # Generate yaml
    dataset_yaml = {
        "path": str(SEG_DATASET_DIR.resolve()),
        "train": "images/train",
        "val": "images/val",
        "names": {
            0: "Benign_Mass",
            1: "Malignant_Mass",
        },
    }

    yaml_file = SEG_DATASET_DIR / "dataset.yaml"
    with open(yaml_file, "w", encoding="utf-8") as f:
        yaml.dump(dataset_yaml, f, default_flow_style=False)

    print(f"✅ Prepared dataset yaml: {yaml_file}")
    return yaml_file


def train_mass_segmenter(epochs: int = 35, imgsz: int = 512, batch: int = 16):
    print("=" * 65)
    print(" 🏥 SMARTLIVA: TRAINING YOLO26s-seg TUMOR INSTANCE SEGMENTATION")
    print("=" * 65)

    yaml_file = prepare_seg_dataset()

    # Load pretrained YOLO26s-seg
    pretrained_pt = BASE_DIR / "weights" / "pretrained" / "yolo26s-seg.pt"
    base_weights = str(pretrained_pt) if pretrained_pt.exists() else "yolo26s-seg.pt"
    model = YOLO(base_weights)

    # Train
    results = model.train(
        data=str(yaml_file),
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        device="mps",
        project=str(BASE_DIR / "runs" / "mass_seg"),
        name="yolo26s_mass_seg",
        exist_ok=True,
        verbose=True,
    )

    # Save best weights
    best_pt = BASE_DIR / "runs" / "mass_seg" / "yolo26s_mass_seg" / "weights" / "best.pt"
    if best_pt.exists():
        OUTPUT_WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
        dest_pt = OUTPUT_WEIGHTS_DIR / "yolo26s_mass_seg_best.pt"
        shutil.copy(best_pt, dest_pt)
        print(f"\n🎉 Successfully trained & saved YOLO26s-seg Mass Model to:")
        print(f"   -> {dest_pt}")
    else:
        print(f"⚠️ Warning: {best_pt} not found.")


if __name__ == "__main__":
    train_mass_segmenter()
