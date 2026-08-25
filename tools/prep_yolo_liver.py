import os
import json
import shutil
from pathlib import Path
import cv2
import numpy as np
from sklearn.model_selection import train_test_split

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_ROOT = BASE_DIR / "data" / "7272660"
YOLO_DIR = BASE_DIR / "data" / "yolo_liver_dataset"

CLASSES = ("Benign", "Malignant", "Normal")

def prepare_dataset():
    # Setup directories
    for split in ["train", "val"]:
        os.makedirs(YOLO_DIR / "images" / split, exist_ok=True)
        os.makedirs(YOLO_DIR / "labels" / split, exist_ok=True)
        
    samples = []
    
    # Collect all samples
    for cls in CLASSES:
        img_dir = DATA_ROOT / cls / cls / "image"
        liver_dir = DATA_ROOT / cls / cls / "segmentation" / "liver"
        for img_path in sorted(img_dir.glob("*.jpg")):
            json_path = liver_dir / f"{img_path.stem}.json"
            if json_path.exists():
                samples.append((img_path, json_path))
                
    print(f"Found {len(samples)} valid image-mask pairs.")
    
    # Split 80/20
    train_samples, val_samples = train_test_split(samples, test_size=0.2, random_state=42)
    
    def process_split(split_samples, split_name):
        for img_path, json_path in split_samples:
            # Read image to get dimensions
            img = cv2.imread(str(img_path))
            if img is None:
                continue
            H, W = img.shape[:2]
            
            # Read JSON
            with open(json_path, "r", encoding="utf-8") as f:
                points = json.load(f)
                
            pts = np.array(points)
            min_x, min_y = np.min(pts, axis=0)
            max_x, max_y = np.max(pts, axis=0)
            
            # Clip
            min_x, max_x = max(0, min_x), min(W, max_x)
            min_y, max_y = max(0, min_y), min(H, max_y)
            
            # YOLO format
            center_x = (min_x + max_x) / 2.0 / W
            center_y = (min_y + max_y) / 2.0 / H
            width = (max_x - min_x) / W
            height = (max_y - min_y) / H
            
            # Ensure within 0-1
            center_x = np.clip(center_x, 0, 1)
            center_y = np.clip(center_y, 0, 1)
            width = np.clip(width, 0, 1)
            height = np.clip(height, 0, 1)
            
            # Save label
            label_name = f"{img_path.stem}_{img_path.parent.parent.name}.txt"
            img_name = f"{img_path.stem}_{img_path.parent.parent.name}.jpg"
            
            with open(YOLO_DIR / "labels" / split_name / label_name, "w") as f:
                f.write(f"0 {center_x:.6f} {center_y:.6f} {width:.6f} {height:.6f}\n")
                
            # Copy image
            shutil.copy(img_path, YOLO_DIR / "images" / split_name / img_name)
            
    print("Processing training set...")
    process_split(train_samples, "train")
    
    print("Processing validation set...")
    process_split(val_samples, "val")
    
    # Create dataset.yaml
    yaml_content = f"""path: {YOLO_DIR.absolute()}
train: images/train
val: images/val

names:
  0: liver
"""
    with open(YOLO_DIR / "dataset.yaml", "w") as f:
        f.write(yaml_content)
        
    print(f"Dataset preparation complete! YOLO format saved to {YOLO_DIR}")

if __name__ == "__main__":
    prepare_dataset()
