"""Scan-view and annotation-label vocabulary for the `Normal แยกบริเวณตรวจ` dataset.

This module is the single source of truth for two vocabularies. Both exist because
the raw data does not agree with itself, and resolving that disagreement silently
is the failure mode most likely to invalidate a whole training run.

1. LABEL_MAP collapses five annotation strings onto two classes. The corpus was
   annotated over time by more than one person using at least six versions of
   X-AnyLabeling, and the liver was written three different ways -- `肝` (5,094),
   `肝脏` (3,932), and `Live` (1,308, a truncated "Liver") -- while the gallbladder
   was written two -- `胆囊` (2,121) and `GB` (522). Training on the raw strings
   would silently produce a five-class model whose "liver" class held less than
   half the liver pixels.

   The lookup is deliberately fatal on an unknown string rather than defaulting to
   background. A sixth spelling arriving in a future data drop and quietly becoming
   background is the highest-probability silent failure in this pipeline: it would
   not crash, would not warn, and would show up only as an unexplained drop in
   Dice weeks later.

2. VIEWS names the seven anatomical sections the images are filed under. Their
   meanings are NOT documented anywhere in the source data -- the mapping below is
   inferred from the Chinese annotation labels and standard liver ultrasound
   protocol, and three of the seven are genuinely uncertain. They are recorded here
   so the guess is visible and correctable, not so it can be relied on. Nothing in
   the training or evaluation path depends on what the codes *mean*; they are used
   only as opaque stratification keys.
"""

import logging
from pathlib import Path
from typing import Dict, Tuple

BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
DATA_ROOT: Path = BASE_DIR / "data" / "Normal แยกบริเวณตรวจ"
REPORTS_DIR: Path = Path(__file__).resolve().parent / "reports"

# Segmentation classes, in mask-integer order. Index IS the pixel value.
CLASS_NAMES: Tuple[str, ...] = ("background", "liver", "gallbladder")
BACKGROUND: int = 0
LIVER: int = 1
GALLBLADDER: int = 2

# Every annotation string observed across all 12,977 polygons in all 10,507 files.
# Counts are from the 2026-08-11 census and are asserted in manifest.audit().
LABEL_MAP: Dict[str, int] = {
    "肝": LIVER,          # 5,094 -- "liver", short form
    "肝脏": LIVER,        # 3,932 -- "liver", full form
    "Live": LIVER,        # 1,308 -- truncated "Liver"
    "胆囊": GALLBLADDER,  # 2,121 -- "gallbladder"
    "GB": GALLBLADDER,    #   522 -- "gallbladder", abbreviated
}

# Scan-view codes, ordered by image count (descending) as measured on disk.
VIEWS: Tuple[str, ...] = ("GBH", "RH", "LHP", "FPH", "LHA", "SPH", "LHV")

# Image counts per view. Asserted in manifest.audit() as a regression gate -- if a
# future data drop changes these, the split and every per-view number must be redone.
EXPECTED_VIEW_COUNTS: Dict[str, int] = {
    "GBH": 2559,
    "RH": 2039,
    "LHP": 1448,
    "FPH": 1424,
    "LHA": 1319,
    "SPH": 934,
    "LHV": 784,
}

EXPECTED_TOTAL_IMAGES: int = 10507
EXPECTED_TOTAL_PATIENTS: int = 2415
EXPECTED_TOTAL_POLYGONS: int = 12977

# Minimum polygon area, in pixels, for an annotation to be treated as real.
#
# Three polygons in the corpus are 3-point slivers with areas 0.00, 0.01 and 0.34
# px^2 -- stray clicks left beside a properly drawn outline on the same image. The
# smallest genuine polygon is a 335 px^2 gallbladder, so there is a ~1000x gap with
# nothing in it, and any threshold inside that gap separates the two populations.
# 1.0 is chosen to sit well clear of both edges. Real outlines carry 9-477 vertices
# (mean 72.7), so these three are unambiguous annotation slips, not small organs.
MIN_POLYGON_AREA_PX: float = 1.0
EXPECTED_DEGENERATE_POLYGONS: int = 3

# Images carrying a gallbladder polygon but no liver polygon. All 178 are in GBH.
#
# MEASURED 2026-08-11: these are ANNOTATION GAPS, NOT TRUE NEGATIVES. The liver is
# in the frame; the annotator simply did not outline it. Two independent checks on
# the 28 that landed in val:
#
#   - Predicted liver area on them has median 12.7% of frame (p10 6.9, p90 19.1).
#     Annotated liver area on GBH images that DO carry a liver polygon has median
#     13.5% (p10 7.9, p90 18.6). The distributions are the same.
#   - The predicted region is a single connected component (median largest-component
#     share 1.000), identical to labelled images. A hallucination fragments.
#
# Consequences, and they are not small:
#   - They must be EXCLUDED FROM TRAINING, not used as all-background liver targets.
#     Training on them teaches the model to suppress liver that is genuinely there.
#   - They must be excluded from liver Dice, which they already are.
#   - No "does the model hallucinate liver on non-liver input" claim can be made from
#     this corpus. It contains no true negatives. Answering that needs the SDK's
#     10-organ router, or at minimum its thyroid counter-example.
EXPECTED_NO_LIVER_IMAGES: int = 178

# INFERRED, NOT DOCUMENTED. Do not treat as ground truth; confirm with the data
# provider. Recorded so the uncertainty is explicit rather than lost.
VIEW_MEANINGS: Dict[str, str] = {
    "GBH": "Gallbladder section (high confidence -- 2,390 of 2,643 胆囊 polygons are here)",
    "RH": "Right hepatic lobe (high confidence)",
    "FPH": "First porta hepatis / 第一肝门 (high confidence -- pairs with SPH)",
    "SPH": "Second porta hepatis / 第二肝门 (high confidence -- pairs with FPH)",
    "LHA": "Left hepatic lobe, sub-section A (UNCERTAIN -- A may be Anterior or Artery)",
    "LHP": "Left hepatic lobe, sub-section P (UNCERTAIN -- P may be Posterior or Portal)",
    "LHV": "Left hepatic vein (UNCERTAIN)",
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger: logging.Logger = logging.getLogger("SmartLiva.SegViews")


class UnknownAnnotationLabel(KeyError):
    """An annotation string that is not in LABEL_MAP.

    Raised rather than defaulted so that a new spelling stops the build instead of
    silently becoming background. See the module docstring.
    """


def label_to_class(raw_label: str) -> int:
    """Map a raw annotation string to its class index. Fatal on anything unknown."""
    try:
        return LABEL_MAP[raw_label]
    except KeyError:
        raise UnknownAnnotationLabel(
            f"annotation label {raw_label!r} is not in LABEL_MAP. "
            f"Known labels: {sorted(LABEL_MAP)}. Add it to views.LABEL_MAP with the "
            f"class it belongs to -- do not let it fall through to background."
        ) from None


def is_known_view(view: str) -> bool:
    """True if `view` is one of the seven expected scan-view codes."""
    return view in EXPECTED_VIEW_COUNTS


def main() -> None:
    """Print the vocabulary so a human can eyeball it without reading the source."""
    print("\n=== Segmentation classes ===")
    for index, name in enumerate(CLASS_NAMES):
        print(f"  {index}  {name}")

    print("\n=== Annotation labels ===")
    for raw, class_index in LABEL_MAP.items():
        print(f"  {raw!r:>10}  ->  {class_index}  {CLASS_NAMES[class_index]}")

    print(f"\n=== Scan views ({len(VIEWS)}) ===")
    for view in VIEWS:
        print(f"  {view:4s} {EXPECTED_VIEW_COUNTS[view]:5d} images   {VIEW_MEANINGS[view]}")

    print(f"\ntotal images   : {EXPECTED_TOTAL_IMAGES}")
    print(f"total patients : {EXPECTED_TOTAL_PATIENTS}")
    print(f"total polygons : {EXPECTED_TOTAL_POLYGONS}")
    print(f"no-liver images: {EXPECTED_NO_LIVER_IMAGES} (all in GBH)")
    print(f"\ndata root      : {DATA_ROOT}")
    print(f"exists         : {DATA_ROOT.is_dir()}")


if __name__ == "__main__":
    main()
