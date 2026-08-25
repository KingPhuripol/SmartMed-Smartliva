"""Build the image-level manifest for the `Normal แยกบริเวณตรวจ` segmentation corpus.

One row per image, with everything the split, the cache, and the evaluator need:
the patient it belongs to, the scan view it was filed under, and which classes are
annotated on it. Every later stage reads this CSV rather than re-walking 31,521
files, and `audit()` is the regression gate that says the corpus on disk is still
the corpus this project was designed around.

Three facts about the raw data drive the parsing:

1. The grouping key is the `Patient_XXXX` directory, not the filename. Filenames are
   DICOM SOP Instance UIDs and are globally unique, so they carry no group signal on
   their own -- but the directory does, and it is the only reason a patient-disjoint
   split is possible at all. The previous segmentation training set had no such key.

2. `imagePath` inside the JSON is not trustworthy. Forty-three files still name a
   ` - 副本.jpg` ("- copy") path that no longer exists because the files were renamed
   afterwards. The image path is therefore derived from the JSON's own filename,
   which is correct for all 10,507 triples.

3. Three polygons are 3-point slivers of 0.00-0.34 px^2 -- stray clicks sitting
   beside a properly drawn outline on the same image. They are counted and dropped
   against views.MIN_POLYGON_AREA_PX rather than left to contribute nothing (or a
   single stray pixel) to a mask. An exact `area == 0` test does not catch them:
   two of the three are near-collinear rather than collinear.
"""

import argparse
import csv
import json
import logging
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from views import (
    CLASS_NAMES,
    DATA_ROOT,
    EXPECTED_DEGENERATE_POLYGONS,
    EXPECTED_NO_LIVER_IMAGES,
    EXPECTED_TOTAL_IMAGES,
    EXPECTED_TOTAL_PATIENTS,
    EXPECTED_TOTAL_POLYGONS,
    EXPECTED_VIEW_COUNTS,
    GALLBLADDER,
    LIVER,
    MIN_POLYGON_AREA_PX,
    REPORTS_DIR,
    UnknownAnnotationLabel,
    label_to_class,
)

MANIFEST_CSV: Path = REPORTS_DIR / "manifest.csv"

FIELDNAMES: Tuple[str, ...] = (
    "patient",
    "view",
    "uid",
    "img_path",
    "json_path",
    "png_path",
    "height",
    "width",
    "n_shapes",
    "n_liver",
    "n_gallbladder",
    "n_degenerate",
    "has_liver",
    "has_gallbladder",
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger: logging.Logger = logging.getLogger("SmartLiva.SegManifest")


def polygon_area(points: List[List[float]]) -> float:
    """Absolute shoelace area of a polygon, in pixels.

    Used only to detect degenerate annotations against MIN_POLYGON_AREA_PX.
    """
    if len(points) < 3:
        return 0.0
    total: float = 0.0
    for i in range(len(points)):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % len(points)]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def iter_annotation_files(data_root: Path = DATA_ROOT) -> Iterator[Path]:
    """Yield every annotation JSON under `Patient_*/<view>/`, sorted for determinism."""
    yield from sorted(data_root.glob("Patient_*/*/*.json"))


def parse_annotation(json_path: Path) -> Optional[Dict[str, Any]]:
    """Parse one annotation file into a manifest row, or None if it is unusable.

    Raises UnknownAnnotationLabel on an unrecognised label string -- that is a stop
    condition for the whole build, not a row to skip.
    """
    try:
        payload: Dict[str, Any] = json.loads(json_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as err:
        logger.error(f"unreadable annotation, skipping: {json_path} ({err})")
        return None

    view: str = json_path.parent.name
    patient: str = json_path.parent.parent.name
    uid: str = json_path.stem

    # Derived from the JSON filename, never from payload["imagePath"] -- see fact 2.
    img_path: Path = json_path.with_suffix(".jpg")
    png_path: Path = json_path.with_suffix(".png")

    counts: Counter = Counter()
    n_degenerate: int = 0
    for shape in payload.get("shapes", []):
        class_index: int = label_to_class(shape.get("label"))
        if polygon_area(shape.get("points", [])) < MIN_POLYGON_AREA_PX:
            n_degenerate += 1
            continue
        counts[class_index] += 1

    return {
        "patient": patient,
        "view": view,
        "uid": uid,
        "img_path": str(img_path.relative_to(DATA_ROOT.parent.parent)),
        "json_path": str(json_path.relative_to(DATA_ROOT.parent.parent)),
        "png_path": str(png_path.relative_to(DATA_ROOT.parent.parent)),
        "height": int(payload.get("imageHeight", 0)),
        "width": int(payload.get("imageWidth", 0)),
        "n_shapes": len(payload.get("shapes", [])),
        "n_liver": counts[LIVER],
        "n_gallbladder": counts[GALLBLADDER],
        "n_degenerate": n_degenerate,
        "has_liver": int(counts[LIVER] > 0),
        "has_gallbladder": int(counts[GALLBLADDER] > 0),
    }


def build_manifest(data_root: Path = DATA_ROOT) -> List[Dict[str, Any]]:
    """Walk the corpus and return one row per annotation file."""
    if not data_root.is_dir():
        raise FileNotFoundError(f"dataset root not found: {data_root}")

    rows: List[Dict[str, Any]] = []
    for json_path in iter_annotation_files(data_root):
        row = parse_annotation(json_path)
        if row is not None:
            rows.append(row)

    logger.info(f"parsed {len(rows)} annotation files from {data_root}")
    return rows


def write_manifest(rows: List[Dict[str, Any]], out_path: Path = MANIFEST_CSV) -> None:
    """Write the manifest CSV, creating the reports directory if needed."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(FIELDNAMES))
        writer.writeheader()
        writer.writerows(rows)
    logger.info(f"wrote manifest to: {out_path}")


def audit(rows: List[Dict[str, Any]]) -> None:
    """Verify the corpus matches what this project was designed around.

    Raises AssertionError on any mismatch. A failure here means the data changed and
    the frozen split, the cache, and every per-view number have to be rebuilt.
    """
    # 1. Total image count.
    assert len(rows) == EXPECTED_TOTAL_IMAGES, (
        f"expected {EXPECTED_TOTAL_IMAGES} images, found {len(rows)}"
    )
    logger.info(f"[1/7] OK  {len(rows)} annotation files")

    # 2. Patient count -- the grouping key that makes a leak-free split possible.
    patients = {row["patient"] for row in rows}
    assert len(patients) == EXPECTED_TOTAL_PATIENTS, (
        f"expected {EXPECTED_TOTAL_PATIENTS} patients, found {len(patients)}"
    )
    logger.info(f"[2/7] OK  {len(patients)} distinct patients")

    # 3. Per-view counts.
    view_counts = Counter(row["view"] for row in rows)
    assert dict(view_counts) == EXPECTED_VIEW_COUNTS, (
        f"view counts {dict(view_counts)} != {EXPECTED_VIEW_COUNTS}"
    )
    logger.info(f"[3/7] OK  all {len(EXPECTED_VIEW_COUNTS)} views match expected counts")

    # 4. Polygon total, and the degenerate slivers dropped out of it.
    n_degenerate = sum(row["n_degenerate"] for row in rows)
    n_polygons = sum(row["n_liver"] + row["n_gallbladder"] for row in rows) + n_degenerate
    assert n_polygons == EXPECTED_TOTAL_POLYGONS, (
        f"expected {EXPECTED_TOTAL_POLYGONS} polygons, found {n_polygons}"
    )
    assert n_degenerate == EXPECTED_DEGENERATE_POLYGONS, (
        f"expected {EXPECTED_DEGENERATE_POLYGONS} degenerate polygons "
        f"(area < {MIN_POLYGON_AREA_PX} px), found {n_degenerate}"
    )
    logger.info(f"[4/7] OK  {n_polygons} polygons, {n_degenerate} degenerate dropped")

    # 5. Images with no liver annotation -- must all be in GBH.
    no_liver = [row for row in rows if not row["has_liver"]]
    assert len(no_liver) == EXPECTED_NO_LIVER_IMAGES, (
        f"expected {EXPECTED_NO_LIVER_IMAGES} no-liver images, found {len(no_liver)}"
    )
    stray_views = {row["view"] for row in no_liver} - {"GBH"}
    assert not stray_views, f"no-liver images appear outside GBH: {sorted(stray_views)}"
    logger.info(f"[5/7] OK  {len(no_liver)} no-liver images, all in GBH")

    # 6. Every triple present on disk. A missing .jpg would fail silently at cache time.
    repo_root: Path = DATA_ROOT.parent.parent
    missing_img = sum(1 for row in rows if not (repo_root / row["img_path"]).is_file())
    missing_png = sum(1 for row in rows if not (repo_root / row["png_path"]).is_file())
    assert missing_img == 0, f"{missing_img} images missing on disk"
    assert missing_png == 0, f"{missing_png} rendered masks missing on disk"
    logger.info(f"[6/7] OK  all {len(rows)} image/mask pairs present on disk")

    # 7. The JSON's declared dimensions must match the actual JPEG. The rasterizer
    # draws polygons into a canvas sized from the JSON, and the cache pairs that
    # canvas with the decoded image -- a mismatch anywhere would silently shift every
    # mask relative to its image. PIL reads the header only, so this is cheap.
    from PIL import Image  # local import: only audit needs it

    dim_mismatches: List[str] = []
    for row in rows:
        with Image.open(repo_root / row["img_path"]) as img:
            if img.size != (row["width"], row["height"]):
                dim_mismatches.append(
                    f"{row['patient']}/{row['view']}/{row['uid']}: "
                    f"json {row['width']}x{row['height']} != jpg {img.size[0]}x{img.size[1]}"
                )
    assert not dim_mismatches, (
        f"{len(dim_mismatches)} images disagree with their JSON dimensions:\n  "
        + "\n  ".join(dim_mismatches[:10])
    )
    logger.info(f"[7/7] OK  JSON dimensions match the JPEG for all {len(rows)} images")


def _print_summary(rows: List[Dict[str, Any]]) -> None:
    """Print the corpus summary a human should sanity-check before freezing a split."""
    patients = Counter(row["patient"] for row in rows)
    view_counts = Counter(row["view"] for row in rows)

    print("\n=== Segmentation corpus ===")
    print(f"images         : {len(rows)}")
    print(f"patients       : {len(patients)}")
    print(f"classes        : {', '.join(f'{i}={n}' for i, n in enumerate(CLASS_NAMES))}")

    print("\nview    images  patients   w/liver  w/gallbladder")
    for view, n_images in view_counts.most_common():
        subset = [row for row in rows if row["view"] == view]
        n_patients = len({row["patient"] for row in subset})
        n_liver = sum(row["has_liver"] for row in subset)
        n_gb = sum(row["has_gallbladder"] for row in subset)
        print(f"  {view:4s} {n_images:7d} {n_patients:9d} {n_liver:9d} {n_gb:14d}")

    n_liver_total = sum(row["has_liver"] for row in rows)
    n_gb_total = sum(row["has_gallbladder"] for row in rows)
    print(f"\nimages with liver       : {n_liver_total}")
    print(f"images with gallbladder : {n_gb_total}")
    print(f"images with neither     : {sum(1 for r in rows if not r['has_liver'] and not r['has_gallbladder'])}")

    print("\nimages per patient:", dict(sorted(Counter(patients.values()).items())))

    degenerate = [row for row in rows if row["n_degenerate"]]
    print(f"\ndegenerate polygons dropped: {sum(r['n_degenerate'] for r in degenerate)} "
          f"across {len(degenerate)} files")
    for row in degenerate:
        print(f"  {row['patient']}/{row['view']}/{row['uid']}")

    heights = [row["height"] for row in rows]
    widths = [row["width"] for row in rows]
    print(f"\nresolution: h {min(heights)}-{max(heights)}, w {min(widths)}-{max(widths)} "
          f"({len({(r['width'], r['height']) for r in rows})} distinct sizes -- resize required)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Segmentation corpus manifest builder and auditor")
    parser.add_argument("--audit", action="store_true", help="Run the corpus verification gate")
    parser.add_argument("--out", type=Path, default=MANIFEST_CSV, help="Manifest CSV output path")
    parser.add_argument("--no-write", action="store_true", help="Summarize without writing the CSV")
    args = parser.parse_args()

    try:
        rows = build_manifest()
    except UnknownAnnotationLabel as err:
        logger.error(f"manifest build aborted: {err}")
        raise SystemExit(1)

    if args.audit:
        audit(rows)

    _print_summary(rows)

    if not args.no_write:
        write_manifest(rows, args.out)


if __name__ == "__main__":
    main()
