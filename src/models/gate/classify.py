"""classify.py — Organ Classifier (ResNet18, 10 Classes) & Quality Gate.

Handles:
  [1] Quality Gate: Validates B-mode ultrasound physics & signal quality.
  [2] Organ Classifier: Identifies organ (Liver, Kidney, Gallbladder, Bladder, Thyroid, etc.).
  [3] Abstain Logic: Abstains with UNCERTAIN if confidence is low or entropy is high.
"""

import argparse
import glob
import io
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import torch
import torchvision
from PIL import Image
from torchvision import transforms as T

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

try:
    from src.config import ORGAN_LABELS_PATH, ORGAN_WEIGHTS_PATH
except ImportError:
    ORGAN_WEIGHTS_PATH = HERE.parent.parent.parent / "weights" / "organ_gate" / "organ_best.pt"
    ORGAN_LABELS_PATH = HERE.parent.parent.parent / "weights" / "organ_gate" / "labels.json"

import quality_gate

MEAN = [0.485, 0.456, 0.406]
STD = [0.229, 0.224, 0.225]
_MODEL: Optional[torch.nn.Module] = None
_CLASSES: Optional[List[str]] = None

ROUTE: Dict[str, str] = {"liver": "liver_disease", "kidney": "kidney_stone"}
CONF_MIN: float = 0.55
ENTROPY_MAX: float = 1.30


def _device() -> torch.device:
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def _tf(size: int = 224) -> T.Compose:
    return T.Compose([
        T.Grayscale(num_output_channels=3),
        T.Resize((size, size)),
        T.ToTensor(),
        T.Normalize(MEAN, STD),
    ])


def load_model(device: Optional[torch.device] = None) -> Tuple[torch.nn.Module, List[str]]:
    """Load the ResNet18 10-Class Organ Classifier."""
    global _MODEL, _CLASSES
    if _MODEL is None:
        device = device or _device()
        labels_path = (
            ORGAN_LABELS_PATH
            if Path(ORGAN_LABELS_PATH).exists()
            else HERE / "labels.json"
        )
        weights_path = (
            ORGAN_WEIGHTS_PATH
            if Path(ORGAN_WEIGHTS_PATH).exists()
            else HERE / "organ_best.pt"
        )

        with open(labels_path, "r", encoding="utf-8") as fh:
            _CLASSES = json.load(fh)["classes"]

        m = torchvision.models.resnet18(weights=None)
        m.fc = torch.nn.Linear(m.fc.in_features, len(_CLASSES))
        m.load_state_dict(torch.load(str(weights_path), map_location=device))
        _MODEL = m.to(device).eval()
    return _MODEL, _CLASSES


def _probs(model: torch.nn.Module, img: Image.Image, device: torch.device) -> np.ndarray:
    x = _tf()(img)[None].to(device)
    with torch.no_grad():
        return torch.softmax(model(x), dim=1)[0].cpu().numpy()


def _ensure_pil(path_or_img: Union[str, Path, Image.Image, np.ndarray]) -> Image.Image:
    if isinstance(path_or_img, Image.Image):
        return path_or_img.convert("RGB")
    if isinstance(path_or_img, np.ndarray):
        if path_or_img.ndim == 2:
            return Image.fromarray(path_or_img).convert("RGB")
        return Image.fromarray(path_or_img).convert("RGB")
    return Image.open(str(path_or_img)).convert("RGB")


def classify(
    path_or_img: Union[str, Path, Image.Image, np.ndarray],
    device: Optional[torch.device] = None,
    filename: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute quality check + 10-organ classification + abstain logic."""
    device = device or _device()
    name = (
        filename
        or (Path(path_or_img).name if isinstance(path_or_img, (str, Path)) else "image.jpg")
    )

    # 1. Quality Assessment
    q = quality_gate.assess(path_or_img)
    if q["decision"] == "REJECT":
        v = "NOT_US" if any("physics" in r for r in q.get("reasons", [])) else "LOW_QUALITY"
        return {
            "path": name,
            "verdict": v,
            "is_liver_us": False,
            "confidence": None,
            "route": None,
            "quality": q["decision"],
            "q_score": q.get("quality"),
            "reasons": q.get("reasons"),
            "top3": [],
        }

    # 2. Organ Classification
    model, classes = load_model(device)
    img_pil = _ensure_pil(path_or_img)
    p = _probs(model, img_pil, device)
    top = int(p.argmax())
    conf = float(p[top])
    ent = float(-(p * np.log(p + 1e-9)).sum())
    organ = classes[top]

    # 3. Abstain Logic
    if conf < CONF_MIN or ent > ENTROPY_MAX:
        verdict = "UNCERTAIN"
        route = None
        is_liver = False
    else:
        verdict = organ
        route = ROUTE.get(organ)
        is_liver = organ == "liver"

    top3 = sorted(
        [(classes[i], round(float(p[i]), 3)) for i in p.argsort()[-3:][::-1]],
        key=lambda x: -x[1],
    )

    return {
        "path": name,
        "verdict": verdict,
        "is_liver_us": is_liver,
        "organ": organ,
        "confidence": round(conf, 4),
        "entropy": round(ent, 3),
        "route": route,
        "quality": q["decision"],
        "q_score": q.get("quality"),
        "reasons": q.get("reasons"),
        "top3": top3,
    }


def main():
    ap = argparse.ArgumentParser(description="Classify Ultrasound image: Quality + Organ")
    ap.add_argument("input")
    args = ap.parse_args()
    files = (
        sorted(sum([glob.glob(os.path.join(args.input, e)) for e in ("*.jpg", "*.jpeg", "*.png", "*.JPG")], []))
        if os.path.isdir(args.input)
        else [args.input]
    )
    for f in files:
        r = classify(f)
        extra = f"conf={r.get('confidence','-')}" if r["verdict"] not in ("NOT_US", "LOW_QUALITY") else r.get("reasons")
        print(f"{r['path'][:32]:34s} q={r['quality']:10s} -> {r['verdict']:11s} route={r['route']}  {extra}")


if __name__ == "__main__":
    main()
