"""Pre-resize the corpus into uint8 memmaps so training is not I/O bound.

Every epoch would otherwise decode 7,506 JPEGs at up to 1301x898 and rasterize
12,977 polygons, on a 10-core laptop CPU feeding an MPS device. That work is
identical every epoch and dominates wall time, so it is done once here.

Layout, indexed by row order in the manifest:
    images.u8  (N, 256, 256, 3)  RGB, resized with PIL bicubic
    masks.u8   (N, 256, 256)     {0, 1, 2}, resized nearest-neighbour
    index.json                   patient / view / split / class flags per row

Two details that matter for comparability:

- Images are resized exactly the way model_sdk.predict_mask resizes them (PIL
  bicubic to 256). Arm B fine-tunes the SDK checkpoint, so the pixels it trains on
  have to come off the same path as the pixels arm A was measured on, or the
  comparison silently measures a preprocessing change instead of training.

- Masks are rasterized at native resolution and only then downsampled, never
  rasterized directly at 256. Drawing a polygon into a 256px canvas would quantize
  the contour before the mask exists; downsampling an already-correct mask loses
  only what the resolution cannot hold either way.

The cache is also the artifact to upload if training ever moves to a cloud GPU:
256x256 uint8 arrays indexed by integer row, with no DICOM UIDs, no patient
directory structure, no original resolution and no EXIF. That is de-identification
by construction -- though downsampling is not consent, so the data agreement still
governs.
"""

import argparse
import csv
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
from PIL import Image

from views import DATA_ROOT, REPORTS_DIR
from manifest import MANIFEST_CSV
from rasterize import rasterize_file
from splits_seg import load_split

CACHE_DIR: Path = Path(__file__).resolve().parent.parent.parent / "outputs" / "seg_cache"
CACHE_SIZE: int = 256
REPO_ROOT: Path = DATA_ROOT.parent.parent

IMAGES_PATH: Path = CACHE_DIR / "images.u8"
MASKS_PATH: Path = CACHE_DIR / "masks.u8"
INDEX_PATH: Path = CACHE_DIR / "index.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger: logging.Logger = logging.getLogger("SmartLiva.SegCache")


def build(size: int = CACHE_SIZE, overwrite: bool = False) -> Dict[str, Any]:
    """Write the image and mask memmaps plus their index."""
    if INDEX_PATH.exists() and not overwrite:
        raise FileExistsError(
            f"{INDEX_PATH} already exists. Pass --overwrite to rebuild -- and note that "
            f"a stale cache is the kind of bug that silently trains on the wrong pixels."
        )

    with MANIFEST_CSV.open(encoding="utf-8", newline="") as handle:
        rows: List[Dict[str, str]] = list(csv.DictReader(handle))
    split_of_patient = load_split()

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    n: int = len(rows)
    images = np.lib.format.open_memmap(
        IMAGES_PATH, mode="w+", dtype=np.uint8, shape=(n, size, size, 3)
    )
    masks = np.lib.format.open_memmap(
        MASKS_PATH, mode="w+", dtype=np.uint8, shape=(n, size, size)
    )

    started: float = time.time()
    for i, row in enumerate(rows):
        image = Image.open(REPO_ROOT / row["img_path"]).convert("RGB")
        images[i] = np.asarray(image.resize((size, size)), dtype=np.uint8)

        native_mask: np.ndarray = rasterize_file(REPO_ROOT / row["json_path"])
        masks[i] = np.asarray(
            Image.fromarray(native_mask).resize((size, size), Image.NEAREST), dtype=np.uint8
        )

        if (i + 1) % 1000 == 0:
            rate: float = (i + 1) / (time.time() - started)
            logger.info(f"  {i + 1}/{n} ({rate:.0f}/s)")

    images.flush()
    masks.flush()

    index: Dict[str, Any] = {
        "size": size,
        "n": n,
        "built_from_manifest": str(MANIFEST_CSV.name),
        "rows": [
            {
                "patient": row["patient"],
                "view": row["view"],
                "split": split_of_patient[row["patient"]],
                "has_liver": int(row["has_liver"]),
                "has_gallbladder": int(row["has_gallbladder"]),
            }
            for row in rows
        ],
    }
    INDEX_PATH.write_text(json.dumps(index), encoding="utf-8")

    elapsed: float = time.time() - started
    logger.info(f"cached {n} images in {elapsed:.0f}s -> {CACHE_DIR}")
    return index


def load_index() -> Dict[str, Any]:
    """Read the cache index, with a message pointing at the fix if it is absent."""
    if not INDEX_PATH.exists():
        raise FileNotFoundError(f"cache not found at {CACHE_DIR}. Run: python cache.py --build")
    return json.loads(INDEX_PATH.read_text(encoding="utf-8"))


def open_arrays() -> tuple:
    """Memory-map the cached arrays read-only."""
    return (
        np.load(IMAGES_PATH, mmap_mode="r"),
        np.load(MASKS_PATH, mmap_mode="r"),
    )


def verify() -> None:
    """Re-derive a sample of rows from source and confirm the cache matches."""
    index = load_index()
    images, masks = open_arrays()
    with MANIFEST_CSV.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == index["n"], f"manifest has {len(rows)} rows, cache has {index['n']}"
    assert images.shape == (index["n"], index["size"], index["size"], 3), f"images {images.shape}"
    assert masks.shape == (index["n"], index["size"], index["size"]), f"masks {masks.shape}"
    logger.info(f"[1/3] OK  shapes match ({index['n']} rows at {index['size']}px)")

    rng = np.random.default_rng(0)
    sample = rng.choice(index["n"], size=25, replace=False)
    for i in sample:
        row = rows[int(i)]
        image = Image.open(REPO_ROOT / row["img_path"]).convert("RGB")
        expected_img = np.asarray(image.resize((index["size"], index["size"])), dtype=np.uint8)
        assert np.array_equal(images[i], expected_img), f"image mismatch at row {i}"

        native = rasterize_file(REPO_ROOT / row["json_path"])
        expected_mask = np.asarray(
            Image.fromarray(native).resize((index["size"], index["size"]), Image.NEAREST),
            dtype=np.uint8,
        )
        assert np.array_equal(masks[i], expected_mask), f"mask mismatch at row {i}"
    logger.info(f"[2/3] OK  {len(sample)} sampled rows re-derive identically from source")

    values = set(np.unique(np.asarray(masks[sample])).tolist())
    assert values <= {0, 1, 2}, f"mask values outside {{0,1,2}}: {sorted(values)}"
    logger.info(f"[3/3] OK  mask values are a subset of {{0, 1, 2}}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the 256px training cache")
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--size", type=int, default=CACHE_SIZE)
    args = parser.parse_args()

    if args.build:
        index = build(size=args.size, overwrite=args.overwrite)
        counts: Dict[str, int] = {}
        for row in index["rows"]:
            counts[row["split"]] = counts.get(row["split"], 0) + 1
        print(f"\ncached {index['n']} rows at {index['size']}px: {counts}")
        total_bytes = IMAGES_PATH.stat().st_size + MASKS_PATH.stat().st_size
        print(f"on disk: {total_bytes / 1e9:.2f} GB")

    if args.verify:
        verify()

    if not args.build and not args.verify:
        parser.print_help()


if __name__ == "__main__":
    main()
