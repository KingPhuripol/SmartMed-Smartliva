"""Anatomical morphology, masking refinement, image encoding, and anonymization."""

import base64
import cv2
import numpy as np


def cv2_to_base64(img_bgr: np.ndarray, ext: str = ".png") -> str:
    """Convert OpenCV BGR image array to Base64 data URL string."""
    success, buffer = cv2.imencode(ext, img_bgr)
    if not success:
        raise ValueError("Failed to encode image buffer to Base64.")
    b64_str: str = base64.b64encode(buffer).decode("utf-8")
    clean_ext: str = ext.lstrip(".")
    return f"data:image/{clean_ext};base64,{b64_str}"


def anonymize_ultrasound(img: np.ndarray, top_pct: float = 0.12) -> np.ndarray:
    """Black out the top portion of the ultrasound image to hide patient names and dates."""
    h = img.shape[0]
    blackout_h = int(h * top_pct)
    anonymized = img.copy()

    if len(img.shape) == 2:
        anonymized[0:blackout_h, :] = 0
    else:
        anonymized[0:blackout_h, :, :] = 0

    return anonymized


def clean_liver_mask(mask: np.ndarray, kernel_size: int = 11) -> np.ndarray:
    """Anatomical morphology refinement: close, keep largest connected component, and fill internal holes."""
    binary: np.ndarray = (mask > 0).astype(np.uint8)
    if binary.sum() == 0:
        return binary

    element: np.ndarray = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    closed: np.ndarray = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, element)

    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(closed, connectivity=8)
    if n_labels <= 1:
        return closed

    largest: int = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    primary = (labels == largest).astype(np.uint8)

    # Flood fill internal holes
    h, w = primary.shape[:2]
    flood: np.ndarray = primary.copy()
    scratch: np.ndarray = np.zeros((h + 2, w + 2), dtype=np.uint8)
    cv2.floodFill(flood, scratch, (0, 0), 1)
    holes: np.ndarray = (flood == 0).astype(np.uint8)
    return ((primary > 0) | (holes > 0)).astype(np.uint8)
