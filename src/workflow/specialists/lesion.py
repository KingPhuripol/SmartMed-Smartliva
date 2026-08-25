"""Focal Lesion Detection Specialist.

Executes YOLOv8 7-Class Focal Lesion Detection and generates:
- LesionFindings linked to visual Region bounding boxes (normalized 0..1 coordinates).
- Inside/outside liver verification.
- Descriptive clinical rationale.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from src.config import LESION_CLASSES
from src.workflow.schemas import LesionInfo

logger = logging.getLogger("SmartLiva.Specialists.Lesion")


def evaluate_lesions(
    yolo_lesion_model: Any,
    img_bgr: np.ndarray,
    mask: np.ndarray,
    conf_thres: float = 0.25,
) -> Dict[str, Any]:
    """Execute YOLOv8 Lesion Detection and construct findings & Region structures."""
    if yolo_lesion_model is None:
        return {
            "findings": [],
            "regions": [],
            "confidence": 0.95,
            "rationale": "โมเดลตรวจจับรอยโรคยังไม่พร้อมใช้งาน",
            "simulated": False,
        }

    try:
        h, w = img_bgr.shape[:2]
        results = yolo_lesion_model.predict(img_bgr, conf=conf_thres, verbose=False)[0]
        lesion_names = results.names

        boxes = []
        for b in results.boxes:
            x1, y1, x2, y2 = b.xyxy[0].tolist()
            boxes.append((int(x1), int(y1), int(x2), int(y2), float(b.conf[0]), int(b.cls[0])))

        findings = []
        regions = []
        lesion_infos = []
        has_low_conf = False

        for idx, (x1, y1, x2, y2, conf, cls_id) in enumerate(boxes):
            if conf < 0.60:
                has_low_conf = True

            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            inside = bool(0 <= cy < h and 0 <= cx < w and mask[cy, cx] == 1)

            class_name = LESION_CLASSES.get(
                int(cls_id), lesion_names.get(int(cls_id), f"Class {cls_id}")
            )

            # Approximate physical size if assumed ~0.35 mm/px
            width_px = x2 - x1
            height_px = y2 - y1
            size_mm = round(max(width_px, height_px) * 0.35, 1)

            region_id = f"les-region-{idx + 1:02d}"
            finding_id = f"les-{idx + 1:02d}"

            # Normalized bounding box coordinates [[x1, y1], [x2, y2]]
            nx1 = max(0.0, min(1.0, x1 / w))
            ny1 = max(0.0, min(1.0, y1 / h))
            nx2 = max(0.0, min(1.0, x2 / w))
            ny2 = max(0.0, min(1.0, y2 / h))

            region = {
                "regionId": region_id,
                "shape": "box",
                "points": [[round(nx1, 4), round(ny1, 4)], [round(nx2, 4), round(ny2, 4)]],
                "label": class_name,
                "confidence": round(conf, 4),
                "source": "lesion",
            }
            regions.append(region)

            finding = {
                "findingId": finding_id,
                "label": class_name,
                "confidence": round(conf, 4),
                "regionId": region_id,
                "sizeMm": size_mm,
                "note": "พบในขอบเขตตับ" if inside else "อยู่นอกขอบเขตตับ",
            }
            findings.append(finding)

            lesion_infos.append(
                LesionInfo(
                    **{
                        "class": class_name,
                        "confidence": round(conf, 4),
                        "bbox": [x1, y1, x2, y2],
                        "inside_liver": inside,
                    }
                )
            )

        if len(findings) == 0:
            top_conf = 0.95
            rationale = "ไม่พบรอยโรคเฉพาะที่ (No focal liver lesion detected) เนื้อตับสม่ำเสมอ"
        else:
            top_conf = max(f["confidence"] for f in findings)
            summary_list = [f"{f['label']} (มั่นใจ {f['confidence']*100:.0f}%)" for f in findings]
            rationale = f"ตรวจพบรอยโรคเฉพาะที่ {len(findings)} ตำแหน่ง: {', '.join(summary_list)}"

        return {
            "findings": findings,
            "regions": regions,
            "lesion_infos": lesion_infos,
            "confidence": round(top_conf, 4),
            "has_low_confidence": has_low_conf,
            "rationale": rationale,
            "simulated": False,
        }

    except Exception as err:
        logger.error(f"Lesion detection failed: {err}")
        return {
            "findings": [],
            "regions": [],
            "lesion_infos": [],
            "confidence": 0.50,
            "has_low_confidence": True,
            "rationale": f"เกิดข้อผิดพลาดในการตรวจจับรอยโรค: {err}",
            "simulated": False,
        }


async def run_lesion_block(
    yolo_lesion_model: Any,
    img_bgr: np.ndarray,
    mask: np.ndarray,
    conf_thres: float = 0.25,
) -> Tuple[List[LesionInfo], bool]:
    """Legacy compatibility wrapper returning LesionInfo list & low_conf flag."""
    eval_res = evaluate_lesions(yolo_lesion_model, img_bgr, mask, conf_thres)
    return eval_res["lesion_infos"], eval_res["has_low_confidence"]
