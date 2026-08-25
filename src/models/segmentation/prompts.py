"""Ultrasound cone extraction and bounding box prompt generation."""

import cv2
import numpy as np


def extract_ultrasound_cone(gray_image: np.ndarray) -> np.ndarray:
    """Extract the valid ultrasound fan/cone area to prevent mask spill-over."""
    _, thresh = cv2.threshold(gray_image, 10, 255, cv2.THRESH_BINARY)
    kernel = np.ones((15, 15), np.uint8)
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
    opened = cv2.morphologyEx(closed, cv2.MORPH_OPEN, kernel)

    contours, _ = cv2.findContours(opened, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    outline_mask = np.zeros_like(gray_image)
    if contours:
        largest_contour = max(contours, key=cv2.contourArea)
        cv2.drawContours(outline_mask, [largest_contour], -1, 1, thickness=cv2.FILLED)
    else:
        outline_mask.fill(1)

    return outline_mask
