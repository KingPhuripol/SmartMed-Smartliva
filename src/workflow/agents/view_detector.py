"""Ultrasound Scanning View Detector Agent."""

import numpy as np
from src.workflow.schemas import ViewDetectionInfo


async def detect_view(img_bgr: np.ndarray, user_provided_view: str = None) -> ViewDetectionInfo:
    """Detect or confirm the ultrasound scan view (e.g. RH, GBH, LHA, LHP, SPH, LHV, FPH)."""
    if user_provided_view:
        return ViewDetectionInfo(
            detected_view=user_provided_view,
            confidence=0.95,
        )

    return ViewDetectionInfo(
        detected_view="Unknown/Not Confident",
        confidence=0.40,
    )
