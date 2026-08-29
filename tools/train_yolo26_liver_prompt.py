"""Train YOLO26n Liver Bounding Box Prompter for MedSAM2."""

from pathlib import Path
import shutil
from ultralytics import YOLO

BASE_DIR = Path(__file__).resolve().parent.parent
YAML_PATH = BASE_DIR / "data" / "yolo_liver_dataset" / "dataset.yaml"
OUTPUT_WEIGHTS_DIR = BASE_DIR / "weights" / "liver_prompt"


def main():
    print("=" * 65)
    print(" 🏥 SMARTLIVA: TRAINING YOLO26n LIVER BOUNDING BOX PROMPTER")
    print("=" * 65)

    # 1. Load pretrained YOLO26n
    pretrained_pt = BASE_DIR / "weights" / "pretrained" / "yolo26n.pt"
    base_weights = str(pretrained_pt) if pretrained_pt.exists() else "yolo26n.pt"
    model = YOLO(base_weights)

    # 2. Train on Liver Bounding Box dataset
    results = model.train(
        data=str(YAML_PATH),
        epochs=30,
        imgsz=640,
        batch=16,
        device="mps",  # Apple Silicon MPS GPU acceleration
        project=str(BASE_DIR / "runs" / "liver_prompt"),
        name="yolo26n_liver",
        exist_ok=True,
        verbose=True,
    )

    # 3. Export best weights to centralized weights directory
    best_pt = BASE_DIR / "runs" / "liver_prompt" / "yolo26n_liver" / "weights" / "best.pt"
    if best_pt.exists():
        OUTPUT_WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
        dest_yolo26 = OUTPUT_WEIGHTS_DIR / "yolo26n_liver.pt"
        dest_legacy = OUTPUT_WEIGHTS_DIR / "yolov8n_liver.pt"
        shutil.copy(best_pt, dest_yolo26)
        shutil.copy(best_pt, dest_legacy)
        print(f"\n🎉 Successfully trained & saved YOLO26n Liver Prompter to:")
        print(f"   -> {dest_yolo26}")
        print(f"   -> {dest_legacy} (legacy compatibility copy)")
    else:
        print(f"⚠️ Warning: {best_pt} not found.")


if __name__ == "__main__":
    main()
