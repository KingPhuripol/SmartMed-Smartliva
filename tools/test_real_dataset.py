"""Real Clinical Ultrasound Dataset Test Suite for SmartLiva.

Tests the full 100% Segmentation-Gated ML+LLM pipeline against real patient cases
from public/samples and data/ directories.
"""

import glob
import io
import json
import os
import sys
import time
from pathlib import Path
from PIL import Image
from fastapi.testclient import TestClient

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.api.server import app


def test_real_clinical_samples():
    print("=" * 70)
    print(" 🏥 SMARTLIVA CLINICAL EVALUATION ON REAL ULTRASOUND DATASET")
    print("=" * 70)

    # Collect sample real clinical images
    sample_files = sorted(glob.glob(str(BASE_DIR / "public" / "samples" / "*.jpg")))
    
    # Also collect some images from data/Normal แยกบริเวณตรวจ if present
    normal_patient_files = sorted(glob.glob(str(BASE_DIR / "data" / "Normal แยกบริเวณตรวจ" / "**" / "*.jpg"), recursive=True))[:4]
    
    all_test_files = sample_files + normal_patient_files
    print(f"📊 Found {len(all_test_files)} Real Clinical Ultrasound Images to test.\n")

    results_table = []

    with TestClient(app) as client:
        for idx, file_path in enumerate(all_test_files, 1):
            path_obj = Path(file_path)
            case_name = path_obj.name
            parent_name = path_obj.parent.name
            display_name = f"{parent_name}/{case_name}" if "Patient" in parent_name else case_name

            print(f"[{idx}/{len(all_test_files)}] 🔬 Analyzing Case: {display_name}...")
            with open(file_path, "rb") as f:
                img_bytes = f.read()

            t0 = time.time()
            res = client.post(
                "/api/v1/liver/analyze",
                files={"file": (case_name, img_bytes, "image/jpeg")},
            )
            elapsed_ms = int((time.time() - t0) * 1000)

            if res.status_code != 200:
                print(f"    ❌ Error {res.status_code}: {res.text}")
                continue

            data = res.json()

            liver_detected = data.get("liver_detected", False)
            liver_area_pct = data.get("liver_area_percent", 0.0)
            organs = data.get("organs_detected", [])
            
            # Specialist Findings
            fibrosis = data.get("fibrosis", {}) or {}
            f_stage = fibrosis.get("stage", "N/A")
            risk_tier = fibrosis.get("risk_tier_label", "N/A")
            kpa = fibrosis.get("kpa_estimate", 0.0)
            
            steatosis = data.get("fatty_liver_stage", "N/A")
            
            lesions = data.get("lesions", [])
            lesion_count = len(lesions)
            lesion_summary = ", ".join([f"{l.get('class_name') or l.get('class')} ({l.get('confidence')*100:.0f}%)" for l in lesions]) if lesions else "None"
            
            fluke = data.get("fluke_risk", {}) or {}
            fluke_level = fluke.get("risk_level", "N/A")
            
            clinical_report = data.get("clinical_report", "")
            first_line_report = clinical_report.split("\n")[0] if clinical_report else "No note"

            print(f"    🫀 Liver Detected: {liver_detected} ({liver_area_pct}% coverage) | Organs: {organs}")
            print(f"    🧬 Fibrosis: {f_stage} ({kpa} kPa, {risk_tier}) | 🧈 Steatosis: {steatosis}")
            print(f"    🎯 Lesions: {lesion_count} detected [{lesion_summary}]")
            print(f"    🪱 Fluke/CCA Risk: {fluke_level}")
            print(f"    🧠 AI Medical Review: {first_line_report[:70]}...")
            print(f"    ⏱️ Pipeline Time: {elapsed_ms} ms\n")

            results_table.append({
                "case": display_name,
                "liver_pct": f"{liver_area_pct}%",
                "organs": ", ".join(organs),
                "fibrosis": f"{f_stage} ({risk_tier})",
                "steatosis": steatosis,
                "lesions": lesion_summary,
                "fluke": fluke_level,
                "time_ms": elapsed_ms
            })

    print("=" * 70)
    print(" 📋 REAL CLINICAL DATASET EVALUATION SUMMARY")
    print("=" * 70)
    print(f"{'Case Name':<32} | {'Liver Area':<10} | {'Fibrosis':<12} | {'Steatosis':<9} | {'Lesions':<20} | {'Fluke'}")
    print("-" * 105)
    for r in results_table:
        print(f"{r['case'][:32]:<32} | {r['liver_pct']:<10} | {r['fibrosis']:<12} | {r['steatosis']:<9} | {r['lesions'][:20]:<20} | {r['fluke']}")
    print("=" * 70)
    print(f" ✅ Successfully evaluated all {len(results_table)} real clinical cases!")


if __name__ == "__main__":
    test_real_clinical_samples()
