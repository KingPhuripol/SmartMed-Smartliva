"""Score a segmentation arm on a frozen split. This file produces the benchmark.

Every arm of the bake-off is measured here, on the same frozen patient split, from
the same rasterized ground truth. That is the only thing that makes A, B and C
comparable, so the harness is written before any model runs -- an arm scored ad hoc
is an arm that cannot be compared.

Four decisions about the metric, each of which changes the headline number:

1. Dice is computed PER IMAGE and then averaged, not aggregated over the dataset.
   Dataset-aggregate Dice pools intersections and unions across all images, which
   lets large livers carry small ones and reads several points higher. Per-image is
   both harsher and closer to what a user experiences one scan at a time. This is
   the single most common reason two published Dice figures are incomparable, and
   the SDK's own metrics.json does not state which it used.

2. The headline is the UNWEIGHTED MACRO AVERAGE over the 7 views. GBH alone is 24%
   of the corpus, and a micro average would let it dominate a number that is
   supposed to say "this works on every view". Micro is reported alongside, never
   as the headline.

3. Images whose ground truth lacks a class are EXCLUDED from that class's Dice. Dice
   is undefined on empty ground truth -- scoring it 1.0 inflates, 0.0 deflates, and
   either makes the number un-auditable. The 178 no-liver images are reported
   separately, under the diagnostic described next.

4. The 178 images with no liver polygon are reported as an ANNOTATION-GAP
   DIAGNOSTIC, not as a safety gate. This started life as a safety metric -- "does
   the model hallucinate liver where there is none" -- and measuring it disproved
   its own premise. On the 28 in val, predicted liver area has median 12.7% of
   frame against 13.5% annotated on comparable GBH images that do carry a liver
   polygon, and the predicted region is a single connected component just as it is
   on labelled images. The liver is there; the annotator did not draw it.

   So a high rate here means the labels are incomplete, not that the model is
   wrong, and it must never be read as a pass/fail gate. This corpus contains no
   true negatives, and no "hallucinates on non-liver input" claim can be made from
   it. That question needs the SDK's 10-organ router or, at minimum, its thyroid
   counter-example.
"""

import argparse
import csv
import json
import logging
import math
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

from views import CLASS_NAMES, DATA_ROOT, GALLBLADDER, LIVER, REPORTS_DIR, VIEWS
from manifest import MANIFEST_CSV
from rasterize import rasterize_file
from splits_seg import SPLITS_PATH, load_split

REPO_ROOT: Path = DATA_ROOT.parent.parent

# A view needs this many annotated instances of a class before its per-view Dice for
# that class is stable enough to quote. Only GBH clears it for gallbladder (2,390);
# RH 117, LHA 95 and SPH 41 are reported but flagged.
MIN_INSTANCES_TO_QUOTE: int = 100

# Predicted liver area, as a fraction of the frame, above which an image with no
# liver polygon is counted as disagreeing with its annotation. Diagnostic only --
# see point 4 in the module docstring for why this is not a safety gate.
EMPTY_GT_FP_THRESHOLD: float = 0.01

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger: logging.Logger = logging.getLogger("SmartLiva.SegEvaluate")


def dice(pred: np.ndarray, truth: np.ndarray, class_index: int) -> Optional[float]:
    """Per-image Dice for one class. None when the class is absent from the truth."""
    truth_mask: np.ndarray = truth == class_index
    truth_area: int = int(truth_mask.sum())
    if truth_area == 0:
        return None
    pred_mask: np.ndarray = pred == class_index
    total: int = truth_area + int(pred_mask.sum())
    return 2.0 * float((pred_mask & truth_mask).sum()) / total


def iou(pred: np.ndarray, truth: np.ndarray, class_index: int) -> Optional[float]:
    """Per-image IoU for one class. None when the class is absent from the truth."""
    truth_mask: np.ndarray = truth == class_index
    if not truth_mask.any():
        return None
    pred_mask: np.ndarray = pred == class_index
    union: int = int((pred_mask | truth_mask).sum())
    return float((pred_mask & truth_mask).sum()) / union


def wilson_interval(successes: int, total: int, z: float = 1.96) -> Tuple[float, float]:
    """Wilson score interval for a binomial proportion.

    Used instead of the normal approximation because the no-liver counts are small
    (16 in test) and near the boundary, where the normal interval is badly wrong.
    """
    if total == 0:
        return (0.0, 1.0)
    phat: float = successes / total
    denominator: float = 1.0 + z * z / total
    centre: float = (phat + z * z / (2 * total)) / denominator
    margin: float = (
        z * math.sqrt(phat * (1 - phat) / total + z * z / (4 * total * total)) / denominator
    )
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def load_rows(split: str, manifest: Path = MANIFEST_CSV, splits: Path = SPLITS_PATH) -> List[Dict[str, str]]:
    """Manifest rows belonging to one split of the frozen patient assignment."""
    split_of_patient: Dict[str, str] = load_split(splits)
    with manifest.open(encoding="utf-8", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if split_of_patient[row["patient"]] == split]
    if not rows:
        raise ValueError(f"no rows for split {split!r}")
    return rows


def build_predictor(arm: str) -> Callable[[Image.Image], np.ndarray]:
    """Return the predict function for an arm name.

    Arms A0/A1 are the SDK checkpoint as shipped, without and with its fan mask.
    Trained arms are registered here as they are produced.
    """
    if arm in ("A0", "A1"):
        from model_sdk import get_device, load_sdk_model, predict_mask

        device = get_device()
        model = load_sdk_model(device=device)
        use_fan: bool = arm == "A1"
        logger.info(f"arm {arm}: SDK 3-class U-Net on {device}, fan_mask={use_fan}")
        return lambda image: predict_mask(image, model, device, use_fan=use_fan)

    raise ValueError(f"unknown arm {arm!r}. Known: A0, A1")


def evaluate(arm: str, split: str, limit: Optional[int] = None) -> Dict[str, Any]:
    """Run one arm over one split and return the full result payload."""
    rows = load_rows(split)
    if limit is not None:
        rows = rows[:limit]

    predict = build_predictor(arm)

    per_view: Dict[str, Dict[str, List[float]]] = defaultdict(
        lambda: {"liver_dice": [], "liver_iou": [], "gallbladder_dice": [], "gallbladder_iou": []}
    )
    empty_gt_total: int = 0
    empty_gt_false_positives: int = 0
    empty_gt_areas: List[float] = []

    started: float = time.time()
    for index, row in enumerate(rows, start=1):
        image = Image.open(REPO_ROOT / row["img_path"]).convert("RGB")
        truth: np.ndarray = rasterize_file(REPO_ROOT / row["json_path"])
        pred: np.ndarray = predict(image)

        if pred.shape != truth.shape:
            raise ValueError(
                f"prediction shape {pred.shape} != ground truth {truth.shape} for "
                f"{row['patient']}/{row['view']}"
            )

        bucket = per_view[row["view"]]
        for class_index, prefix in ((LIVER, "liver"), (GALLBLADDER, "gallbladder")):
            score = dice(pred, truth, class_index)
            if score is not None:
                bucket[f"{prefix}_dice"].append(score)
                bucket[f"{prefix}_iou"].append(iou(pred, truth, class_index))

        # Annotation-gap diagnostic: ground truth carries no liver polygon.
        if not (truth == LIVER).any():
            empty_gt_total += 1
            area_fraction: float = float((pred == LIVER).sum()) / pred.size
            empty_gt_areas.append(area_fraction)
            if area_fraction > EMPTY_GT_FP_THRESHOLD:
                empty_gt_false_positives += 1

        if index % 250 == 0:
            rate: float = index / (time.time() - started)
            logger.info(f"  {index}/{len(rows)} images ({rate:.1f}/s)")

    elapsed: float = time.time() - started
    return _assemble(arm, split, rows, per_view, empty_gt_total, empty_gt_false_positives,
                     empty_gt_areas, elapsed)


def _assemble(
    arm: str,
    split: str,
    rows: List[Dict[str, str]],
    per_view: Dict[str, Dict[str, List[float]]],
    empty_gt_total: int,
    empty_gt_false_positives: int,
    empty_gt_areas: List[float],
    elapsed: float,
) -> Dict[str, Any]:
    """Turn accumulated per-image scores into the reported payload."""
    view_table: Dict[str, Any] = {}
    for view in VIEWS:
        bucket = per_view.get(view)
        if not bucket:
            continue
        entry: Dict[str, Any] = {"n_images": sum(1 for row in rows if row["view"] == view)}
        for prefix in ("liver", "gallbladder"):
            scores = bucket[f"{prefix}_dice"]
            ious = bucket[f"{prefix}_iou"]
            entry[prefix] = {
                "n": len(scores),
                "dice_mean": round(float(np.mean(scores)), 6) if scores else None,
                "dice_median": round(float(np.median(scores)), 6) if scores else None,
                "dice_p10": round(float(np.percentile(scores, 10)), 6) if scores else None,
                "iou_mean": round(float(np.mean(ious)), 6) if ious else None,
                # Below this many instances the per-view figure is too unstable to quote.
                "quotable": len(scores) >= MIN_INSTANCES_TO_QUOTE,
            }
        view_table[view] = entry

    def macro(prefix: str, quotable_only: bool) -> Optional[float]:
        values = [
            view_table[view][prefix]["dice_mean"]
            for view in view_table
            if view_table[view][prefix]["dice_mean"] is not None
            and (view_table[view][prefix]["quotable"] or not quotable_only)
        ]
        return round(float(np.mean(values)), 6) if values else None

    def micro(prefix: str) -> Optional[float]:
        total_n = sum(view_table[view][prefix]["n"] for view in view_table)
        if total_n == 0:
            return None
        weighted = sum(
            view_table[view][prefix]["dice_mean"] * view_table[view][prefix]["n"]
            for view in view_table
            if view_table[view][prefix]["dice_mean"] is not None
        )
        return round(weighted / total_n, 6)

    fp_low, fp_high = wilson_interval(empty_gt_false_positives, empty_gt_total)
    clean = empty_gt_total - empty_gt_false_positives
    clean_low, clean_high = wilson_interval(clean, empty_gt_total)

    return {
        "arm": arm,
        "split": split,
        "n_images": len(rows),
        "n_patients": len({row["patient"] for row in rows}),
        "elapsed_s": round(elapsed, 1),
        "metric_definition": {
            "dice": "per-image, then averaged",
            "headline": "unweighted macro average over views",
            "empty_ground_truth": "excluded from Dice, scored as empty_gt_fp_rate",
            "empty_gt_fp_threshold": EMPTY_GT_FP_THRESHOLD,
        },
        "headline": {
            "liver_macro_dice": macro("liver", quotable_only=False),
            "liver_micro_dice": micro("liver"),
            "gallbladder_macro_dice_quotable_views": macro("gallbladder", quotable_only=True),
        },
        "per_view": view_table,
        "annotation_gap_diagnostic": {
            "interpretation": (
                "Images with no liver polygon. MEASURED 2026-08-11: these are annotation "
                "gaps, not true negatives -- predicted liver area matches the annotated "
                "area on comparable labelled images. A high disagreement rate here means "
                "incomplete labels, NOT model error. Not a pass/fail gate."
            ),
            "n_images": empty_gt_total,
            "n_disagreeing": empty_gt_false_positives,
            "disagreement_rate": round(empty_gt_false_positives / empty_gt_total, 6) if empty_gt_total else None,
            "disagreement_rate_ci95": [round(fp_low, 6), round(fp_high, 6)],
            "agreement_rate": round(clean / empty_gt_total, 6) if empty_gt_total else None,
            "agreement_rate_ci95": [round(clean_low, 6), round(clean_high, 6)],
            "predicted_liver_area_median": (
                round(float(np.median(empty_gt_areas)), 6) if empty_gt_areas else None
            ),
            "predicted_liver_area_max": (
                round(float(np.max(empty_gt_areas)), 6) if empty_gt_areas else None
            ),
        },
    }


def _print_result(result: Dict[str, Any]) -> None:
    """Print the benchmark table."""
    print(f"\n=== arm {result['arm']} on {result['split']} ===")
    print(
        f"{result['n_images']} images from {result['n_patients']} patients "
        f"in {result['elapsed_s']}s"
    )
    print("Dice is per-image then averaged; headline is the unweighted macro over views.")

    print("\nview      n   liver Dice   median      p10      IoU  |  GB Dice     n")
    for view, entry in result["per_view"].items():
        liver, gall = entry["liver"], entry["gallbladder"]
        gb_cell = "      -      -"
        if gall["dice_mean"] is not None:
            flag = " " if gall["quotable"] else "*"
            gb_cell = f"{gall['dice_mean']:8.4f}{flag} {gall['n']:5d}"
        print(
            f"  {view:4s} {liver['n']:5d}    {liver['dice_mean']:8.4f} "
            f"{liver['dice_median']:8.4f} {liver['dice_p10']:8.4f} {liver['iou_mean']:8.4f}  |{gb_cell}"
        )
    print(f"  (* fewer than {MIN_INSTANCES_TO_QUOTE} instances -- unstable, do not quote)")

    head = result["headline"]
    print(f"\nliver macro Dice (headline) : {head['liver_macro_dice']:.4f}")
    print(f"liver micro Dice            : {head['liver_micro_dice']:.4f}")
    if head["gallbladder_macro_dice_quotable_views"] is not None:
        print(f"gallbladder macro Dice      : {head['gallbladder_macro_dice_quotable_views']:.4f}"
              f"  (quotable views only)")

    gap = result["annotation_gap_diagnostic"]
    if gap["n_images"]:
        print(
            f"\nannotation-gap diagnostic (NOT a safety gate)"
            f"\n  images with no liver polygon : {gap['n_images']}"
            f"\n  model predicts liver on      : {gap['n_disagreeing']} of them"
            f"\n  predicted liver area         : median "
            f"{gap['predicted_liver_area_median'] * 100:.2f}%, max "
            f"{gap['predicted_liver_area_max'] * 100:.2f}% of frame"
        )
        print(
            "  These are unannotated livers, not hallucinations -- the predicted area\n"
            "  matches what is annotated on comparable labelled images. Exclude them\n"
            "  from training; this corpus cannot test non-liver input."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Score a segmentation arm on a frozen split")
    parser.add_argument("--arm", required=True, help="Arm name (A0, A1, ...)")
    parser.add_argument("--split", default="val", choices=("train", "val", "test"))
    parser.add_argument("--limit", type=int, default=None, help="Score only the first N images")
    parser.add_argument("--out", type=Path, default=None, help="Result JSON path")
    args = parser.parse_args()

    if args.split == "test":
        logger.warning(
            "Scoring on TEST. This split is opened once, by one model, at the freeze "
            "gate. If you are comparing arms or tuning anything, use --split val."
        )

    result = evaluate(args.arm, args.split, limit=args.limit)
    _print_result(result)

    out: Path = args.out or REPORTS_DIR / f"eval_{args.arm}_{args.split}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    logger.info(f"wrote result to: {out}")


if __name__ == "__main__":
    main()
