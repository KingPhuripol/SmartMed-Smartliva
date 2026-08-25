"""Fibrosis inference: a fold ensemble behind one array-in, dict-out call.

`predict_fibrosis` takes an in-memory grayscale image and liver mask rather than a path,
so the FastAPI server can hand over the mask the U-Net has already computed for the
request instead of segmenting the image twice.

The headline output is a **risk tier**, not a stage or a stiffness value. Measured on the
730 held-out exams, the regression collapses toward the mean: predicted kPa spans only
39% of the true spread, and exams that are truly F4 (15.09 kPa on average) are predicted
at 5.97 kPa on average -- below the F0/F1 cutoff. Presented as a stage, that would label
cirrhotic patients F0, which is worse than showing nothing.

What the model does support is ranking. Cut on P(stage >= F2) from the ordinal head, the
held-out exams separate cleanly: 9.7% were >=F2 in the low tier against 51.4% in the high
tier, and 2.3% versus 29.7% for F4. Each tier therefore ships the rates actually observed
in it. The kPa estimate and derived stage are still returned, clearly marked as compressed
scores rather than measurements.
"""

import argparse
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import torch

from dataset import IMAGENET_MEAN, IMAGENET_STD, UNKNOWN_VIEW, VIEW_TO_INDEX
from labels import STAGES, TE_THRESHOLDS, kpa_to_stage
from model import FibrosisNet, corn_cumulative_probs, get_device
from preprocess import apply_roi, clean_mask, liver_roi_bbox

BASE_DIR: Path = Path(__file__).resolve().parent
CHECKPOINT_DIR: Path = BASE_DIR / "checkpoints"
ENSEMBLE_PATH: Path = CHECKPOINT_DIR / "fibrosis_ensemble.pt"

# Risk tiers are cut on P(stage >= F2) from the ordinal head, not on the estimated kPa.
# Regression shrinks hard toward the mean here -- out-of-fold predictions span only 39%
# of the true spread, and true F4 exams average 5.97 kPa predicted against 15.09 actual,
# so a kPa point estimate is not a measurement and must not be presented as one. The
# ordinal probability is on a fixed [0,1] scale, so it is comparable across fold models
# and can be averaged and thresholded meaningfully.
RISK_TIER_BOUNDS: Tuple[float, float] = (0.15, 0.30)
RISK_TIER_LABELS: Tuple[str, str, str] = ("ต่ำ", "ปานกลาง", "สูง")
RISK_TIER_LABELS_EN: Tuple[str, str, str] = ("low", "moderate", "high")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger: logging.Logger = logging.getLogger("SmartLiva.FibrosisInfer")


class FibrosisEnsemble:
    """A set of per-fold FibrosisNet weights averaged in log-stiffness space."""

    def __init__(
        self,
        models: List[FibrosisNet],
        mode: str,
        img_size: int,
        use_view: bool,
        cutoffs_log_kpa: List[float],
        risk_tier_bounds: Optional[List[float]] = None,
        risk_tier_stats: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.models: List[FibrosisNet] = models
        self.mode: str = mode
        self.img_size: int = img_size
        self.use_view: bool = use_view
        self.cutoffs_log_kpa: List[float] = cutoffs_log_kpa
        self.risk_tier_bounds: List[float] = risk_tier_bounds or list(RISK_TIER_BOUNDS)
        self.risk_tier_stats: List[Dict[str, Any]] = risk_tier_stats or []
        self.metadata: Dict[str, Any] = metadata or {}

    def __len__(self) -> int:
        return len(self.models)


def tier_from_probability(prob_ge_f2: float, bounds: Sequence[float]) -> int:
    """Map P(stage >= F2) to a risk tier index 0 (low) / 1 (moderate) / 2 (high)."""
    return int(np.searchsorted(np.asarray(bounds, dtype=float), prob_ge_f2, side="right"))


def compute_tier_stats(
    predictions_csv: Path,
    bounds: Sequence[float] = RISK_TIER_BOUNDS,
) -> List[Dict[str, Any]]:
    """Measure what each risk tier actually contained, from out-of-fold predictions.

    This is what makes a tier interpretable: rather than asserting that "high risk" means
    something, the ensemble ships the observed rate of >=F2, >=F3 and F4 among the
    held-out exams that landed in that tier.
    """
    import pandas as pd

    preds = pd.read_csv(predictions_csv)
    exams = preds.groupby("exam_id").agg({"stage_index": "first", "prob_ge_f2": "mean"}).reset_index()
    tiers = np.searchsorted(np.asarray(bounds, dtype=float), exams["prob_ge_f2"].to_numpy(), side="right")

    stats: List[Dict[str, Any]] = []
    for index in range(len(bounds) + 1):
        group = exams[tiers == index]
        stage = group["stage_index"].to_numpy()
        stats.append(
            {
                "tier": index,
                "label": RISK_TIER_LABELS[index],
                "label_en": RISK_TIER_LABELS_EN[index],
                "n_exams": int(len(group)),
                "observed_ge_f2": round(float((stage >= 2).mean()), 4) if len(group) else None,
                "observed_ge_f3": round(float((stage >= 3).mean()), 4) if len(group) else None,
                "observed_f4": round(float((stage >= 4).mean()), 4) if len(group) else None,
            }
        )
    return stats


def build_ensemble(
    checkpoint_paths: Sequence[Path],
    out_path: Path = ENSEMBLE_PATH,
    reference_predictions: Optional[Path] = None,
) -> Path:
    """Bundle per-fold checkpoints into a single file the server can load in one read."""
    if not checkpoint_paths:
        raise ValueError("No checkpoints given")

    states: List[Dict[str, torch.Tensor]] = []
    cutoffs: List[List[float]] = []
    config: Optional[Dict[str, Any]] = None

    for path in checkpoint_paths:
        checkpoint: Dict[str, Any] = torch.load(str(path), map_location="cpu", weights_only=False)
        states.append(checkpoint["state_dict"])
        cutoffs.append(checkpoint["cutoffs_log_kpa"])
        entry = {
            "backbone": checkpoint["backbone"],
            "mode": checkpoint["mode"],
            "img_size": checkpoint["img_size"],
            "use_view": checkpoint["use_view"],
        }
        if config is None:
            config = entry
        elif config != entry:
            raise ValueError(f"{path} config {entry} differs from {config}; cannot ensemble")

    assert config is not None
    payload: Dict[str, Any] = {
        **config,
        "state_dicts": states,
        # Averaging the per-fold cutoffs is legitimate: each was fitted on its own inner
        # split, none of them ever saw the folds they were scored on.
        "cutoffs_log_kpa": np.mean(np.asarray(cutoffs, dtype=float), axis=0).tolist(),
        "source_checkpoints": [p.name for p in checkpoint_paths],
        "n_members": len(states),
        "risk_tier_bounds": list(RISK_TIER_BOUNDS),
        "risk_tier_stats": compute_tier_stats(reference_predictions) if reference_predictions else [],
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(payload, str(out_path))
    logger.info(f"Bundled {len(states)} folds -> {out_path}")
    return out_path


def load_ensemble(path: Path = ENSEMBLE_PATH, device: Optional[torch.device] = None) -> FibrosisEnsemble:
    """Load the bundled ensemble onto a device, ready for inference."""
    device = device or get_device()
    payload: Dict[str, Any] = torch.load(str(path), map_location=device, weights_only=False)

    models: List[FibrosisNet] = []
    for state in payload["state_dicts"]:
        net = FibrosisNet(
            backbone=payload["backbone"], pretrained=False, use_view=payload["use_view"]
        ).to(device)
        net.load_state_dict(state)
        net.eval()
        models.append(net)

    logger.info(f"Loaded {len(models)}-fold fibrosis ensemble ({payload['backbone']}, {payload['mode']})")
    return FibrosisEnsemble(
        models=models,
        mode=payload["mode"],
        img_size=payload["img_size"],
        use_view=payload["use_view"],
        cutoffs_log_kpa=payload["cutoffs_log_kpa"],
        risk_tier_bounds=payload.get("risk_tier_bounds"),
        risk_tier_stats=payload.get("risk_tier_stats"),
        metadata={k: payload[k] for k in ("n_members", "source_checkpoints") if k in payload},
    )


def _to_tensor(roi: np.ndarray, img_size: int, device: torch.device) -> torch.Tensor:
    """Resize a cropped grayscale ROI into a normalized 3-channel batch of one."""
    import cv2  # local import keeps this module importable where cv2 is absent

    interpolation: int = cv2.INTER_AREA if max(roi.shape[:2]) > img_size else cv2.INTER_LINEAR
    resized: np.ndarray = cv2.resize(roi, (img_size, img_size), interpolation=interpolation)

    tensor: torch.Tensor = torch.from_numpy(resized).float().div_(255.0)
    tensor = tensor.unsqueeze(0).repeat(3, 1, 1)
    mean = torch.tensor(IMAGENET_MEAN).view(3, 1, 1)
    std = torch.tensor(IMAGENET_STD).view(3, 1, 1)
    return ((tensor - mean) / std).unsqueeze(0).to(device)


@torch.no_grad()
def predict_fibrosis(
    ensemble: FibrosisEnsemble,
    device: torch.device,
    gray: np.ndarray,
    mask: Optional[np.ndarray],
    view: Optional[str] = None,
    tta: bool = True,
) -> Dict[str, Any]:
    """Estimate liver stiffness and fibrosis stage for one ultrasound image."""
    roi: np.ndarray = apply_roi(gray, mask, ensemble.mode)
    image: torch.Tensor = _to_tensor(roi, ensemble.img_size, device)

    view_index: int = VIEW_TO_INDEX.get(view, UNKNOWN_VIEW) if (view and ensemble.use_view) else UNKNOWN_VIEW
    view_tensor: torch.Tensor = torch.tensor([view_index], dtype=torch.long, device=device)

    log_kpa_values: List[float] = []
    cumulative_values: List[np.ndarray] = []

    for model in ensemble.models:
        outputs = model(image, view_tensor)
        log_kpa: torch.Tensor = outputs["log_kpa"]
        cumulative: torch.Tensor = corn_cumulative_probs(outputs["corn"])

        if tta:
            flipped = model(torch.flip(image, dims=[3]), view_tensor)
            log_kpa = 0.5 * (log_kpa + flipped["log_kpa"])
            cumulative = 0.5 * (cumulative + corn_cumulative_probs(flipped["corn"]))

        log_kpa_values.append(float(log_kpa.squeeze().cpu()))
        cumulative_values.append(cumulative.squeeze(0).float().cpu().numpy())

    mean_log_kpa: float = float(np.mean(log_kpa_values))
    kpa: float = float(np.exp(mean_log_kpa))
    cumulative_mean: np.ndarray = np.mean(np.stack(cumulative_values), axis=0)

    stage: str = kpa_to_stage(kpa)
    calibrated_index: int = int(np.searchsorted(np.asarray(ensemble.cutoffs_log_kpa), mean_log_kpa, side="left"))

    cleaned: Optional[np.ndarray] = clean_mask(mask) if mask is not None else None
    bbox = liver_roi_bbox(cleaned) if cleaned is not None else None

    prob_ge_f2: float = float(cumulative_mean[1])
    tier: int = tier_from_probability(prob_ge_f2, ensemble.risk_tier_bounds)
    tier_stats: Dict[str, Any] = (
        ensemble.risk_tier_stats[tier] if tier < len(ensemble.risk_tier_stats) else {}
    )

    return {
        "risk_tier": tier,
        "risk_tier_label": RISK_TIER_LABELS[tier],
        "risk_tier_label_en": RISK_TIER_LABELS_EN[tier],
        "tier_observed_ge_f2": tier_stats.get("observed_ge_f2"),
        "tier_observed_ge_f3": tier_stats.get("observed_ge_f3"),
        "tier_observed_f4": tier_stats.get("observed_f4"),
        "tier_n_reference_exams": tier_stats.get("n_exams"),
        "kpa": round(kpa, 2),
        "log_kpa": round(mean_log_kpa, 4),
        "stage": stage,
        "stage_index": STAGES.index(stage),
        "stage_calibrated": STAGES[calibrated_index],
        "prob_ge_f2": round(float(cumulative_mean[1]), 4),
        "prob_ge_f3": round(float(cumulative_mean[2]), 4),
        "prob_f4": round(float(cumulative_mean[3]), 4),
        "roi_bbox": [int(v) for v in bbox] if bbox else None,
        "input_mode": ensemble.mode,
        "n_models": len(ensemble),
        "kpa_spread": round(float(np.exp(np.max(log_kpa_values)) - np.exp(np.min(log_kpa_values))), 2),
        "thresholds_kpa": list(TE_THRESHOLDS),
    }


def predict_fibrosis_from_path(
    ensemble: FibrosisEnsemble,
    device: torch.device,
    img_path: str,
    mask_path: Optional[str] = None,
    view: Optional[str] = None,
    tta: bool = True,
) -> Dict[str, Any]:
    """Path-based wrapper for CLI use; the server should call predict_fibrosis directly."""
    from preprocess import load_pair

    gray, mask = load_pair(img_path, mask_path)
    result: Dict[str, Any] = predict_fibrosis(ensemble, device, gray, mask, view=view, tta=tta)
    result["image"] = Path(img_path).name
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Fibrosis inference and ensemble bundling")
    parser.add_argument("--build", nargs="+", type=Path, help="Checkpoint paths to bundle into an ensemble")
    parser.add_argument("--build_glob", default=None, help="Glob under checkpoints/, e.g. 'resnet18_roi_r0f*.pt'")
    parser.add_argument("--out", type=Path, default=ENSEMBLE_PATH)
    parser.add_argument("--reference", type=Path, default=None,
                        help="Out-of-fold predictions CSV used to measure what each risk tier contained")
    parser.add_argument("--image", type=Path, help="Image to run inference on")
    parser.add_argument("--mask", type=Path, default=None)
    parser.add_argument("--view", default=None)
    parser.add_argument("--ensemble", type=Path, default=ENSEMBLE_PATH)
    args = parser.parse_args()

    if args.build or args.build_glob:
        paths: List[Path] = list(args.build or [])
        if args.build_glob:
            paths += sorted(CHECKPOINT_DIR.glob(args.build_glob))
        build_ensemble(paths, args.out, reference_predictions=args.reference)
        return

    if not args.image:
        parser.error("Provide --image, or --build/--build_glob to bundle an ensemble")

    device: torch.device = get_device()
    ensemble: FibrosisEnsemble = load_ensemble(args.ensemble, device)
    result: Dict[str, Any] = predict_fibrosis_from_path(
        ensemble, device, str(args.image), str(args.mask) if args.mask else None, view=args.view
    )

    print(f"\n=== {result['image']} ===")
    print(f"risk tier           : {result['risk_tier_label_en']}  "
          f"(held-out exams in this tier were >=F2 in {(result['tier_observed_ge_f2'] or 0) * 100:.0f}% of cases)")
    print(f"estimated stiffness : {result['kpa']} kPa  -- compressed toward the mean, not a measurement")
    print(f"stage               : {result['stage']}  (calibrated: {result['stage_calibrated']})")
    print(f"P(>=F2)             : {result['prob_ge_f2']:.3f}")
    print(f"P(>=F3)             : {result['prob_ge_f3']:.3f}")
    print(f"P(F4)               : {result['prob_f4']:.3f}")


if __name__ == "__main__":
    main()
