# SmartLiva Clinical Data & Flywheel Directory

This directory stores clinical dataset structures and the SQLite Flywheel Database for doctor feedback collection.

---

## 🔒 Data Privacy & PDPA Notice

* **Patient Confidentiality (PDPA)**: Raw patient ultrasound images and identifiable DICOM metadata must never be committed to public repositories.
* Real patient ultrasound samples for UI demonstration are stored safely in `public/samples/` with full de-identification and pseudonymization.

---

## 🗄️ Directory Structure

* **`flywheel/`**: Stores `flywheel.db` (SQLite database) where physician reviews, manual overrides, bounding box annotations, and clinical rationales are logged during Stage 2 Pilot Shadow Studies.
* **`Normal แยกบริเวณตรวจ/`**: Internal local benchmark dataset (ignored by Git).
