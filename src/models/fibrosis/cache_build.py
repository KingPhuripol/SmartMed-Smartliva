"""Precompute preprocessed fibrosis images so training does not re-decode 1MP PNGs.

Each epoch would otherwise read a full-resolution PNG, run morphology on the mask, and
crop -- per image, per epoch, across 15 cross-validation folds. Caching at 320x320
(training crops to 256) turns that into a small PNG read.

One cache directory per input mode, so mode ablations and the negative-control probes
all read from the same layout.
"""

import argparse
import logging
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import pandas as pd

from labels import BASE_DIR, load_test_labels, load_train_labels
from preprocess import INPUT_MODES, preprocess_image

CACHE_ROOT: Path = BASE_DIR / "outputs" / "fibrosis_cache"
DEFAULT_MODES: Tuple[str, ...] = ("roi_masked_bbox", "fan")
CACHE_SIZE: int = 320

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger: logging.Logger = logging.getLogger("SmartLiva.FibrosisCache")


def cache_path(mode: str, image_name: str, root: Path = CACHE_ROOT) -> Path:
    """Return the cache location for one image under one preprocessing mode."""
    return root / mode / f"{image_name}.png"


def _build_one(args: Tuple[str, Optional[str], str, str, int, bool]) -> Tuple[str, bool, str]:
    """Worker: preprocess a single image into the cache. Returns (name, ok, message)."""
    img_path, mask_path, image_name, mode, size, clahe = args
    try:
        out: Path = cache_path(mode, image_name)
        processed = preprocess_image(img_path, mask_path, mode=mode, size=size, clahe=clahe)
        cv2.imwrite(str(out), processed)
        return image_name, True, ""
    except Exception as err:  # a single unreadable file must not kill the whole build
        return image_name, False, str(err)


def build_mode(
    df: pd.DataFrame,
    mode: str,
    size: int = CACHE_SIZE,
    clahe: bool = False,
    workers: int = 4,
    overwrite: bool = False,
) -> int:
    """Populate the cache for one input mode. Returns the number of failures."""
    out_dir: Path = CACHE_ROOT / mode
    out_dir.mkdir(parents=True, exist_ok=True)

    jobs: List[Tuple[str, Optional[str], str, str, int, bool]] = []
    for _, row in df.iterrows():
        name: str = row["image_name"]
        if not overwrite and cache_path(mode, name).exists():
            continue
        mask: Optional[str] = row.get("mask_path")
        jobs.append((row["img_path"], mask, name, mode, size, clahe))

    if not jobs:
        logger.info(f"[{mode}] cache already complete ({len(df)} images)")
        return 0

    logger.info(f"[{mode}] building {len(jobs)} images at {size}x{size} (clahe={clahe})")

    failures: int = 0
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_build_one, job) for job in jobs]
        for i, future in enumerate(as_completed(futures), 1):
            name, ok, message = future.result()
            if not ok:
                failures += 1
                logger.warning(f"[{mode}] failed on {name}: {message}")
            if i % 500 == 0:
                logger.info(f"[{mode}] {i}/{len(jobs)}")

    logger.info(f"[{mode}] done, {failures} failures")
    return failures


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the preprocessed fibrosis image cache")
    parser.add_argument("--modes", nargs="+", default=list(DEFAULT_MODES), choices=list(INPUT_MODES))
    parser.add_argument("--size", type=int, default=CACHE_SIZE)
    parser.add_argument("--clahe", action="store_true", help="Apply CLAHE when caching (ablation arm)")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--include_test", action="store_true", help="Also cache the 433 blind-test images")
    args = parser.parse_args()

    train_df: pd.DataFrame = load_train_labels()
    frames: List[pd.DataFrame] = [train_df[["image_name", "img_path", "mask_path"]]]

    if args.include_test:
        test_df: pd.DataFrame = load_test_labels()
        # The blind-test images have no cached U-Net mask; masks are computed on demand.
        test_df["mask_path"] = None
        frames.append(test_df[["image_name", "img_path", "mask_path"]])

    df: pd.DataFrame = pd.concat(frames).drop_duplicates("image_name").reset_index(drop=True)
    logger.info(f"Caching {len(df)} unique images into {CACHE_ROOT}")

    total_failures: int = 0
    for mode in args.modes:
        total_failures += build_mode(
            df, mode, size=args.size, clahe=args.clahe, workers=args.workers, overwrite=args.overwrite
        )

    for mode in args.modes:
        n_cached: int = len(list((CACHE_ROOT / mode).glob("*.png")))
        print(f"{mode:20s} {n_cached} images cached")

    if total_failures:
        logger.warning(f"Completed with {total_failures} failures")


if __name__ == "__main__":
    main()
