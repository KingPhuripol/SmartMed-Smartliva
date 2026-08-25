"""seg_contour.py — Extract liver and gallbladder contours and polygon coordinates.

Model: UNet (base=32) 3 classes: background / liver / gallbladder
Supports:
  - Mask prediction
  - Contour polygon extraction (smooth closed curves)
  - Region formatting for frontend overlay
"""

import argparse
import glob
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import cv2
import numpy as np
from PIL import Image
import torch

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

try:
    from src.config import MULTIORGAN_SDK_PATH
    SEG_WEIGHTS = MULTIORGAN_SDK_PATH if MULTIORGAN_SDK_PATH.exists() else HERE.parent.parent.parent / "weights" / "multiorgan" / "multiorgan_best.pt"
except ImportError:
    SEG_WEIGHTS = HERE.parent.parent.parent / "weights" / "multiorgan" / "multiorgan_best.pt"

from .unet import UNet

SEG_CLASSES = ["background", "liver", "gallbladder"]
LIVER, GALLBLADDER = 1, 2
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], np.float32)
SEG_SIZE = 256

OUTLINE = {LIVER: (69, 75, 230), GALLBLADDER: (87, 200, 46)}
NAME = {LIVER: "liver", GALLBLADDER: "gallbladder"}
_MODEL: Optional[torch.nn.Module] = None


def device() -> torch.device:
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def load_seg(dev: Optional[torch.device] = None) -> torch.nn.Module:
    global _MODEL
    if _MODEL is None:
        dev = dev or device()
        m = UNet(len(SEG_CLASSES), base=32)
        m.load_state_dict(torch.load(str(SEG_WEIGHTS), map_location=dev))
        _MODEL = m.to(dev).eval()
    return _MODEL


def _ensure_pil(path_or_img: Union[str, Path, Image.Image, np.ndarray]) -> Image.Image:
    if isinstance(path_or_img, Image.Image):
        return path_or_img.convert("RGB")
    if isinstance(path_or_img, np.ndarray):
        if path_or_img.ndim == 2:
            return Image.fromarray(path_or_img).convert("RGB")
        if path_or_img.shape[2] == 3 and path_or_img.dtype == np.uint8:
            return Image.fromarray(cv2.cvtColor(path_or_img, cv2.COLOR_BGR2RGB))
        return Image.fromarray(path_or_img).convert("RGB")
    return Image.open(str(path_or_img)).convert("RGB")


def fan_mask(img_rgb: Image.Image, thr: int = 10) -> np.ndarray:
    """Find the ultrasound fan area to suppress false positives in black borders."""
    g = np.asarray(img_rgb.convert("L"))
    m = (g > thr).astype("uint8")
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((5, 5), "uint8"))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, 8)
    if n <= 1:
        return np.ones_like(m)
    biggest = 1 + int(stats[1:, cv2.CC_STAT_AREA].argmax())
    fan = (lab == biggest).astype("uint8")
    fan = cv2.morphologyEx(fan, cv2.MORPH_CLOSE, np.ones((25, 25), "uint8"))
    return cv2.morphologyEx(fan, cv2.MORPH_DILATE, np.ones((5, 5), "uint8"))


def predict_mask(
    path_or_img: Union[str, Path, Image.Image, np.ndarray],
    dev: Optional[torch.device] = None,
    use_fan: bool = True,
) -> np.ndarray:
    """Return a multi-class mask matching original image dimensions (0=bg, 1=liver, 2=gallbladder)."""
    dev = dev or device()
    img = _ensure_pil(path_or_img)
    W, H = img.size
    x = np.asarray(img.resize((SEG_SIZE, SEG_SIZE)), np.float32)
    x = ((x / 255.0 - IMAGENET_MEAN) / IMAGENET_STD).transpose(2, 0, 1).astype(np.float32)
    with torch.no_grad():
        pm = load_seg(dev)(torch.from_numpy(x)[None].to(dev)).argmax(1)[0].cpu().numpy().astype(np.uint8)
    pm = np.asarray(Image.fromarray(pm).resize((W, H), Image.NEAREST))
    return pm * fan_mask(img) if use_fan else pm


def smooth_closed(pts: np.ndarray, k: int) -> np.ndarray:
    """Smooth closed polygon points."""
    if k < 3 or len(pts) < k:
        return pts
    if k % 2 == 0:
        k += 1
    pad = k // 2
    ext = np.concatenate([pts[-pad:], pts, pts[:pad]], 0).astype(np.float64)
    ker = np.ones(k) / k
    return np.stack([
        np.convolve(ext[:, 0], ker, "valid"),
        np.convolve(ext[:, 1], ker, "valid"),
    ], axis=1)


def contours_for(
    mask: np.ndarray,
    cls: int,
    min_area_frac: float = 0.002,
    smooth: int = 7,
    epsilon_frac: float = 0.001,
) -> List[Dict[str, Any]]:
    """Extract outer contours and holes for a given class."""
    binm = (mask == cls).astype(np.uint8)
    if binm.sum() == 0:
        return []
    binm = cv2.morphologyEx(binm, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    cnts, hier = cv2.findContours(binm, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    if not cnts or hier is None:
        return []
    H, W = mask.shape
    min_area = min_area_frac * H * W
    hier = hier[0]
    out = []
    for i, c in enumerate(cnts):
        if hier[i][3] != -1 or cv2.contourArea(c) < min_area:
            continue
        holes = [
            cnts[j]
            for j in range(len(cnts))
            if hier[j][3] == i and cv2.contourArea(cnts[j]) >= min_area
        ]

        def finish(cc: np.ndarray) -> np.ndarray:
            p = smooth_closed(cc[:, 0, :].astype(np.float64), smooth)
            if epsilon_frac > 0:
                q = p.astype(np.float32)[:, None, :]
                p = cv2.approxPolyDP(q, epsilon_frac * cv2.arcLength(q, True), True)[:, 0, :]
            return np.clip(p, [0, 0], [W - 1, H - 1])

        outer_pts = finish(c)
        hole_pts = [finish(h) for h in holes]
        area = float(cv2.contourArea(c) - sum(cv2.contourArea(h) for h in holes))
        out.append({
            "outer": outer_pts,
            "holes": hole_pts,
            "area_px": area,
            "perimeter_px": float(cv2.arcLength(c, True)),
        })
    out.sort(key=lambda d: -d["area_px"])
    return out


def contour_of(
    path_or_img: Union[str, Path, Image.Image, np.ndarray],
    classes: Tuple[int, ...] = (LIVER, GALLBLADDER),
    use_fan: bool = True,
    **kw: Any,
) -> Dict[str, List[Dict[str, Any]]]:
    """Return contour dictionaries for specified classes."""
    img = _ensure_pil(path_or_img)
    pm = predict_mask(img, use_fan=use_fan)
    r = {NAME[c]: contours_for(pm, c, **kw) for c in classes if c in NAME}
    return {k: v for k, v in r.items() if v}


def to_json(
    res: Dict[str, List[Dict[str, Any]]],
    img_name: str,
    W: int,
    H: int,
) -> Dict[str, Any]:
    blob: Dict[str, Any] = {
        "image": os.path.basename(img_name),
        "width": W,
        "height": H,
        "classes": {},
    }
    for name, polys in res.items():
        blob["classes"][name] = [
            {
                "outer": [[round(float(x), 1), round(float(y), 1)] for x, y in p["outer"]],
                "holes": [
                    [[round(float(x), 1), round(float(y), 1)] for x, y in h]
                    for h in p["holes"]
                ],
                "n_points": len(p["outer"]),
                "area_px": round(p["area_px"], 1),
                "area_pct_frame": round(100 * p["area_px"] / (W * H), 2),
                "perimeter_px": round(p["perimeter_px"], 1),
            }
            for p in polys
        ]
    return blob


def draw(
    img_rgb: Image.Image,
    res: Dict[str, List[Dict[str, Any]]],
    thickness: int = 2,
    dim: float = 0.25,
) -> np.ndarray:
    """Draw overlay contour lines on image."""
    canvas = cv2.cvtColor(np.asarray(img_rgb), cv2.COLOR_RGB2BGR).astype(np.float32)
    canvas = (canvas * (1 - dim)).astype(np.uint8)
    inv = {v: k for k, v in NAME.items()}
    for name, polys in res.items():
        col = OUTLINE.get(inv.get(name, 1), (69, 75, 230))
        for p in polys:
            cv2.polylines(canvas, [p["outer"].astype(np.int32)], True, col, thickness, cv2.LINE_AA)
            for h in p["holes"]:
                cv2.polylines(canvas, [h.astype(np.int32)], True, col, max(1, thickness - 1), cv2.LINE_AA)
    return cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)
