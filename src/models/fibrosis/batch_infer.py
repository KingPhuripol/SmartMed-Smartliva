"""Run the fibrosis ensemble over a folder of ultrasound images and write a JSON report.

Files are located by globbing, never by reconstructing a name from a stem: one image in
this dataset is literally called "5e4b507fe13823298400053d (1).png".

Liver masks are taken from the dataset's precomputed liver_masks/ when available, and
otherwise produced on demand with the project's segmentation U-Net.
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import torch

from infer import ENSEMBLE_PATH, FibrosisEnsemble, load_ensemble, predict_fibrosis
from labels import DATA_ROOT, IMAGES_DIR, MASKS_DIR, load_test_labels
from model import get_device
from preprocess import load_pair

BASE_DIR: Path = Path(__file__).resolve().parent
SEGMENTATION_DIR: Path = BASE_DIR.parent / "segmentation"
SEG_CHECKPOINT: Path = SEGMENTATION_DIR / "checkpoints" / "liver_unet_best.pt"
DEFAULT_OUT_DIR: Path = BASE_DIR.parent.parent / "outputs" / "fibrosis_results"

IMG_EXTS: Tuple[str, ...] = (".png", ".jpg", ".jpeg", ".bmp")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger: logging.Logger = logging.getLogger("SmartLiva.FibrosisBatch")


def load_segmentation_model(device: torch.device):
    """Load the project's liver U-Net for images that have no precomputed mask.

    Sibling modules in this project are imported flatly, and models/segmentation/ has its
    own model.py, train.py and infer.py. They are loaded here with the segmentation
    directory temporarily first on sys.path, and the shadowed entries are restored after,
    so the fibrosis modules of the same name stay bound to their own files.
    """
    collide: Tuple[str, ...] = ("dataset", "model", "train", "infer")
    saved = {name: sys.modules.pop(name) for name in collide if name in sys.modules}
    sys.path.insert(0, str(SEGMENTATION_DIR))
    try:
        import model as segmentation_model  # noqa: PLC0415
        import infer as segmentation_infer  # noqa: PLC0415

        net = segmentation_model.UNet(in_ch=1, out_ch=1).to(device)
        net.load_state_dict(torch.load(str(SEG_CHECKPOINT), map_location=device))
        net.eval()
        return net, segmentation_infer.predict
    finally:
        sys.path.remove(str(SEGMENTATION_DIR))
        for name in collide:
            sys.modules.pop(name, None)
        sys.modules.update(saved)


def find_mask(image_path: Path, mask_dir: Path = MASKS_DIR) -> Optional[Path]:
    """Locate the precomputed liver mask for an image, matching by stem via glob."""
    if not mask_dir.exists():
        return None
    matches: List[Path] = [p for p in mask_dir.glob(f"{glob_escape(image_path.stem)}.*") if p.is_file()]
    return matches[0] if matches else None


def glob_escape(text: str) -> str:
    """Escape glob metacharacters so stems containing [ ] ? * still match literally."""
    return "".join(f"[{ch}]" if ch in "[]*?" else ch for ch in text)


def collect_images(images_dir: Path, limit: Optional[int] = None) -> List[Path]:
    """Glob every supported image in a directory, sorted, optionally truncated."""
    found: List[Path] = sorted(p for p in images_dir.glob("*") if p.suffix.lower() in IMG_EXTS)
    if limit is not None and limit < len(found):
        logger.warning(f"Processing the first {limit} of {len(found)} images (--limit)")
        return found[:limit]
    return found


def analyze_image(
    ensemble: FibrosisEnsemble,
    device: torch.device,
    image_path: Path,
    view: Optional[str],
    segmentation=None,
) -> Dict[str, Any]:
    """Predict stiffness and stage for one image, segmenting the liver if needed."""
    mask_path: Optional[Path] = find_mask(image_path)
    gray, mask = load_pair(str(image_path), str(mask_path) if mask_path else None)

    if mask is None and segmentation is not None:
        net, predict_mask = segmentation
        _, mask = predict_mask(net, device, image_path)

    result: Dict[str, Any] = predict_fibrosis(ensemble, device, gray, mask, view=view)
    result["image"] = image_path.name
    result["mask_source"] = "precomputed" if mask_path else ("unet" if mask is not None else "none")
    return result


def print_report(result: Dict[str, Any]) -> None:
    """Print one image's result in the same shape as combined_infer.py's reports."""
    print(f"\n=== {result['image']} ===")
    print(f"stiffness : {result['kpa']} kPa (est.)  ->  stage {result['stage']}")
    print(
        f"risk      : P(>=F2)={result['prob_ge_f2']:.2f}  "
        f"P(>=F3)={result['prob_ge_f3']:.2f}  P(F4)={result['prob_f4']:.2f}"
    )
    print(f"roi       : {result['roi_bbox']} ({result['mask_source']} mask, {result['input_mode']})")


def write_submission(results: List[Dict[str, Any]], out_path: Path) -> None:
    """Emit a test_submission-shaped CSV.

    This is a demonstration path only. test_submission.csv carries no target column, so
    nothing written here can be validated locally -- it is never used for any metric in
    reports/metrics.json.
    """
    test_df: pd.DataFrame = load_test_labels()
    predicted: Dict[str, Dict[str, Any]] = {Path(r["image"]).stem: r for r in results}

    rows: List[Dict[str, Any]] = []
    for _, row in test_df.iterrows():
        result = predicted.get(row["image_name"])
        rows.append(
            {
                "image_name": row["image_name"],
                "view": row["view"],
                "SWE fibrosis stage": row["swe_stage"] if isinstance(row["swe_stage"], str) else "-",
                "TE(kPa)": result["kpa"] if result else "",
                "TE result": result["stage"] if result else "",
            }
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out_path, index=False)
    missing: int = sum(1 for r in rows if r["TE(kPa)"] == "")
    logger.info(f"Wrote submission for {len(rows) - missing}/{len(rows)} test images -> {out_path}")
    if missing:
        logger.warning(f"{missing} test images had no prediction (not present in --images_dir)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch fibrosis inference over a folder of images")
    parser.add_argument("--images_dir", type=Path, default=IMAGES_DIR)
    parser.add_argument("--ensemble", type=Path, default=ENSEMBLE_PATH)
    parser.add_argument("--out_dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--view", default=None, help="Acquisition view, if uniform across the folder")
    parser.add_argument("--views_from_csv", action="store_true", help="Take each image's view from the dataset CSVs")
    parser.add_argument("--json_out", type=Path, default=None)
    parser.add_argument("--submission", type=Path, default=None, help="Also write a test_submission-shaped CSV")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    if not args.ensemble.exists():
        raise FileNotFoundError(
            f"No ensemble at {args.ensemble}. Build one with:\n"
            "  python infer.py --build_glob 'resnet18_roi_r0f*.pt'"
        )

    device: torch.device = get_device()
    ensemble: FibrosisEnsemble = load_ensemble(args.ensemble, device)

    views: Dict[str, str] = {}
    if args.views_from_csv:
        from labels import load_train_labels

        for frame in (load_train_labels(), load_test_labels()):
            views.update(dict(zip(frame["image_name"], frame["view"])))
        logger.info(f"Loaded views for {len(views)} images from the dataset CSVs")

    images: List[Path] = collect_images(args.images_dir, args.limit)
    logger.info(f"Running fibrosis inference on {len(images)} images from {args.images_dir}")

    segmentation = None
    if not MASKS_DIR.exists() or args.images_dir.resolve() != IMAGES_DIR.resolve():
        if SEG_CHECKPOINT.exists():
            segmentation = load_segmentation_model(device)
            logger.info("Loaded the liver U-Net for images without a precomputed mask")
        else:
            logger.warning(f"No U-Net checkpoint at {SEG_CHECKPOINT}; unmasked images fall back to the fan crop")

    results: List[Dict[str, Any]] = []
    for i, image_path in enumerate(images, 1):
        view: Optional[str] = views.get(image_path.stem, args.view)
        try:
            result: Dict[str, Any] = analyze_image(ensemble, device, image_path, view, segmentation)
        except Exception as err:
            logger.warning(f"Skipped {image_path.name}: {err}")
            continue
        results.append(result)
        if not args.quiet:
            print_report(result)
        if args.quiet and i % 100 == 0:
            logger.info(f"{i}/{len(images)}")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    json_path: Path = args.json_out or (args.out_dir / "fibrosis_reports.json")
    json_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"Wrote {len(results)} reports -> {json_path}")

    if results:
        stages = pd.Series([r["stage"] for r in results]).value_counts().sort_index()
        print(f"\npredicted stage distribution: {dict(stages)}")
        print(f"mean estimated stiffness    : {np.mean([r['kpa'] for r in results]):.2f} kPa")

    if args.submission:
        write_submission(results, args.submission)


if __name__ == "__main__":
    main()
