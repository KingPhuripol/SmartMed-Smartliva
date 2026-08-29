"""Centralized configuration, paths, and constants for SmartLiva."""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional
import torch

# Base project root directory
BASE_DIR: Path = Path(__file__).resolve().parent.parent

# Third-party dependencies
THIRD_PARTY_DIR: Path = BASE_DIR / "third_party"
MEDSAM2_DIR: Path = THIRD_PARTY_DIR / "MedSAM2"

# Centralized Model Checkpoints (Weights)
WEIGHTS_DIR: Path = BASE_DIR / "weights"
PRETRAINED_WEIGHTS_DIR: Path = WEIGHTS_DIR / "pretrained"
MEDSAM_CKPT: Path = WEIGHTS_DIR / "medsam2" / "MedSAM2_latest.pt"
MEDSAM_CFG: str = "configs/sam2.1_hiera_t512.yaml"
YOLO_LESION_PATH: Path = WEIGHTS_DIR / "lesion" / "yolov8_lesion_best.pt"
MASS_SEG_WEIGHTS_PATH: Path = WEIGHTS_DIR / "lesion" / "yolo26s_mass_seg_best.pt"
YOLO_LIVER_PATH: Path = WEIGHTS_DIR / "liver_prompt" / "yolov8n_liver.pt"
YOLO26_LIVER_PATH: Path = WEIGHTS_DIR / "liver_prompt" / "yolo26n_liver.pt"
MULTIORGAN_SDK_PATH: Path = WEIGHTS_DIR / "multiorgan" / "multiorgan_best.pt"
FIBROSIS_ENSEMBLE_PATH: Path = WEIGHTS_DIR / "fibrosis" / "fibrosis_ensemble.pt"
STEATOSIS_WEIGHTS_PATH: Path = WEIGHTS_DIR / "steatosis" / "yolo26s_steatosis_cls_best.pt"
ORGAN_WEIGHTS_PATH: Path = WEIGHTS_DIR / "organ_gate" / "organ_best.pt"
ORGAN_LABELS_PATH: Path = WEIGHTS_DIR / "organ_gate" / "labels.json"
ORGAN_METRICS_PATH: Path = WEIGHTS_DIR / "organ_gate" / "metrics_organ.json"
QUALITY_ENVELOPES_PATH: Path = BASE_DIR / "src" / "models" / "gate" / "quality_envelopes.json"

# Data & Flywheel Paths
DATA_DIR: Path = BASE_DIR / "data"
PATIENT_SPLIT_PATH: Path = DATA_DIR / "patient_split.json"
SAMPLES_DIR: Path = DATA_DIR.resolve()
SAMPLE_EXTENSIONS: frozenset = frozenset({".jpg", ".jpeg", ".png", ".bmp"})
FLYWHEEL_DIR: Path = DATA_DIR / "flywheel"
FLYWHEEL_DB_PATH: Path = FLYWHEEL_DIR / "flywheel.db"

# Static & Frontend Distribution
FRONTEND_DIST_DIR: Path = BASE_DIR / "frontend" / "dist"
STATIC_DIR: Path = FRONTEND_DIST_DIR if FRONTEND_DIST_DIR.exists() else (BASE_DIR / "public")
REPORTS_DIR: Path = BASE_DIR / "reports"
FIBROSIS_METRICS_PATH: Path = BASE_DIR / "src" / "models" / "fibrosis" / "reports" / "metrics.json"
FIBROSIS_VERDICT_PATH: Path = BASE_DIR / "src" / "models" / "fibrosis" / "reports" / "verdict.json"

# Lesion Classes Definition
LESION_CLASSES: Dict[int, str] = {
    0: "FFC",         # Focal Fatty Change
    1: "FFS",         # Focal Fatty Sparing
    2: "HCC",         # Hepatocellular Carcinoma
    3: "Cyst",        # Simple Cyst
    4: "Hemangioma",   # Cavernous Hemangioma
    5: "Dysplastic",  # Dysplastic Nodule
    6: "CCA"          # Cholangiocarcinoma
}

# Clinical Caveat & Explanation
ESTIMATE_CAVEAT: str = (
    "ค่า kPa ด้านล่างเป็นคะแนนที่ถูกบีบเข้าหาค่ากลาง ไม่ใช่ค่าที่วัดได้จริง "
    "จากการทดสอบ ผู้ป่วยตับแข็ง (ค่าจริงเฉลี่ย 15.1 kPa) ถูกประเมินเฉลี่ยเพียง 6.0 kPa "
    "ระยะ F0–F4 ที่ไฮไลต์ใช้เกณฑ์ที่ปรับค่าตามสัดส่วนที่พบจริง (prevalence-matched) เพื่อชดเชยการบีบตัวนี้ "
    "วัดจาก 730 exams ได้ quadratic kappa 0.37 และจับผู้ป่วยตับแข็งได้ประมาณ 35% "
    "จึงยังพลาด F4 เกินครึ่ง และต้องอ่าน 'ระดับความเสี่ยง' ด้านบนเป็นหลัก"
)

logger = logging.getLogger("SmartLiva.Config")


def get_device() -> torch.device:
    """Return available torch device (MPS, CUDA, or CPU)."""
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def load_fibrosis_verdict() -> Optional[Dict[str, Any]]:
    """Read the negative-control verdict written by shortcut_probe.py, if available."""
    if not FIBROSIS_VERDICT_PATH.exists():
        return None
    try:
        return json.loads(FIBROSIS_VERDICT_PATH.read_text(encoding="utf-8"))
    except Exception as err:
        logger.warning(f"Could not read fibrosis verdict: {err}")
        return None


def build_verdict_sentence(verdict: Optional[Dict[str, Any]]) -> str:
    """State the negative-control outcome in the caveat."""
    if not verdict or not verdict.get("controls"):
        return " ยังไม่ได้ตรวจ negative control สำหรับผลนี้"

    tightest = min(verdict["controls"], key=lambda c: c.get("delta_ci_low", float("-inf")))
    margin: str = (
        f"ผลต่าง {tightest['delta']:+.3f} (95% CI {tightest['delta_ci_low']:+.3f}"
        f"–{tightest['delta_ci_high']:+.3f}) เทียบกับ {tightest['run']}"
    )
    if verdict.get("passed"):
        return f" ผ่านการตรวจ negative control ทุกตัว โดยกรณีที่คับที่สุดคือ {margin}."
    return (
        f" ยังไม่ผ่านการตรวจ negative control: คะแนนยังแยกไม่ออกทางสถิติจากอินพุตที่ไม่มีข้อมูลเนื้อตับ "
        f"({margin}) จึงควรใช้เป็นการจัดลำดับความเสี่ยงเท่านั้น ไม่ใช่ผลระดับพังผืด."
    )


def build_confidence_note() -> str:
    """Compose the user-facing caveat from measured metrics."""
    fallback: str = (
        "ผลประเมินนี้เป็นการคาดการณ์จากภาพ B-mode เทียบกับค่า elastography (ไม่ใช่ผลชิ้นเนื้อ) "
        "ใช้ประกอบการพิจารณาเท่านั้น ไม่ใช่การวินิจฉัย"
    )
    verdict_sentence: str = build_verdict_sentence(load_fibrosis_verdict())
    if not FIBROSIS_METRICS_PATH.exists():
        return fallback + verdict_sentence

    try:
        metrics: Dict[str, Any] = json.loads(FIBROSIS_METRICS_PATH.read_text(encoding="utf-8"))
        runs = [r for name, r in metrics.items() if not name.startswith("B") and not name.startswith("probe")]
        if not runs:
            return fallback + verdict_sentence
        best = max(runs, key=lambda r: r["summary"]["endpoints"]["ge_f2"]["auroc"]["mean"])
        auroc = best["summary"]["endpoints"]["ge_f2"]["auroc"]["mean"]
        interval = best["bootstrap_ci_subject_level"]["ge_f2"]
        return (
            f"วัดผลแบบ grouped cross-validation {best['n_folds']} folds บน {best['n_exams_pooled']} exams: "
            f"AUROC สำหรับพังผืดระดับ ≥F2 = {auroc:.2f} "
            f"(95% CI {interval['auroc_ci_low']:.2f}–{interval['auroc_ci_high']:.2f}). "
            + fallback
            + verdict_sentence
        )
    except Exception as err:
        logger.warning(f"Could not read fibrosis metrics: {err}")
        return fallback + verdict_sentence
