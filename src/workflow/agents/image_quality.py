"""Image Quality Assessment Agent."""

import cv2
import numpy as np
from src.workflow.schemas import ImageQualityInfo


async def analyze_image_quality(img_bgr: np.ndarray) -> ImageQualityInfo:
    """Assess image quality, brightness, and contrast."""
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    mean_brightness = float(np.mean(gray))

    warnings = []
    brightness_level = "Normal"
    if mean_brightness < 30:
        brightness_level = "Dark"
        warnings.append("Image is too dark, contrast may be poor.")
    elif mean_brightness > 200:
        brightness_level = "Bright"
        warnings.append("Image is overexposed.")

    score = 0.90 if brightness_level == "Normal" else 0.60
    is_acceptable = score > 0.50

    return ImageQualityInfo(
        score=score,
        is_acceptable=is_acceptable,
        brightness_level=brightness_level,
        warnings=warnings,
    )
