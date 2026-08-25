"""Comprehensive Multi-Disease Clinical Evaluation Benchmark for SmartLiva.

Evaluates all 4 disease modules on real patient ultrasound scans:
1. 🫀 Multi-Organ Gated Segmentation (MedSAM2 / UNet)
2. 🧬 Fibrosis Staging (F0-F4) & kPa Stiffness (FibrosisNet 5-Fold)
3. 🧈 Steatosis / Fatty Liver (S0-S3) & Attenuation Ratio
4. 🎯 Focal Lesions (7-Class YOLOv8 Detection + Spatial Containment)
5. 🪱 Liver Fluke & Cholangiocarcinoma Risk Matrix
6. 🧠 AI Medical Reviewer & Deterministic Safety Verifier
"""

import glob
import json
import os
import sys
import time
from pathlib import Path
import cv2
import numpy as np
from fastapi.testclient import TestClient

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.api.server import app


def run_comprehensive_evaluation():
    print("=" * 105)
    print(" 🏥 SMARTLIVA: COMPREHENSIVE MULTI-DISEASE CLINICAL EVALUATION BENCHMARK")
    print("=" * 105)

    # Gather test cases
    sample_files = sorted(glob.glob(str(BASE_DIR / "public" / "samples" / "case*.jpg")))
    
    # Also include cases from data/Normal if available
    normal_files = sorted(glob.glob(str(BASE_DIR / "data" / "Normal แยกบริเวณตรวจ" / "**" / "*.jpg"), recursive=True))[:4]
    
    all_test_files = sample_files + normal_files
    print(f"📊 Total Test Cases Selected: {len(all_test_files)}")
    print("-" * 105)

    results = []

    with TestClient(app) as client:
        for idx, fpath in enumerate(all_test_files, 1):
            p = Path(fpath)
            fname = p.name
            parent_folder = p.parent.name
            display_name = f"{parent_folder}/{fname}" if "Normal" in str(p) else fname

            with open(fpath, "rb") as f:
                img_bytes = f.read()

            t0 = time.perf_counter()
            res = client.post(
                "/api/v1/liver/analyze",
                files={"file": (fname, img_bytes, "image/jpeg")},
            )
            latency_ms = round((time.perf_counter() - t0) * 1000, 1)

            if res.status_code != 200:
                print(f"[{idx:02d}] ❌ {display_name}: HTTP {res.status_code} - {res.text}")
                continue

            d = res.json()
            liver_cov = f"{d.get('liver_area_percent', 0):.1f}%"
            organs = ", ".join(d.get("organs_detected", []))
            
            # 1. Fibrosis
            fib = d.get("fibrosis") or {}
            fib_stage = fib.get("stage", "F0")
            kpa = fib.get("kpa_estimate", 0.0)
            risk_tier = fib.get("risk_tier_label", "Low")
            
            # 2. Steatosis
            stea_stage = d.get("fatty_liver_stage", "S0")
            
            # 3. Lesions
            lesions = d.get("lesions", [])
            if lesions:
                les_strs = [f"{l.get('class_name') or l.get('class')} ({l.get('confidence')*100:.0f}%, {l.get('bbox')})" for l in lesions]
                les_summary = "; ".join(les_strs)
            else:
                les_summary = "None (Homogeneous)"

            # 4. Fluke
            fluke_info = d.get("fluke_risk") or {}
            fluke_level = fluke_info.get("risk_level", "Low")

            # 5. Clinical Safety Warning
            warning = d.get("clinical_warning")
            safety = "⚠️ Warning: " + warning[:40] + "..." if warning else "✅ Normal Protocol"

            print(f"[{idx:02d}] 🔬 Case: {display_name}")
            print(f"      🫀 Segmentation: {liver_cov} | Organs: [{organs}]")
            print(f"      🧬 Fibrosis:     {fib_stage} (Stiffness: {kpa:.1f} kPa, Tier: {risk_tier})")
            print(f"      🧈 Steatosis:    {stea_stage}")
            print(f"      🎯 Lesions ({len(lesions)}): {les_summary}")
            print(f"      🪱 Fluke / CCA:  {fluke_level}")
            print(f"      🛡️ Safety:       {safety}")
            print(f"      ⏱️ Latency:      {latency_ms} ms\n")

            results.append({
                "case": display_name,
                "liver_cov": liver_cov,
                "fib_stage": fib_stage,
                "kpa": kpa,
                "risk_tier": risk_tier,
                "stea_stage": stea_stage,
                "num_lesions": len(lesions),
                "les_summary": les_summary,
                "fluke_level": fluke_level,
                "latency": latency_ms,
            })

    # Summary Statistics Table
    print("=" * 115)
    print(f"{'Case ID / Name':<30} | {'Liver Mask':<10} | {'Fibrosis':<16} | {'Steatosis':<10} | {'Lesions':<28} | {'Fluke':<8}")
    print("-" * 115)
    for r in results:
        fib_col = f"{r['fib_stage']} ({r['kpa']:.1f} kPa)"
        les_col = r['les_summary'][:28]
        print(f"{r['case']:<30} | {r['liver_cov']:<10} | {fib_col:<16} | {r['stea_stage']:<10} | {les_col:<28} | {r['fluke_level']:<8}")
    print("=" * 115)

    # Diagnostic Distribution Analysis
    print("\n📊 DIAGNOSTIC DISTRIBUTION SUMMARY:")
    fib_counts = {}
    stea_counts = {}
    total_les = sum(r["num_lesions"] for r in results)
    avg_latency = np.mean([r["latency"] for r in results]) if results else 0

    for r in results:
        fib_counts[r["fib_stage"]] = fib_counts.get(r["fib_stage"], 0) + 1
        stea_counts[r["stea_stage"]] = stea_counts.get(r["stea_stage"], 0) + 1

    print(f"  • Total Evaluated Cases:  {len(results)}")
    print(f"  • Fibrosis Breakdown:     {dict(sorted(fib_counts.items()))}")
    print(f"  • Steatosis Breakdown:    {dict(sorted(stea_counts.items()))}")
    print(f"  • Total Lesions Detected: {total_les} lesions across cases")
    print(f"  • Mean Pipeline Latency:  {avg_latency:.1f} ms / study")
    print("=" * 115)


if __name__ == "__main__":
    run_comprehensive_evaluation()
