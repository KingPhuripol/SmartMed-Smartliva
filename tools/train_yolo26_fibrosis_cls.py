"""Train YOLO26s-cls 5-Stage Liver Fibrosis Classifier (METAVIR F0–F4).

Features:
1. Zero Cross-Patient Leakage via Subject/Patient-Level Stratified Partitioning.
2. 1,772 ultrasound images across 528 patients.
3. Classes: F0, F1, F2, F3, F4.
4. Auto-exports trained best checkpoint to weights/fibrosis/yolo26s_fibrosis_cls_best.pt.
"""

import os
import shutil
from pathlib import Path
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from ultralytics import YOLO

BASE_DIR = Path(__file__).resolve().parent.parent
FIBROSIS_DATA_DIR = BASE_DIR / "data" / "liver-fibrosis-severity-prediction"
TRAIN_CSV = FIBROSIS_DATA_DIR / "train.csv"
RAW_IMG_DIR = FIBROSIS_DATA_DIR / "images" / "images"
CLS_DATASET_DIR = FIBROSIS_DATA_DIR / "yolo_cls_dataset"
OUTPUT_WEIGHTS_DIR = BASE_DIR / "weights" / "fibrosis"


def prepare_fibrosis_cls_dataset(test_size: float = 0.20, seed: int = 42) -> Path:
    print("📁 Preparing Patient-Stratified Fibrosis (F0–F4) Classification Dataset...")
    df = pd.read_csv(TRAIN_CSV)
    
    # Standardize stage labels (F0, F1, F2, F3, F4)
    df["stage"] = df["TE result"].astype(str).str.strip()
    valid_stages = {"F0", "F1", "F2", "F3", "F4"}
    df = df[df["stage"].isin(valid_stages)].copy()
    
    # Get dominant stage per patient for stratification
    patient_df = df.groupby("subject")["stage"].agg(lambda x: x.mode()[0]).reset_index()
    
    train_subjects, val_subjects = train_test_split(
        patient_df["subject"].values,
        test_size=test_size,
        random_state=seed,
        stratify=patient_df["stage"].values,
    )
    
    train_subj_set = set(train_subjects)
    print(f"   Total Unique Patients: {len(patient_df)}")
    print(f"   • Train Patients: {len(train_subjects)}")
    print(f"   • Val Patients:   {len(val_subjects)}")
    
    # Recreate directory
    if CLS_DATASET_DIR.exists():
        shutil.rmtree(CLS_DATASET_DIR)
        
    for split in ["train", "val"]:
        for stage in sorted(valid_stages):
            (CLS_DATASET_DIR / split / stage).mkdir(parents=True, exist_ok=True)
            
    train_count, val_count = 0, 0
    
    for _, row in df.iterrows():
        subj = row["subject"]
        img_name = str(row["image_name"])
        stage = str(row["stage"])
        
        # Locate source image (.png / .jpg)
        src_candidates = [
            RAW_IMG_DIR / f"{img_name}.png",
            RAW_IMG_DIR / f"{img_name}.jpg",
            RAW_IMG_DIR / img_name,
        ]
        src_img = next((c for c in src_candidates if c.exists()), None)
        if src_img is None:
            continue
            
        split = "train" if subj in train_subj_set else "val"
        dest_img = CLS_DATASET_DIR / split / stage / src_img.name
        
        try:
            os.symlink(src_img.resolve(), dest_img)
        except Exception:
            shutil.copy2(src_img, dest_img)
            
        if split == "train":
            train_count += 1
        else:
            val_count += 1
            
    print(f"✅ Prepared Fibrosis Classification dataset at: {CLS_DATASET_DIR}")
    print(f"   • Train Frames: {train_count}")
    print(f"   • Val Frames:   {val_count}")
    return CLS_DATASET_DIR


def train_fibrosis_classifier(epochs: int = 40, imgsz: int = 448, batch: int = 32):
    print("=" * 65)
    print(" 🏥 SMARTLIVA: TRAINING YOLO26s-cls FIBROSIS (F0–F4) CLASSIFIER")
    print("=" * 65)
    
    dataset_dir = prepare_fibrosis_cls_dataset()
    
    # Load pretrained YOLO26s-cls
    pretrained_pt = BASE_DIR / "weights" / "pretrained" / "yolo26s-cls.pt"
    base_weights = str(pretrained_pt) if pretrained_pt.exists() else "yolo26s-cls.pt"
    model = YOLO(base_weights)
    
    # Train
    results = model.train(
        data=str(dataset_dir),
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        device="mps",
        project=str(BASE_DIR / "runs" / "fibrosis_cls"),
        name="yolo26s_fibrosis",
        exist_ok=True,
        verbose=True,
    )
    
    # Save best weights
    best_pt = BASE_DIR / "runs" / "fibrosis_cls" / "yolo26s_fibrosis" / "weights" / "best.pt"
    if best_pt.exists():
        OUTPUT_WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
        dest_pt = OUTPUT_WEIGHTS_DIR / "yolo26s_fibrosis_cls_best.pt"
        shutil.copy(best_pt, dest_pt)
        print(f"\n🎉 Successfully trained & saved YOLO26s-cls Fibrosis Model to:")
        print(f"   -> {dest_pt}")
    else:
        print(f"⚠️ Warning: {best_pt} not found.")


if __name__ == "__main__":
    train_fibrosis_classifier()
