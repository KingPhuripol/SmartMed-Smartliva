"""Rasterize LabelMe-style polygon annotations into integer class masks.

The corpus ships two representations of every annotation: the JSON polygons and a
co-located colour-coded PNG. This module treats the JSON as authoritative and the
PNG as a cross-check, for three reasons:

1. The JSON carries the class label. The PNG encodes it as a colour (white liver,
   green gallbladder) that has to be re-derived, and a colour that is nearly but not
   exactly (0,255,0) would silently become background.

2. The PNGs are stored inconsistently -- some RGB, some RGBA -- so any reader has to
   normalize channel count anyway.

3. The JSON is what a re-annotation would update. A mask regenerated from polygons
   cannot drift out of sync with the labels it was drawn from.

`audit_against_png()` measures how far apart the two representations actually are.
If they agree, the choice above costs nothing and the PNGs are confirmed derived; if
they disagree, that is a labelling bug worth knowing about before training on it.

Draw order is liver, then gallbladder. On the 2,465 images carrying both, the
gallbladder sits inside or against the liver contour, so last-write-wins must be
deterministic or the gallbladder would be partly swallowed depending on the order
the annotator happened to click.
"""

import argparse
import json
import logging
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

from views import (
    BACKGROUND,
    CLASS_NAMES,
    DATA_ROOT,
    GALLBLADDER,
    LIVER,
    MIN_POLYGON_AREA_PX,
    REPORTS_DIR,
    label_to_class,
)
from manifest import iter_annotation_files, polygon_area

AUDIT_PATH: Path = REPORTS_DIR / "raster_audit.json"
DEFAULT_AUDIT_N: int = 200

# Class order for drawing. Later entries paint over earlier ones.
DRAW_ORDER: Tuple[int, ...] = (LIVER, GALLBLADDER)

# PNG colour encoding, as BGR (cv2 channel order). Verified over the corpus: the
# only non-black colours present are pure white and pure green.
PNG_COLOURS: Dict[int, Tuple[int, int, int]] = {
    LIVER: (255, 255, 255),
    GALLBLADDER: (0, 255, 0),
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger: logging.Logger = logging.getLogger("SmartLiva.SegRasterize")


def rasterize(payload: Dict[str, Any]) -> np.ndarray:
    """Render one annotation payload into a uint8 mask with values {0, 1, 2}.

    The canvas is sized from the JSON's own imageHeight/imageWidth, which
    manifest.audit() gate 7 has verified equals the JPEG's size for every image.
    """
    height: int = int(payload["imageHeight"])
    width: int = int(payload["imageWidth"])
    mask: np.ndarray = np.full((height, width), BACKGROUND, dtype=np.uint8)

    by_class: Dict[int, List[np.ndarray]] = {class_index: [] for class_index in DRAW_ORDER}
    for shape in payload.get("shapes", []):
        points = shape.get("points", [])
        if polygon_area(points) < MIN_POLYGON_AREA_PX:
            continue
        class_index: int = label_to_class(shape.get("label"))
        # Clip to canvas: a handful of polygons have vertices a pixel or two outside
        # the frame, which fillPoly would otherwise wrap or drop.
        contour = np.clip(
            np.asarray(points, dtype=np.float64).round().astype(np.int32),
            (0, 0),
            (width - 1, height - 1),
        )
        by_class[class_index].append(contour)

    for class_index in DRAW_ORDER:
        contours = by_class[class_index]
        if contours:
            cv2.fillPoly(mask, contours, color=int(class_index))

    return mask


def rasterize_file(json_path: Path) -> np.ndarray:
    """Read one annotation file and rasterize it."""
    return rasterize(json.loads(json_path.read_text(encoding="utf-8")))


def decode_png_mask(png_path: Path) -> Optional[np.ndarray]:
    """Decode a colour-coded PNG mask into the same {0, 1, 2} encoding.

    Returns None if the file cannot be read. Channel count varies across the corpus
    (some RGB, some RGBA), so alpha is dropped and only the colour planes compared.
    """
    raw: Optional[np.ndarray] = cv2.imread(str(png_path), cv2.IMREAD_UNCHANGED)
    if raw is None:
        return None
    if raw.ndim == 2:
        # Greyscale: treat any non-zero pixel as liver -- no colour to distinguish with.
        return np.where(raw > 127, LIVER, BACKGROUND).astype(np.uint8)

    bgr: np.ndarray = raw[:, :, :3]
    mask: np.ndarray = np.full(bgr.shape[:2], BACKGROUND, dtype=np.uint8)
    # Green before white: pure green is unambiguous, whereas an anti-aliased edge
    # pixel can be near-white, so white is matched with a looser test afterwards.
    mask[np.all(bgr == PNG_COLOURS[GALLBLADDER], axis=-1)] = GALLBLADDER
    mask[np.all(bgr >= 200, axis=-1)] = LIVER
    return mask


def class_iou(a: np.ndarray, b: np.ndarray, class_index: int) -> Optional[float]:
    """IoU for one class between two integer masks. None if the class is in neither."""
    lhs, rhs = a == class_index, b == class_index
    union: int = int((lhs | rhs).sum())
    if union == 0:
        return None
    return float((lhs & rhs).sum()) / union


def boundary_fraction(
    a: np.ndarray, b: np.ndarray, class_index: int, tolerance: float = 2.0
) -> Optional[float]:
    """Fraction of disagreeing pixels lying within `tolerance` px of the boundary.

    This is what separates "the two renderers disagree about edge pixels" from "the
    two sources disagree about where the organ is". cv2.fillPoly and the annotation
    tool's own rasterizer differ by roughly half a pixel on whether a boundary pixel
    is inside the polygon, which produces a thin symmetric rim and nothing else. A
    value near 1.0 means the disagreement is entirely that artifact; a lower value
    would mean a real labelling discrepancy and should stop the pipeline.
    """
    lhs, rhs = a == class_index, b == class_index
    disagreement: np.ndarray = np.logical_xor(lhs, rhs)
    if not disagreement.any():
        return 1.0
    reference: np.ndarray = rhs.astype(np.uint8)
    edges: np.ndarray = cv2.morphologyEx(reference, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8))
    distance: np.ndarray = cv2.distanceTransform((1 - edges).astype(np.uint8), cv2.DIST_L2, 3)
    return float((distance[disagreement] <= tolerance).mean())


def audit_against_png(
    n_samples: int = DEFAULT_AUDIT_N, seed: int = 42
) -> Dict[str, Any]:
    """Compare rasterized polygons against the shipped PNG masks on a random sample.

    Reports per-class IoU so a systematic disagreement in one class (which is what a
    colour-encoding mistake would look like) is not averaged away by the other.
    """
    files: List[Path] = list(iter_annotation_files())
    rng = random.Random(seed)
    sample: List[Path] = rng.sample(files, min(n_samples, len(files)))

    per_class: Dict[str, List[float]] = {name: [] for name in CLASS_NAMES[1:]}
    per_class_boundary: Dict[str, List[float]] = {name: [] for name in CLASS_NAMES[1:]}
    unreadable: List[str] = []
    worst: List[Tuple[float, str, str]] = []

    for json_path in sample:
        png_mask = decode_png_mask(json_path.with_suffix(".png"))
        if png_mask is None:
            unreadable.append(str(json_path.relative_to(DATA_ROOT)))
            continue

        own_mask = rasterize_file(json_path)
        if own_mask.shape != png_mask.shape:
            unreadable.append(
                f"{json_path.relative_to(DATA_ROOT)} (shape {own_mask.shape} vs {png_mask.shape})"
            )
            continue

        for class_index, name in enumerate(CLASS_NAMES):
            if class_index == BACKGROUND:
                continue
            iou = class_iou(own_mask, png_mask, class_index)
            if iou is not None:
                per_class[name].append(iou)
                boundary = boundary_fraction(own_mask, png_mask, class_index)
                if boundary is not None:
                    per_class_boundary[name].append(boundary)
                worst.append((iou, name, str(json_path.relative_to(DATA_ROOT))))

    worst.sort()
    result: Dict[str, Any] = {
        "n_sampled": len(sample),
        "n_compared": len(sample) - len(unreadable),
        "seed": seed,
        "min_polygon_area_px": MIN_POLYGON_AREA_PX,
        "per_class": {
            name: {
                "n": len(values),
                "mean_iou": round(float(np.mean(values)), 6) if values else None,
                "min_iou": round(float(np.min(values)), 6) if values else None,
                # Near 1.0 means every disagreement is a boundary-rendering artifact.
                "mean_boundary_fraction": (
                    round(float(np.mean(per_class_boundary[name])), 6)
                    if per_class_boundary[name]
                    else None
                ),
                "min_boundary_fraction": (
                    round(float(np.min(per_class_boundary[name])), 6)
                    if per_class_boundary[name]
                    else None
                ),
            }
            for name, values in per_class.items()
        },
        "unreadable": unreadable,
        "worst_10": [
            {"iou": round(iou, 6), "class": name, "file": path} for iou, name, path in worst[:10]
        ],
    }
    return result


def _print_audit(result: Dict[str, Any]) -> None:
    """Print the audit so a human can decide whether the two sources agree."""
    print("\n=== Polygon-vs-PNG agreement ===")
    print(f"sampled : {result['n_sampled']}   compared: {result['n_compared']}")
    print("\nclass          n    mean IoU     min IoU   boundary-only (mean/min)")
    for name, stats in result["per_class"].items():
        mean = "n/a" if stats["mean_iou"] is None else f"{stats['mean_iou']:.6f}"
        low = "n/a" if stats["min_iou"] is None else f"{stats['min_iou']:.6f}"
        b_mean = (
            "n/a" if stats["mean_boundary_fraction"] is None
            else f"{stats['mean_boundary_fraction'] * 100:.1f}%"
        )
        b_min = (
            "n/a" if stats["min_boundary_fraction"] is None
            else f"{stats['min_boundary_fraction'] * 100:.1f}%"
        )
        print(f"  {name:12s} {stats['n']:4d}  {mean:>10s}  {low:>10s}   {b_mean:>6s} / {b_min:>6s}")

    print(
        "\nboundary-only near 100% means every polygon-vs-PNG disagreement sits on the\n"
        "contour itself -- a fill-convention difference, not a labelling one. Small\n"
        "objects score lower IoU for the same rim: a 2 px rim costs a 629 px\n"
        "gallbladder far more than a 68,000 px liver."
    )

    if result["unreadable"]:
        print(f"\nunreadable/mismatched: {len(result['unreadable'])}")
        for path in result["unreadable"][:5]:
            print(f"  {path}")

    print("\nlowest-agreement samples:")
    for entry in result["worst_10"][:5]:
        print(f"  IoU {entry['iou']:.6f}  {entry['class']:12s} {entry['file']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Rasterize polygon annotations to class masks")
    parser.add_argument("--audit", action="store_true", help="Compare against the shipped PNG masks")
    parser.add_argument("--n", type=int, default=DEFAULT_AUDIT_N, help="Audit sample size")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=AUDIT_PATH, help="Audit JSON output path")
    parser.add_argument("--show", type=Path, default=None, help="Rasterize one JSON and report it")
    args = parser.parse_args()

    if args.show is not None:
        mask = rasterize_file(args.show)
        print(f"shape  : {mask.shape}")
        print(f"dtype  : {mask.dtype}")
        for class_index, name in enumerate(CLASS_NAMES):
            n_px = int((mask == class_index).sum())
            print(f"  {class_index} {name:12s} {n_px:9d} px  ({n_px / mask.size * 100:5.2f}%)")
        return

    if args.audit:
        result = audit_against_png(n_samples=args.n, seed=args.seed)
        _print_audit(result)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
        logger.info(f"wrote audit to: {args.out}")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
