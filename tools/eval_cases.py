"""Evaluation script for SmartLiva on the 8 Real Clinical Cases."""

import glob
import io
import json
import os
import sys
import time
from pathlib import Path
from fastapi.testclient import TestClient

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.api.server import app


def evaluate_clinical_cases():
    sample_files = sorted(glob.glob(str(BASE_DIR / "public" / "samples" / "case*.jpg")))
    
    print("=" * 80)
    print(" 🏥 SMARTLIVA: REAL CLINICAL CASES EVALUATION")
    print("=" * 80)

    results = []

    with TestClient(app) as client:
        for idx, fpath in enumerate(sample_files, 1):
            fname = Path(fpath).name
            with open(fpath, "rb") as f:
                img_bytes = f.read()

            t0 = time.time()
            res = client.post(
                "/api/v1/liver/analyze",
                files={"file": (fname, img_bytes, "image/jpeg")},
            )
            elapsed = round((time.time() - t0), 2)

            if res.status_code != 200:
                print(f"[{idx}] ❌ {fname}: {res.status_code} {res.text}")
                continue

            d = res.json()
            liver_cov = f"{d.get('liver_area_percent', 0)}%"
            organs = ", ".join(d.get("organs_detected", []))
            
            fib = d.get("fibrosis", {}) or {}
            fib_str = f"{fib.get('stage', 'N/A')} ({fib.get('kpa_estimate', 0)} kPa, {fib.get('risk_tier_label', 'N/A')})"
            
            stea_str = d.get("fatty_liver_stage", "S0")
            
            lesions = d.get("lesions", [])
            les_str = ", ".join([f"{l.get('class_name') or l.get('class')} ({l.get('confidence')*100:.0f}%)" for l in lesions]) if lesions else "No lesion"
            
            fluke_str = (d.get("fluke_risk") or {}).get("risk_level", "Low")
            
            report = d.get("clinical_report", "").replace("\n", " ")
            short_rep = report[:60] + "..." if len(report) > 60 else report

            print(f"[{idx}/8] 🔬 Case: {fname}")
            print(f"      🫀 Segmentation: {liver_cov} [{organs}]")
            print(f"      🧬 Fibrosis: {fib_str}")
            print(f"      🧈 Steatosis: {stea_str}")
            print(f"      🎯 Lesions: {les_str}")
            print(f"      🪱 Fluke/CCA: {fluke_str}")
            print(f"      🧠 AI Review: {short_rep}")
            print(f"      ⏱️ Time: {elapsed}s\n")

            results.append({
                "case": fname,
                "liver_cov": liver_cov,
                "organs": organs,
                "fib": fib.get('stage', 'N/A'),
                "kpa": fib.get('kpa_estimate', 0),
                "risk": fib.get('risk_tier_label', 'N/A'),
                "stea": stea_str,
                "les": les_str,
                "fluke": fluke_str
            })

    print("=" * 95)
    print(f"{'Case':<32} | {'Liver':<7} | {'Organs':<18} | {'Fibrosis':<10} | {'Steatosis':<9} | {'Lesions':<15}")
    print("-" * 95)
    for r in results:
        print(f"{r['case']:<32} | {r['liver_cov']:<7} | {r['organs']:<18} | {r['fib']} ({r['risk']}) | {r['stea']:<9} | {r['les']}")
    print("=" * 95)


if __name__ == "__main__":
    evaluate_clinical_cases()
