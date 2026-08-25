"""Phase 1 gate: visually and numerically QC the U-Net liver masks on the fibrosis set.

The segmentation checkpoint was trained on `data/7272660` -- a different dataset with a
different vendor mix and a different clinical question -- so its masks on this dataset
are an assumption, not a given. This script costs half a day and decides whether the
liver-ROI branch is worth building at all.

Outputs contact sheets to reports/qc/ plus reports/qc/qc_report.json. A human grades the
sheets, then records the decision with --decide.
"""

import argparse
import json
import logging
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
import pandas as pd

from labels import STAGES, load_train_labels
from preprocess import apply_roi, clean_mask, detect_fan, liver_roi_bbox, load_pair

BASE_DIR: Path = Path(__file__).resolve().parent
REPORT_DIR: Path = BASE_DIR / "reports" / "qc"

TILE: int = 220
ROWS_PER_SHEET: int = 10

# Grading branches from the plan. The chosen primary input mode follows from the
# fraction of masks a human grades as "good".
DECISION_RULES: Tuple[Tuple[float, str, str], ...] = (
    (0.85, "roi_masked_bbox", "masks are reliable: use the liver ROI, ablate against fan"),
    (0.60, "fan", "masks are patchy: use the fan crop, keep ROI only as an ablation"),
    (0.00, "fan", "masks are unusable: drop the ROI branch entirely, fan + centre crop"),
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger: logging.Logger = logging.getLogger("SmartLiva.FibrosisQC")


def _n_components(binary: np.ndarray) -> int:
    """Count foreground connected components in a binary mask."""
    if binary.sum() == 0:
        return 0
    n_labels, _ = cv2.connectedComponents(binary.astype(np.uint8), connectivity=8)
    return n_labels - 1


def stratified_sample(df: pd.DataFrame, n: int, seed: int = 42) -> pd.DataFrame:
    """Sample `n` rows spread across stages and the resolutions present in the data.

    Both axes matter: a mask failure concentrated in one scanner would be invisible in a
    stage-only sample, and resolution is the confound we most need to see across.
    """
    rng = np.random.default_rng(seed)
    per_stage: int = max(n // len(STAGES), 1)

    picked: List[pd.DataFrame] = []
    for stage in STAGES:
        pool: pd.DataFrame = df[df["te_stage"] == stage]
        if pool.empty:
            continue
        take: int = min(per_stage, len(pool))
        idx = rng.choice(len(pool), size=take, replace=False)
        picked.append(pool.iloc[idx])

    sample: pd.DataFrame = pd.concat(picked).reset_index(drop=True)
    return sample.iloc[rng.permutation(len(sample))].reset_index(drop=True)


def measure(row: pd.Series) -> Dict[str, Any]:
    """Compute the per-image QC numbers that back up the visual grading."""
    gray, mask = load_pair(row["img_path"], row["mask_path"])
    h, w = gray.shape[:2]

    if mask is None:
        return {"image_name": row["image_name"], "te_stage": row["te_stage"], "mask_read_failed": True}

    cleaned: np.ndarray = clean_mask(mask)
    fx1, fy1, fx2, fy2 = detect_fan(gray)
    bbox: Optional[Tuple[int, int, int, int]] = liver_roi_bbox(cleaned)

    # A mask leaking outside the imaging sector means the U-Net is segmenting chrome.
    outside_fan: np.ndarray = cleaned.copy()
    outside_fan[fy1:fy2, fx1:fx2] = 0
    leak: float = float(outside_fan.sum() / max(cleaned.sum(), 1))

    return {
        "image_name": row["image_name"],
        "te_stage": row["te_stage"],
        "shape": [h, w],
        "fg_fraction_raw": round(float(mask.mean()), 4),
        "fg_fraction_clean": round(float(cleaned.mean()), 4),
        "components_raw": _n_components(mask),
        "components_clean": _n_components(cleaned),
        "fan_fraction": round(float((fx2 - fx1) * (fy2 - fy1) / (h * w)), 4),
        "mask_outside_fan": round(leak, 4),
        "roi_bbox": list(bbox) if bbox else None,
        "roi_aspect": round((bbox[2] - bbox[0]) / max(bbox[3] - bbox[1], 1), 3) if bbox else None,
        "mask_read_failed": False,
    }


def _panel(img: np.ndarray, caption: str) -> np.ndarray:
    """Render one square BGR tile with a caption bar."""
    if img.size == 0:
        img = np.zeros((TILE, TILE), dtype=np.uint8)
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)

    tile: np.ndarray = cv2.resize(img, (TILE, TILE), interpolation=cv2.INTER_AREA)
    cv2.rectangle(tile, (0, TILE - 20), (TILE, TILE), (0, 0, 0), -1)
    cv2.putText(tile, caption[:34], (4, TILE - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 255, 255), 1)
    return tile


def build_row(row: pd.Series) -> np.ndarray:
    """Build one contact-sheet row: source + fan box, cleaned mask overlay, ROI crop."""
    gray, mask = load_pair(row["img_path"], row["mask_path"])
    cleaned: np.ndarray = clean_mask(mask) if mask is not None else np.zeros_like(gray)

    source: np.ndarray = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    fx1, fy1, fx2, fy2 = detect_fan(gray)
    cv2.rectangle(source, (fx1, fy1), (fx2, fy2), (0, 200, 255), 3)

    overlay: np.ndarray = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    overlay[cleaned == 1] = (0.55 * overlay[cleaned == 1] + 0.45 * np.array([0, 220, 0])).astype(np.uint8)
    bbox = liver_roi_bbox(cleaned)
    if bbox:
        cv2.rectangle(overlay, (bbox[0], bbox[1]), (bbox[2], bbox[3]), (0, 0, 255), 3)

    roi: np.ndarray = apply_roi(gray, mask, "roi_masked_bbox")

    return np.hstack(
        [
            _panel(source, f"{row['te_stage']} {row['image_name'][:12]} fan"),
            _panel(overlay, f"mask fg={cleaned.mean():.2f} cc={_n_components(cleaned)}"),
            _panel(roi, "roi_masked_bbox"),
        ]
    )


def write_sheets(sample: pd.DataFrame, out_dir: Path) -> List[Path]:
    """Write the sampled rows out as numbered contact sheets."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("sheet_*.png"):
        stale.unlink()

    paths: List[Path] = []
    for start in range(0, len(sample), ROWS_PER_SHEET):
        chunk: pd.DataFrame = sample.iloc[start : start + ROWS_PER_SHEET]
        sheet: np.ndarray = np.vstack([build_row(r) for _, r in chunk.iterrows()])
        path: Path = out_dir / f"sheet_{start // ROWS_PER_SHEET:02d}.png"
        cv2.imwrite(str(path), sheet)
        paths.append(path)
    return paths


def summarize(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate the per-image measurements into the numbers that inform the decision."""
    usable: List[Dict[str, Any]] = [r for r in records if not r["mask_read_failed"]]

    def pct(key: str, q: float) -> float:
        return round(float(np.percentile([r[key] for r in usable], q)), 4)

    empty: int = sum(1 for r in usable if r["fg_fraction_clean"] < 0.01)
    implausible: int = sum(1 for r in usable if not 0.05 <= r["fg_fraction_clean"] <= 0.75)
    leaking: int = sum(1 for r in usable if r["mask_outside_fan"] > 0.15)

    return {
        "n_sampled": len(records),
        "n_mask_read_failed": len(records) - len(usable),
        "fg_fraction_clean": {"p05": pct("fg_fraction_clean", 5), "median": pct("fg_fraction_clean", 50), "p95": pct("fg_fraction_clean", 95)},
        "components_raw": {"median": pct("components_raw", 50), "p95": pct("components_raw", 95), "max": max(r["components_raw"] for r in usable)},
        "components_clean": {"median": pct("components_clean", 50), "max": max(r["components_clean"] for r in usable)},
        "n_empty_masks": empty,
        "n_implausible_fg": implausible,
        "n_leaking_outside_fan": leaking,
        "distinct_shapes": len({tuple(r["shape"]) for r in usable}),
        "by_stage": dict(Counter(r["te_stage"] for r in usable)),
    }


def decide(good_fraction: float, out_dir: Path) -> Dict[str, Any]:
    """Record the human grading outcome and the input mode it implies."""
    for threshold, mode, rationale in DECISION_RULES:
        if good_fraction >= threshold:
            decision: Dict[str, Any] = {
                "good_fraction": good_fraction,
                "primary_input_mode": mode,
                "ablation_input_mode": "fan" if mode != "fan" else "roi_masked_bbox",
                "rationale": rationale,
            }
            break

    out_dir.mkdir(parents=True, exist_ok=True)
    path: Path = out_dir / "decision.json"
    path.write_text(json.dumps(decision, indent=2), encoding="utf-8")
    logger.info(f"Recorded decision -> {path}")
    print(json.dumps(decision, indent=2))
    return decision


def main() -> None:
    parser = argparse.ArgumentParser(description="QC the U-Net liver masks on the fibrosis dataset")
    parser.add_argument("--n", type=int, default=120, help="Number of images to sample")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out_dir", type=Path, default=REPORT_DIR)
    parser.add_argument("--decide", type=float, default=None, help="Record the fraction graded 'good' (0-1) and exit")
    args = parser.parse_args()

    if args.decide is not None:
        decide(args.decide, args.out_dir)
        return

    df: pd.DataFrame = load_train_labels()
    sample: pd.DataFrame = stratified_sample(df, args.n, seed=args.seed)
    logger.info(f"Sampled {len(sample)} images across {sample['te_stage'].nunique()} stages")

    records: List[Dict[str, Any]] = [measure(row) for _, row in sample.iterrows()]
    sheets: List[Path] = write_sheets(sample, args.out_dir)

    report: Dict[str, Any] = {"summary": summarize(records), "images": records}
    report_path: Path = args.out_dir / "qc_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\n=== Mask QC summary ===")
    print(json.dumps(report["summary"], indent=2))
    print(f"\nWrote {len(sheets)} contact sheets to {args.out_dir}")
    print("Review them, then record the outcome, e.g.:")
    print(f"  python {Path(__file__).name} --decide 0.9")


if __name__ == "__main__":
    main()
