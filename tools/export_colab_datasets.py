"""Package datasets into clean zip archives for rapid Google Colab training.

Outputs:
- data/lesion_yolo_train.zip (Focal Lesions 7 Classes)
- data/fibrosis_yolo_cls.zip (Fibrosis METAVIR F0-F4)
"""

import os
import shutil
import zipfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"


def zip_directory(src_dir: Path, zip_path: Path):
    print(f"📦 Zipping {src_dir} -> {zip_path}...")
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(src_dir):
            for file in files:
                if file.startswith(".") or file.endswith(".cache"):
                    continue
                full_path = Path(root) / file
                rel_path = full_path.relative_to(src_dir.parent)
                zf.write(full_path, rel_path)
    size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    print(f"✅ Created {zip_path.name} ({size_mb:.2f} MB)")


def main():
    print("=" * 65)
    print(" 🏥 SMARTLIVA: PACKAGING DATASETS FOR GOOGLE COLAB")
    print("=" * 65)

    # 1. Lesion Detection Dataset
    lesion_dir = DATA_DIR / "lesion_yolo_train"
    if lesion_dir.exists():
        zip_directory(lesion_dir, DATA_DIR / "lesion_yolo_train.zip")

    # 2. Fibrosis Classification Dataset
    fibrosis_dir = DATA_DIR / "liver-fibrosis-severity-prediction" / "yolo_cls_dataset"
    if fibrosis_dir.exists():
        zip_directory(fibrosis_dir, DATA_DIR / "fibrosis_yolo_cls.zip")

    print("\n🎉 All datasets packaged successfully for Google Colab!")


if __name__ == "__main__":
    main()
