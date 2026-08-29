"""Train YOLO26s-cls Steatosis Staging (S0–S3) Classification Model.

Zero Cross-Patient Leakage Guaranteed via Patient-Level Stratified Partitioning.
"""

import os
import shutil
from pathlib import Path
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from ultralytics import YOLO

BASE_DIR = Path(__file__).resolve().parent.parent
FATTY_DATA_DIR = BASE_DIR / "data" / "Fatty" / "extracted"
CLS_DATASET_DIR = BASE_DIR / "data" / "Fatty" / "yolo_cls_dataset"
OUTPUT_WEIGHTS_DIR = BASE_DIR / "weights" / "steatosis"


def prepare_classification_dataset(seed: int = 42) -> Path:
    """Prepare train/val dataset organized by class folders with zero patient leakage."""
    print("📁 Preparing Patient-Stratified Classification Dataset...")
    
    patient_summary_path = FATTY_DATA_DIR / "patient_summary.csv"
    metadata_path = FATTY_DATA_DIR / "metadata.csv"
    
    df_patients = pd.read_csv(patient_summary_path)
    df_meta = pd.read_csv(metadata_path)
    
    # Stratified split on patient level (80% train, 20% val)
    train_pids, val_pids = train_test_split(
        df_patients["patient_id"].values,
        test_size=0.20,
        random_state=seed,
        stratify=df_patients["s_stage"].values,
    )
    
    print(f"   Total Patients: {len(df_patients)}")
    print(f"   Train Patients: {len(train_pids)} ({sorted(train_pids)})")
    print(f"   Val Patients:   {len(val_pids)} ({sorted(val_pids)})")
    
    # Recreate directory
    if CLS_DATASET_DIR.exists():
        shutil.rmtree(CLS_DATASET_DIR)
        
    for split in ["train", "val"]:
        for stage in ["S0", "S1", "S2", "S3"]:
            (CLS_DATASET_DIR / split / stage).mkdir(parents=True, exist_ok=True)
            
    train_pid_set = set(train_pids)
    train_count, val_count = 0, 0
    
    for _, row in df_meta.iterrows():
        pid = int(row["patient_id"])
        stage = str(row["s_stage"])
        fname = str(row["filename"])
        src_img = FATTY_DATA_DIR / "images" / fname
        
        split = "train" if pid in train_pid_set else "val"
        dest_img = CLS_DATASET_DIR / split / stage / fname
        shutil.copy(src_img, dest_img)
        
        if split == "train":
            train_count += 1
        else:
            val_count += 1
            
    print(f"✅ Prepared YOLO-cls dataset at: {CLS_DATASET_DIR}")
    print(f"   Train Frames: {train_count}, Val Frames: {val_count}")
    return CLS_DATASET_DIR


def train_steatosis_classifier(epochs: int = 40, batch: int = 16):
    print("=" * 65)
    print(" 🏥 SMARTLIVA: TRAINING YOLO26s-cls STEATOSIS (S0–S3) CLASSIFIER")
    print("=" * 65)
    
    dataset_dir = prepare_classification_dataset()
    
    # Load pretrained YOLO26s-cls
    pretrained_pt = BASE_DIR / "weights" / "pretrained" / "yolo26s-cls.pt"
    base_weights = str(pretrained_pt) if pretrained_pt.exists() else "yolo26s-cls.pt"
    model = YOLO(base_weights)
    
    # Train
    results = model.train(
        data=str(dataset_dir),
        epochs=epochs,
        imgsz=448,
        batch=batch,
        device="mps",
        project=str(BASE_DIR / "runs" / "steatosis_cls"),
        name="yolo26s_steatosis",
        exist_ok=True,
        verbose=True,
    )
    
    # Save best weights
    best_pt = BASE_DIR / "runs" / "steatosis_cls" / "yolo26s_steatosis" / "weights" / "best.pt"
    if best_pt.exists():
        OUTPUT_WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
        dest_pt = OUTPUT_WEIGHTS_DIR / "yolo26s_steatosis_cls_best.pt"
        shutil.copy(best_pt, dest_pt)
        print(f"\n🎉 Successfully trained & saved YOLO26s-cls Steatosis Model to:")
        print(f"   -> {dest_pt}")
    else:
        print(f"⚠️ Warning: {best_pt} not found.")


if __name__ == "__main__":
    train_steatosis_classifier()
