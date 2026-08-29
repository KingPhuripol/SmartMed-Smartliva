"""Extract and organize the Hepatic Steatosis (S-Stage) Ultrasound Dataset (.mat).

Dataset Origin:
    - Byra et al. (2018), "Transfer learning with deep convolutional neural networks
      for liver steatosis assessment in ultrasound imaging", IJCARS.
    - Zenodo DOI: 10.5281/zenodo.1009146
    - MD5: c87da28a498eae0f0874408c7ac92524

Extracted Outputs:
    - data/Fatty/extracted/images/ (All 550 ultrasound frame PNGs)
    - data/Fatty/extracted/by_stage/S0..S3/ (Symlinks or copies organized by S-Stage)
    - data/Fatty/extracted/by_patient/patient_01..55/ (Frames organized by patient)
    - data/Fatty/extracted/metadata.csv (Per-image metadata)
    - data/Fatty/extracted/patient_summary.csv (Per-patient summary)
    - data/Fatty/extracted/dataset_summary.json (Overall statistics)
"""

import os
import json
import hashlib
from pathlib import Path
import cv2
import numpy as np
import pandas as pd
import scipy.io as sio


def get_s_stage(fat_pct: float) -> tuple[str, str]:
    """Classify steatosis stage based on standard clinical biopsy/fat percentage:
    - S0: Normal (< 5%)
    - S1: Mild steatosis (5% - 33%)
    - S2: Moderate steatosis (> 33% - 66%)
    - S3: Severe steatosis (> 66%)
    """
    if fat_pct < 5.0:
        return "S0", "Normal (< 5% fat)"
    elif fat_pct <= 33.0:
        return "S1", "Mild Steatosis (5-33% fat)"
    elif fat_pct <= 66.0:
        return "S2", "Moderate Steatosis (>33-66% fat)"
    else:
        return "S3", "Severe Steatosis (>66% fat)"


def extract_dataset(
    mat_path: Path = Path("/Users/king_phuripol/AI-Engineer/01_Projects/Aong-Task/SmartMed/New-SmartLiva/data/Fatty/dataset_liver_bmodes_steatosis_assessment_IJCARS.mat"),
    output_dir: Path = Path("/Users/king_phuripol/AI-Engineer/01_Projects/Aong-Task/SmartMed/New-SmartLiva/data/Fatty/extracted"),
):
    print(f"Loading .mat dataset from: {mat_path}")
    if not mat_path.exists():
        raise FileNotFoundError(f"Source file not found: {mat_path}")

    mat = sio.loadmat(str(mat_path))
    data = mat["data"]
    num_patients = data.shape[1]
    print(f"Found {num_patients} patients in dataset.")

    # Create directory tree
    images_dir = output_dir / "images"
    by_stage_dir = output_dir / "by_stage"
    by_patient_dir = output_dir / "by_patient"

    images_dir.mkdir(parents=True, exist_ok=True)
    by_stage_dir.mkdir(parents=True, exist_ok=True)
    by_patient_dir.mkdir(parents=True, exist_ok=True)

    for stage in ["S0", "S1", "S2", "S3"]:
        (by_stage_dir / stage).mkdir(parents=True, exist_ok=True)

    hashes = {}
    image_records = []
    patient_records = []

    stage_counts = {"S0": 0, "S1": 0, "S2": 0, "S3": 0}
    stage_patient_counts = {"S0": 0, "S1": 0, "S2": 0, "S3": 0}

    for i in range(num_patients):
        item = data[0, i]
        pid = int(item["id"][0][0])
        pclass = int(item["class"][0][0])
        fat_pct = float(item["fat"][0][0])
        imgs = item["images"]  # shape (10, H, W)
        num_frames = imgs.shape[0]

        stage_code, stage_desc = get_s_stage(fat_pct)
        stage_patient_counts[stage_code] += 1

        p_dir = by_patient_dir / f"patient_{pid:02d}"
        p_dir.mkdir(parents=True, exist_ok=True)

        patient_unique_frames = 0

        for f_idx in range(num_frames):
            img_arr = imgs[f_idx]
            h, w = img_arr.shape
            img_hash = hashlib.md5(img_arr.tobytes()).hexdigest()

            is_dup = img_hash in hashes
            dup_of = hashes.get(img_hash, None)
            if not is_dup:
                hashes[img_hash] = f"patient_{pid:02d}_frame_{f_idx+1:02d}"
                patient_unique_frames += 1

            stage_counts[stage_code] += 1

            # Format filename
            fname = f"P{pid:02d}_frame{f_idx+1:02d}_{stage_code}_fat{int(fat_pct):02d}pct.png"
            main_path = images_dir / fname
            stage_path = by_stage_dir / stage_code / fname
            pat_path = p_dir / f"frame_{f_idx+1:02d}.png"

            # Save PNG image
            cv2.imwrite(str(main_path), img_arr)
            cv2.imwrite(str(stage_path), img_arr)
            cv2.imwrite(str(pat_path), img_arr)

            image_records.append({
                "patient_id": pid,
                "frame_index": f_idx + 1,
                "filename": fname,
                "relative_path": str(main_path.relative_to(output_dir.parent)),
                "s_stage": stage_code,
                "s_stage_description": stage_desc,
                "fat_percentage": fat_pct,
                "class_binary": pclass,
                "class_label": "Steatosis" if pclass == 1 else "Normal/Non-Steatotic",
                "width": w,
                "height": h,
                "mean_intensity": round(float(np.mean(img_arr)), 2),
                "std_intensity": round(float(np.std(img_arr)), 2),
                "is_duplicate": is_dup,
                "duplicate_of": dup_of if is_dup else "",
                "md5_hash": img_hash,
            })

        patient_records.append({
            "patient_id": pid,
            "s_stage": stage_code,
            "s_stage_description": stage_desc,
            "fat_percentage": fat_pct,
            "class_binary": pclass,
            "class_label": "Steatosis" if pclass == 1 else "Normal/Non-Steatotic",
            "total_frames": num_frames,
            "unique_frames": patient_unique_frames,
            "duplicate_frames": num_frames - patient_unique_frames,
        })

    # Save metadata CSVs
    df_images = pd.DataFrame(image_records)
    df_patients = pd.DataFrame(patient_records)

    images_csv = output_dir / "metadata.csv"
    patients_csv = output_dir / "patient_summary.csv"

    df_images.to_csv(images_csv, index=False, encoding="utf-8-sig")
    df_patients.to_csv(patients_csv, index=False, encoding="utf-8-sig")

    # Dataset Summary JSON
    summary_data = {
        "dataset_name": "IJCARS Liver Ultrasound Steatosis Assessment Dataset",
        "citation": "Byra et al., Transfer learning with deep convolutional neural networks for liver steatosis assessment in ultrasound imaging, IJCARS 2018",
        "doi": "10.5281/zenodo.1009146",
        "total_patients": num_patients,
        "total_frames": len(image_records),
        "unique_frames": len(hashes),
        "duplicate_frames": len(image_records) - len(hashes),
        "image_resolution": [434, 636],
        "stages": {
            "S0": {
                "description": "Normal (< 5% fat)",
                "patients": stage_patient_counts["S0"],
                "frames": stage_counts["S0"],
            },
            "S1": {
                "description": "Mild Steatosis (5–33% fat)",
                "patients": stage_patient_counts["S1"],
                "frames": stage_counts["S1"],
            },
            "S2": {
                "description": "Moderate Steatosis (>33–66% fat)",
                "patients": stage_patient_counts["S2"],
                "frames": stage_counts["S2"],
            },
            "S3": {
                "description": "Severe Steatosis (>66% fat)",
                "patients": stage_patient_counts["S3"],
                "frames": stage_counts["S3"],
            },
        },
        "binary_classes": {
            "0 (Non-Steatotic)": sum(1 for p in patient_records if p["class_binary"] == 0),
            "1 (Steatotic)": sum(1 for p in patient_records if p["class_binary"] == 1),
        }
    }

    summary_json = output_dir / "dataset_summary.json"
    with open(summary_json, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2, ensure_ascii=False)

    print("\nExtraction completed successfully!")
    print(f"Total Patients: {num_patients}")
    print(f"Total Frames Extracted: {len(image_records)} (Unique: {len(hashes)})")
    print("Stage Distribution:")
    for s, c in stage_patient_counts.items():
        print(f"  {s}: {c} patients ({stage_counts[s]} frames)")
    print(f"\nFiles written:")
    print(f"  - Metadata CSV: {images_csv}")
    print(f"  - Patient Summary CSV: {patients_csv}")
    print(f"  - Dataset Summary JSON: {summary_json}")
    print(f"  - Images Directory: {images_dir}")
    print(f"  - By Stage Directory: {by_stage_dir}")
    print(f"  - By Patient Directory: {by_patient_dir}")


if __name__ == "__main__":
    extract_dataset()
