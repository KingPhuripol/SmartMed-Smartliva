"""Non-Liver Ultrasound Hard-Gating Harness & Quality Guardrail.

Enforces strict clinical validation before allowing any disease specialists
(Fibrosis, Steatosis, Lesions, Fluke) to execute.

If the image is:
1. Not an ultrasound image (e.g. general photo, text, invalid physics), OR
2. A non-liver organ (Kidney, Spleen, Heart, Thyroid, Breast, Bladder, etc.), OR
3. Uncertain organ classification (confidence < 0.55 or entropy > 1.30), OR
4. Liver segmentation coverage < 5.0% of the frame:

-> The Gatekeeper HALTS execution immediately (Hard-Stop) and produces a clean,
   explanatory clinical rejection report. Disease specialists are NEVER run on non-liver inputs.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
from PIL import Image

from src.models.gate.classify import classify, load_model as load_organ_gate_model

logger = logging.getLogger("SmartLiva.GatekeeperHarness")


ORGAN_NAMES_TH: Dict[str, str] = {
    "liver": "ตับ (Liver)",
    "gallbladder": "ถุงน้ำดี (Gallbladder)",
    "kidney": "ไต (Kidney)",
    "spleen": "ม้าม (Spleen)",
    "heart": "หัวใจ (Echocardiogram / Heart)",
    "bladder": "กระเพาะปัสสาวะ (Urinary Bladder)",
    "thyroid": "ต่อมไทรอยด์ (Thyroid)",
    "breast": "เต้านม (Breast)",
    "carotid": "หลอดเลือดคอ (Carotid Artery)",
    "other": "อวัยวะอื่นๆ (Other Organ / Non-Liver)",
}


class GatekeeperVerdict:
    def __init__(
        self,
        is_liver: bool,
        verdict: str,
        detected_organ: str,
        confidence: Optional[float],
        quality: str,
        rejection_reason: Optional[str] = None,
        top3: Optional[List[Tuple[str, float]]] = None,
        warnings: Optional[List[str]] = None,
    ):
        self.is_liver = is_liver
        self.verdict = verdict
        self.detected_organ = detected_organ
        self.confidence = confidence
        self.quality = quality
        self.rejection_reason = rejection_reason
        self.top3 = top3 or []
        self.warnings = warnings or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_liver": self.is_liver,
            "verdict": self.verdict,
            "detected_organ": self.detected_organ,
            "confidence": self.confidence,
            "quality": self.quality,
            "rejection_reason": self.rejection_reason,
            "top3": self.top3,
            "warnings": self.warnings,
        }


def run_organ_gatekeeper_harness(
    img: Union[np.ndarray, Image.Image, str],
    device: Any = None,
) -> GatekeeperVerdict:
    """Run physics quality gate and 10-class organ classifier with abstain logic."""
    try:
        gate_res = classify(img, device=device)
        
        is_liver_us = bool(gate_res.get("is_liver_us", False))
        verdict = gate_res.get("verdict", "UNCERTAIN")
        organ = gate_res.get("organ", "unknown")
        conf = gate_res.get("confidence")
        quality = gate_res.get("quality", "ACCEPT")
        top3 = gate_res.get("top3", [])
        reasons = gate_res.get("reasons", [])

        # If quality gate rejected the image
        if quality == "REJECT":
            reason_str = ", ".join(reasons) if reasons else "Physics quality envelope failed"
            return GatekeeperVerdict(
                is_liver=False,
                verdict="REJECT_NOT_ULTRASOUND",
                detected_organ="Non-Ultrasound / Poor Quality",
                confidence=conf,
                quality=quality,
                rejection_reason=f"⛔ ภาพที่อัปโหลดไม่ผ่านเกณฑ์มาตรฐานฟิสิกส์คลื่นเสียง B-mode: {reason_str}",
                top3=top3,
                warnings=[reason_str],
            )

        # If organ classification failed or abstained
        if verdict == "UNCERTAIN":
            return GatekeeperVerdict(
                is_liver=False,
                verdict="UNCERTAIN_ORGAN",
                detected_organ=organ,
                confidence=conf,
                quality=quality,
                rejection_reason="⚠️ ระบบไม่สามารถยืนยันได้ว่าเป็นภาพอัลตราซาวด์ตับ (ความเชื่อมั่นต่ำกว่าเกณฑ์ 55% หรือ Entropy สูง) โปรดตรวจสอบมุมมองภาพ",
                top3=top3,
                warnings=["Uncertain organ classification"],
            )

        # If classified as another organ
        if not is_liver_us or verdict != "liver":
            organ_th = ORGAN_NAMES_TH.get(organ, organ)
            conf_str = f"{conf * 100:.1f}%" if conf is not None else "-"
            return GatekeeperVerdict(
                is_liver=False,
                verdict=f"NON_LIVER_{organ.upper()}",
                detected_organ=organ_th,
                confidence=conf,
                quality=quality,
                rejection_reason=f"⛔ ภาพที่อัปโหลดไม่ใช่ภาพอัลตราซาวด์ตับ: ระบบตรวจพบว่าเป็น '{organ_th}' (ความมั่นใจ {conf_str}) จึงระงับการวิเคราะห์โรคตับเพื่อความปลอดภัยของผู้ป่วย",
                top3=top3,
                warnings=[f"Detected {organ} instead of liver"],
            )

        # Valid liver ultrasound
        return GatekeeperVerdict(
            is_liver=True,
            verdict="liver",
            detected_organ="Liver",
            confidence=conf,
            quality=quality,
            rejection_reason=None,
            top3=top3,
            warnings=[],
        )

    except Exception as err:
        logger.error(f"Gatekeeper harness execution failed: {err}")
        return GatekeeperVerdict(
            is_liver=False,
            verdict="GATEKEEPER_ERROR",
            detected_organ="Error",
            confidence=None,
            quality="ERROR",
            rejection_reason=f"เกิดข้อผิดพลาดในการตรวจสอบภาพ: {err}",
            top3=[],
            warnings=[str(err)],
        )
