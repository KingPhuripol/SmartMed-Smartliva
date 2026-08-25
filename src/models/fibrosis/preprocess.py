"""Image preprocessing for fibrosis staging: fan detection, mask cleanup, ROI cropping.

Two measured properties of this dataset drive the design:

1. Burned-in vendor chrome (patient id, depth, gain, timestamps) is NOT pixel-static --
   its content changes on every image, so a static pixel mask cannot remove it. The
   only workable defence is a *geometric* crop to the ultrasound fan region.

2. Image resolution is confounded with the label (mean 5.10 kPa at 720x1000 versus
   6.75 kPa at 730x1020, F4 rate 0.0% versus 11.9%). Every input is therefore stretched
   to a fixed square without preserving aspect ratio -- preserving it would preserve the
   scanner fingerprint and hand the model a shortcut.
"""

import logging
from typing import Optional, Tuple

import cv2
import numpy as np

INPUT_MODES: Tuple[str, ...] = (
    "full",              # whole frame, chrome included -- the naive baseline
    "fan",               # geometric crop to the ultrasound sector
    "roi_bbox",          # crop to the liver mask bounding box
    "roi_masked_bbox",   # crop to the liver bbox and zero everything outside the mask
    "chrome",            # INVERSE of the fan -- negative control, must carry no signal
    "mask_only",         # binary liver mask alone, no texture -- negative control
)

logger: logging.Logger = logging.getLogger("SmartLiva.FibrosisPreprocess")


def detect_fan(
    gray: np.ndarray,
    thresh: int = 8,
    kernel: int = 15,
    shrink: float = 0.02,
) -> Tuple[int, int, int, int]:
    """Locate the ultrasound sector and return its bounding box as (x1, y1, x2, y2).

    Thresholding at a near-black level keeps the sector and the chrome text; the
    morphological opening then dissolves thin glyphs while leaving the solid sector
    intact, so the largest remaining component is the imaging area. The box is shrunk
    slightly to drop the bright rim that borders the sector on some vendors.
    """
    h, w = gray.shape[:2]

    _, binary = cv2.threshold(gray, thresh, 255, cv2.THRESH_BINARY)
    element: np.ndarray = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel, kernel))
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, element)

    n_labels, _, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    if n_labels <= 1:
        return 0, 0, w, h

    largest: int = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    x, y, bw, bh = (int(v) for v in stats[largest, :4])

    dx, dy = int(bw * shrink), int(bh * shrink)
    x1, y1 = max(x + dx, 0), max(y + dy, 0)
    x2, y2 = min(x + bw - dx, w), min(y + bh - dy, h)

    # Degenerate detection (mostly-black frame) falls back to the whole image.
    if x2 - x1 < 32 or y2 - y1 < 32:
        return 0, 0, w, h
    return x1, y1, x2, y2


def _fill_holes(binary: np.ndarray) -> np.ndarray:
    """Fill interior holes of a binary mask by flood-filling the background from the border."""
    h, w = binary.shape[:2]
    flood: np.ndarray = binary.copy()
    scratch: np.ndarray = np.zeros((h + 2, w + 2), dtype=np.uint8)
    cv2.floodFill(flood, scratch, (0, 0), 1)
    holes: np.ndarray = (flood == 0).astype(np.uint8)
    return ((binary > 0) | (holes > 0)).astype(np.uint8)


def clean_mask(mask: np.ndarray, kernel: int = 15) -> np.ndarray:
    """Close, keep the largest connected component, and fill holes in a liver mask.

    Required, not cosmetic: the U-Net masks shipped for this dataset have a median of
    2 connected components and up to 14, so speckle fragments would otherwise dominate
    the ROI bounding box.
    """
    binary: np.ndarray = (mask > 0).astype(np.uint8)
    if binary.sum() == 0:
        return binary

    element: np.ndarray = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel, kernel))
    closed: np.ndarray = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, element)

    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(closed, connectivity=8)
    if n_labels <= 1:
        return closed

    largest: int = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    return _fill_holes((labels == largest).astype(np.uint8))


def liver_roi_bbox(mask: np.ndarray, pad: float = 0.05) -> Optional[Tuple[int, int, int, int]]:
    """Return the padded bounding box (x1, y1, x2, y2) of a cleaned mask, or None if empty."""
    if mask.sum() == 0:
        return None

    h, w = mask.shape[:2]
    ys, xs = np.nonzero(mask)
    x1, x2 = int(xs.min()), int(xs.max()) + 1
    y1, y2 = int(ys.min()), int(ys.max()) + 1

    dx, dy = int((x2 - x1) * pad), int((y2 - y1) * pad)
    return max(x1 - dx, 0), max(y1 - dy, 0), min(x2 + dx, w), min(y2 + dy, h)


def apply_roi(
    gray: np.ndarray,
    mask: Optional[np.ndarray],
    mode: str = "roi_masked_bbox",
) -> np.ndarray:
    """Extract the region a model should see, according to `mode`.

    Falls back to the fan crop whenever a mask-dependent mode is requested but the mask
    is missing or empty, so a segmentation failure degrades rather than crashes.
    """
    if mode not in INPUT_MODES:
        raise ValueError(f"Unknown input mode: {mode!r}. Expected one of {INPUT_MODES}")

    if mode == "full":
        return gray

    fx1, fy1, fx2, fy2 = detect_fan(gray)

    if mode == "fan":
        return gray[fy1:fy2, fx1:fx2]

    if mode == "chrome":
        # Negative control: keep only what lies OUTSIDE the imaging sector.
        blanked: np.ndarray = gray.copy()
        blanked[fy1:fy2, fx1:fx2] = 0
        return blanked

    cleaned: Optional[np.ndarray] = clean_mask(mask) if mask is not None else None
    bbox = liver_roi_bbox(cleaned) if cleaned is not None else None
    if bbox is None:
        logger.debug("Empty or missing liver mask; falling back to fan crop.")
        return gray[fy1:fy2, fx1:fx2]

    x1, y1, x2, y2 = bbox

    if mode == "mask_only":
        # Negative control: shape without texture.
        return (cleaned[y1:y2, x1:x2] * 255).astype(np.uint8)

    if mode == "roi_bbox":
        return gray[y1:y2, x1:x2]

    masked: np.ndarray = gray * cleaned
    return masked[y1:y2, x1:x2]


def standardize(
    gray: np.ndarray,
    size: int = 256,
    clahe: bool = False,
    normalize_roi: bool = False,
) -> np.ndarray:
    """Resize to a fixed square and optionally equalize local contrast.

    The resize deliberately stretches rather than letterboxes: aspect ratio is a
    scanner fingerprint that correlates with the label in this dataset.
    `normalize_roi` additionally removes absolute gain, which is the other half of the
    same fingerprint -- enable it if the metadata-only baseline (B3) proves strong.
    """
    if gray.size == 0:
        return np.zeros((size, size), dtype=np.uint8)

    interp: int = cv2.INTER_AREA if max(gray.shape[:2]) > size else cv2.INTER_LINEAR
    out: np.ndarray = cv2.resize(gray, (size, size), interpolation=interp)

    if clahe:
        out = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(out)

    if normalize_roi:
        foreground: np.ndarray = out[out > 0]
        if foreground.size > 0:
            mean, std = float(foreground.mean()), float(foreground.std()) + 1e-6
            out = np.clip((out.astype(np.float32) - mean) / std * 48.0 + 128.0, 0, 255).astype(np.uint8)

    return out


def load_pair(img_path: str, mask_path: Optional[str] = None) -> Tuple[np.ndarray, Optional[np.ndarray]]:
    """Read a grayscale ultrasound image and its liver mask, resizing the mask to match."""
    gray: Optional[np.ndarray] = cv2.imread(str(img_path), cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise ValueError(f"Failed to read image at: {img_path}")

    if mask_path is None:
        return gray, None

    mask: Optional[np.ndarray] = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        logger.warning(f"Failed to read mask at: {mask_path}")
        return gray, None

    if mask.shape[:2] != gray.shape[:2]:
        mask = cv2.resize(mask, (gray.shape[1], gray.shape[0]), interpolation=cv2.INTER_NEAREST)

    return gray, (mask > 127).astype(np.uint8)


def preprocess_image(
    img_path: str,
    mask_path: Optional[str],
    mode: str = "roi_masked_bbox",
    size: int = 256,
    clahe: bool = False,
    normalize_roi: bool = False,
) -> np.ndarray:
    """Full path-to-tensor-ready pipeline: read, crop by `mode`, resize to `size`."""
    gray, mask = load_pair(img_path, mask_path)
    return standardize(apply_roi(gray, mask, mode), size=size, clahe=clahe, normalize_roi=normalize_roi)
