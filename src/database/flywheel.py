"""Flywheel SQLite Database Manager for collecting clinician feedback and training datasets."""

import base64
import datetime
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from src.config import BASE_DIR, FLYWHEEL_DB_PATH, FLYWHEEL_DIR
from src.workflow.schemas import FeedbackRequest

logger = logging.getLogger("SmartLiva.Flywheel")


def init_db() -> None:
    """Initialize the SQLite database for clinician feedback & training flywheel with auto-migration."""
    FLYWHEEL_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(FLYWHEEL_DB_PATH))
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS feedback_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            study_id TEXT,
            filename TEXT,
            timestamp DATETIME,
            image_path TEXT,
            verdicts TEXT,
            annotations TEXT,
            events TEXT,
            raw_payload TEXT,
            status TEXT,
            doctor_note TEXT,
            doctor_label TEXT
        )
    """)

    # Safe migration: ensure all columns exist
    cursor.execute("PRAGMA table_info(feedback_log)")
    existing_cols = {row[1] for row in cursor.fetchall()}
    desired_cols = {
        "study_id": "TEXT",
        "verdicts": "TEXT",
        "annotations": "TEXT",
        "events": "TEXT",
        "raw_payload": "TEXT",
    }
    for col, col_type in desired_cols.items():
        if col not in existing_cols:
            cursor.execute(f"ALTER TABLE feedback_log ADD COLUMN {col} {col_type}")

    conn.commit()
    conn.close()


def save_feedback(payload: Union[FeedbackRequest, Dict[str, Any]]) -> Dict[str, Any]:
    """Save doctor feedback and training data into disk and SQLite database."""
    init_db()
    timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    # If payload is a dict from React TrainingFeedbackRecord
    if isinstance(payload, dict):
        study_id = payload.get("studyId", f"SL-{timestamp_str}")
        intake = payload.get("intake", {})
        filename = intake.get("fileName") or payload.get("filename") or "ultrasound.png"
        review = payload.get("review", {})
        verdicts = review.get("verdicts", {})
        annotations = review.get("annotations", [])
        events = review.get("events", [])

        # Check if original image data URL or blob is present
        image_source = intake.get("source") or payload.get("original_image") or ""
        saved_img_rel = ""
        if image_source and image_source.startswith("data:image"):
            try:
                b64_data = image_source.split(",")[1]
                clean_filename = filename.replace("/", "_").replace("\\", "_")
                safe_name = f"{timestamp_str}_{clean_filename}"
                img_path = FLYWHEEL_DIR / safe_name
                with open(img_path, "wb") as f:
                    f.write(base64.b64decode(b64_data))
                saved_img_rel = str(img_path.relative_to(BASE_DIR))
            except Exception as e:
                logger.warning(f"Could not save base64 image: {e}")

        conn = sqlite3.connect(str(FLYWHEEL_DB_PATH))
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO feedback_log 
               (study_id, filename, timestamp, image_path, verdicts, annotations, events, raw_payload, status, doctor_note, doctor_label) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                study_id,
                filename,
                datetime.datetime.now().isoformat(),
                saved_img_rel,
                json.dumps(verdicts, ensure_ascii=False),
                json.dumps(annotations, ensure_ascii=False),
                json.dumps(events, ensure_ascii=False),
                json.dumps(payload, ensure_ascii=False),
                "reviewed",
                "",
                json.dumps(verdicts, ensure_ascii=False),
            ),
        )
        record_id = cursor.lastrowid
        conn.commit()
        conn.close()

        logger.info(f"Saved Training Feedback for Study {study_id} (ID: {record_id})")
        return {"success": True, "record_id": record_id, "study_id": study_id}

    # Legacy FeedbackRequest
    safe_filename = payload.filename.replace("/", "_").replace("\\", "_")
    image_save_name = f"{timestamp_str}_{safe_filename}"
    image_path: Path = FLYWHEEL_DIR / image_save_name

    b64_data = payload.original_image
    if "," in b64_data:
        b64_data = b64_data.split(",")[1]

    with open(image_path, "wb") as f:
        f.write(base64.b64decode(b64_data))

    conn = sqlite3.connect(str(FLYWHEEL_DB_PATH))
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO feedback_log 
           (study_id, filename, timestamp, image_path, verdicts, annotations, events, raw_payload, status, doctor_note, doctor_label) 
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            f"SL-{timestamp_str}",
            payload.filename,
            datetime.datetime.now().isoformat(),
            str(image_path.relative_to(BASE_DIR)),
            None,
            None,
            None,
            json.dumps(payload.model_dump() if hasattr(payload, "model_dump") else payload, ensure_ascii=False),
            payload.status,
            payload.doctor_note,
            json.dumps(payload.doctor_label, ensure_ascii=False) if payload.doctor_label else None,
        ),
    )
    record_id = cursor.lastrowid
    conn.commit()
    conn.close()

    logger.info(f"Flywheel Feedback Saved: {payload.status} for {payload.filename}")
    return {"success": True, "record_id": record_id, "image_path": str(image_path)}


def get_feedback_history(limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieve recent feedback records from the database."""
    init_db()
    conn = sqlite3.connect(str(FLYWHEEL_DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM feedback_log ORDER BY id DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]
