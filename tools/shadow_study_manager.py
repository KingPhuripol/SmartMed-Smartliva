"""SmartLiva Stage 2: Pilot Shadow Study & Flywheel Manager.

Enables clinical teams and AI engineers to:
1. Run automated shadow-mode batch evaluation on clinical ultrasound cases.
2. Calculate Doctor-AI Concordance Rates (% Agreement) on Fibrosis, Steatosis, and Lesions.
3. Inspect Flywheel feedback logs stored in SQLite.
4. Export high-quality doctor-audited training datasets for model calibration & fine-tuning.
"""

import argparse
import datetime
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.config import FLYWHEEL_DB_PATH
from src.database.flywheel import get_feedback_history, init_db


def show_flywheel_summary():
    """Print an executive statistical summary of all doctor audit feedback."""
    init_db()
    conn = sqlite3.connect(str(FLYWHEEL_DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM feedback_log")
    total_reviews = cursor.fetchone()[0]

    cursor.execute("SELECT * FROM feedback_log ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()

    print("=" * 70)
    print(" 🏥 SMARTLIVA PILOT SHADOW STUDY — DOCTOR AUDIT SUMMARY")
    print("=" * 70)
    print(f" Total Audited Studies in Flywheel DB: {total_reviews}")
    print(f" Database Path: {FLYWHEEL_DB_PATH}")

    if total_reviews == 0:
        print("\n [!] No clinical feedback records found yet.")
        print("     Doctors can start reviewing cases in the web UI at http://localhost:8000")
        return

    confirmed_count = 0
    modified_count = 0
    agent_stats = {"fibrosis": {"ok": 0, "mod": 0}, "steatosis": {"ok": 0, "mod": 0}, "lesion": {"ok": 0, "mod": 0}, "fluke": {"ok": 0, "mod": 0}}

    for r in rows:
        verdicts_str = r["verdicts"]
        if verdicts_str:
            try:
                v_dict = json.loads(verdicts_str)
                for agent_id, v in v_dict.items():
                    status = v.get("status") if isinstance(v, dict) else v
                    target_key = agent_id if agent_id in agent_stats else None
                    if target_key:
                        if status in ("confirmed", "approved", "ok"):
                            agent_stats[target_key]["ok"] += 1
                            confirmed_count += 1
                        elif status in ("modified", "corrected", "rejected"):
                            agent_stats[target_key]["mod"] += 1
                            modified_count += 1
            except Exception:
                pass

    total_decisions = confirmed_count + modified_count
    overall_concordance = (confirmed_count / total_decisions * 100) if total_decisions > 0 else 0.0

    print(f"\n 📊 Overall Doctor-AI Concordance Rate: {overall_concordance:.1f}% ({confirmed_count}/{total_decisions} decisions agreed)")
    print("-" * 70)
    print(" Breakdown by Specialist Agent:")
    for agent_id, stats in agent_stats.items():
        total_a = stats["ok"] + stats["mod"]
        acc_a = (stats["ok"] / total_a * 100) if total_a > 0 else 0.0
        bar = "█" * int(acc_a // 10) + "░" * (10 - int(acc_a // 10))
        print(f"  • {agent_id.upper():<10} | [{bar}] {acc_a:>5.1f}% Agreement ({stats['ok']} Confirmed, {stats['mod']} Adjusted)")

    print("\n Recent 5 Doctor Reviews:")
    for i, r in enumerate(rows[:5], 1):
        ts = r["timestamp"][:19].replace("T", " ")
        fn = r["filename"] or "-"
        sid = r["study_id"] or "-"
        print(f"  [{i}] Study: {sid} | File: {fn:<22} | Time: {ts}")

    print("=" * 70)


def export_flywheel_dataset(output_json: str = "flywheel_training_export.json"):
    """Export audited records into structured JSON format for retraining/calibration."""
    init_db()
    conn = sqlite3.connect(str(FLYWHEEL_DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM feedback_log ORDER BY id ASC")
    rows = cursor.fetchall()
    conn.close()

    export_data = []
    for r in rows:
        item = {
            "id": r["id"],
            "study_id": r["study_id"],
            "filename": r["filename"],
            "timestamp": r["timestamp"],
            "image_path": r["image_path"],
            "verdicts": json.loads(r["verdicts"]) if r["verdicts"] else {},
            "annotations": json.loads(r["annotations"]) if r["annotations"] else [],
            "events": json.loads(r["events"]) if r["events"] else [],
            "doctor_note": r["doctor_note"],
        }
        export_data.append(item)

    out_path = BASE_DIR / output_json
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(export_data, f, ensure_ascii=False, indent=2)

    print(f"✅ Exported {len(export_data)} doctor-audited records to: {out_path}")


def main():
    parser = argparse.ArgumentParser(description="SmartLiva Pilot Shadow Study Manager")
    parser.add_argument("--summary", action="store_true", help="Display Flywheel stats and doctor agreement rate")
    parser.add_argument("--export", type=str, nargs="?", const="flywheel_dataset.json", help="Export audited datasets to JSON")
    args = parser.parse_args()

    if args.export:
        export_flywheel_dataset(args.export)
    else:
        show_flywheel_summary()


if __name__ == "__main__":
    main()
