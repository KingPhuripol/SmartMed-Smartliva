"""Liver fibrosis label table: parse train/test CSVs and group images into exams.

This module is the single source of truth for fibrosis labels. Two facts drive its design:

1. `TE result` is a deterministic binning of `TE(kPa)` with zero overlap between stages
   (F0 2.4-5.9, F1 6.0-7.0, F2 7.1-8.6, F3 8.7-10.2, F4 10.3-46.0), so the continuous
   kPa value is the richer training target and the stage is derived from it.

2. The `subject` column is NOT a patient id -- it is a clinic session / scan day.
   Within-subject time spans measured from the ObjectId timestamps have a median of
   145 s and never cross a day, and 113 subjects carry more than one distinct kPa
   value. Images must therefore be grouped into *exams* by a temporal gap before any
   per-patient aggregation, or a single "patient" would mix an F0 and an F4 case.
   Cross-validation still groups by `subject`, which is the conservative superset.
"""

import argparse
import bisect
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
DATA_ROOT: Path = BASE_DIR / "data" / "liver-fibrosis-severity-prediction"
TRAIN_CSV: Path = DATA_ROOT / "train.csv"
TEST_CSV: Path = DATA_ROOT / "test_submission.csv"
IMAGES_DIR: Path = DATA_ROOT / "images" / "images"
MASKS_DIR: Path = DATA_ROOT / "liver_masks"

# Clinical TE cutoffs (kPa) separating METAVIR stages, and the midpoint bin edges
# used to assign a stage. Verified to reproduce `TE result` for all 1,772 train rows.
TE_THRESHOLDS: Tuple[float, ...] = (6.0, 7.1, 8.7, 10.3)
STAGE_EDGES: Tuple[float, ...] = (5.95, 7.05, 8.65, 10.25)
STAGES: Tuple[str, ...] = ("F0", "F1", "F2", "F3", "F4")

# `SWE fibrosis stage` is a second, independent elastography label. F0 and F1 are
# collapsed by the acquisition protocol, and 46 rows are missing (encoded as "-").
SWE_STAGES: Tuple[str, ...] = ("F0-1", "F2", "F3", "F4")
VIEWS: Tuple[str, ...] = ("Intercostal", "Liver/RK", "Subcostal_hepatic_vein")

DEFAULT_GAP_S: int = 300

# Expected exam-level counts at DEFAULT_GAP_S -- the Phase 0 go/no-go gate.
EXPECTED_EXAM_COUNTS: Dict[str, int] = {"F0": 497, "F1": 105, "F2": 48, "F3": 37, "F4": 43}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger: logging.Logger = logging.getLogger("SmartLiva.FibrosisLabels")


def kpa_to_stage(kpa: float) -> str:
    """Map a transient-elastography stiffness value (kPa) to its METAVIR stage."""
    return STAGES[bisect.bisect_left(STAGE_EDGES, kpa)]


def stage_to_index(stage: str) -> int:
    """Map a stage string ("F0".."F4") to its ordinal index 0..4."""
    return STAGES.index(stage)


def objectid_timestamp(image_name: str) -> int:
    """Decode the acquisition Unix timestamp from the leading 4 bytes of an ObjectId.

    Image filenames are 24-hex-character MongoDB ObjectIds whose first 8 hex chars
    encode the creation time in seconds. This is the only acquisition-time signal in
    the dataset and it is what makes exam clustering possible.
    """
    return int(image_name[:8], 16)


def _clean_swe(raw: str) -> Optional[str]:
    """Normalize a raw `SWE fibrosis stage` cell: strip whitespace, "-" becomes None."""
    value: str = str(raw).strip()
    return None if value in ("-", "", "nan") else value


def assign_exams(df: pd.DataFrame, gap_s: int = DEFAULT_GAP_S) -> pd.DataFrame:
    """Group rows into exams by temporal proximity within a subject.

    A new exam starts whenever the subject changes or the gap to the previous image
    exceeds `gap_s`. The resulting cluster is then further split by kPa, because a
    session can contain two patients scanned back to back with no measurable gap.
    """
    df = df.sort_values(["subject", "ts"], kind="mergesort").reset_index(drop=True)

    cluster_indices: List[int] = []
    prev_subject: Optional[str] = None
    prev_ts: int = 0
    cluster: int = 0

    for subject, ts in zip(df["subject"], df["ts"]):
        if subject != prev_subject:
            cluster = 0
        elif ts - prev_ts > gap_s:
            cluster += 1
        cluster_indices.append(cluster)
        prev_subject, prev_ts = subject, int(ts)

    df["cluster_idx"] = cluster_indices
    # Embedding kPa in the exam id performs the sub-split: two patients sharing one
    # temporal cluster differ in kPa and therefore land in different exams.
    df["exam_id"] = (
        df["subject"].astype(str)
        + "_"
        + df["cluster_idx"].astype(str)
        + "_"
        + df["kpa"].map(lambda v: f"{v:g}")
    )
    return df


def load_train_labels(gap_s: int = DEFAULT_GAP_S) -> pd.DataFrame:
    """Load train.csv into the canonical label table used by every downstream script."""
    raw: pd.DataFrame = pd.read_csv(TRAIN_CSV)

    df = pd.DataFrame(
        {
            "subject": raw["subject"].astype(str),
            "image_name": raw["image_name"].astype(str),
            "view": raw["view"].astype(str).str.strip(),
            "swe_stage": raw["SWE fibrosis stage"].map(_clean_swe),
            "kpa": raw["TE(kPa)"].astype(float),
            "te_stage_csv": raw["TE result"].astype(str).str.strip(),
        }
    )
    df["te_stage"] = df["kpa"].map(kpa_to_stage)
    df["stage_index"] = df["te_stage"].map(stage_to_index)
    df["ts"] = df["image_name"].map(objectid_timestamp)
    df["img_path"] = df["image_name"].map(lambda n: str(IMAGES_DIR / f"{n}.png"))
    df["mask_path"] = df["image_name"].map(lambda n: str(MASKS_DIR / f"{n}.png"))

    return assign_exams(df, gap_s=gap_s)


def load_test_labels() -> pd.DataFrame:
    """Load test_submission.csv (the blind split -- no target, unusable for evaluation).

    `image_name` is preserved verbatim: one row is literally
    "5e4b507fe13823298400053d (1)", trailing space and parenthesis included.
    """
    raw: pd.DataFrame = pd.read_csv(TEST_CSV)

    df = pd.DataFrame(
        {
            "image_name": raw["image_name"].astype(str),
            "view": raw["view"].astype(str).str.strip(),
            "swe_stage": raw["SWE fibrosis stage"].map(_clean_swe),
            "kpa": pd.to_numeric(raw["TE(kPa)"], errors="coerce"),
        }
    )
    df["img_path"] = df["image_name"].map(lambda n: str(IMAGES_DIR / f"{n}.png"))
    return df


def exam_table(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse the image-level table to one row per exam -- the unit of evaluation."""
    grouped = df.groupby("exam_id", sort=True)
    exams = pd.DataFrame(
        {
            "subject": grouped["subject"].first(),
            "kpa": grouped["kpa"].first(),
            "te_stage": grouped["te_stage"].first(),
            "stage_index": grouped["stage_index"].first(),
            "n_images": grouped.size(),
            "views": grouped["view"].apply(lambda s: "|".join(sorted(set(s)))),
            "ts": grouped["ts"].min(),
        }
    ).reset_index()
    return exams


def audit(gap_s: int = DEFAULT_GAP_S) -> None:
    """Run the Phase 0 verification gate. Raises AssertionError on any failure."""
    df: pd.DataFrame = load_train_labels(gap_s=gap_s)
    test_df: pd.DataFrame = load_test_labels()

    # 1. The derived stage must reproduce the CSV's own `TE result` column exactly.
    mismatches: int = int((df["te_stage"] != df["te_stage_csv"]).sum())
    assert mismatches == 0, f"kpa_to_stage disagrees with TE result on {mismatches} rows"
    logger.info(f"[1/5] OK  derived stage == TE result for all {len(df)} rows")

    # 2. Every training row must have both its image and its U-Net mask on disk.
    missing_imgs: int = sum(1 for p in df["img_path"] if not Path(p).exists())
    missing_masks: int = sum(1 for p in df["mask_path"] if not Path(p).exists())
    assert missing_imgs == 0, f"{missing_imgs} training images missing on disk"
    assert missing_masks == 0, f"{missing_masks} liver masks missing on disk"
    logger.info(f"[2/5] OK  all {len(df)} images and masks present on disk")

    # 3. Exam clustering must leave every exam with a single stiffness value.
    impure: int = int((df.groupby("exam_id")["kpa"].nunique() > 1).sum())
    assert impure == 0, f"{impure} exams contain more than one kPa value"
    logger.info("[3/5] OK  every exam carries exactly one kPa value")

    # 4. Exam-level class counts are the go/no-go gate for the whole project.
    exams: pd.DataFrame = exam_table(df)
    counts: Dict[str, int] = {s: int((exams["te_stage"] == s).sum()) for s in STAGES}
    assert counts == EXPECTED_EXAM_COUNTS, f"exam counts {counts} != {EXPECTED_EXAM_COUNTS}"
    logger.info(f"[4/5] OK  {len(exams)} exams, class counts match expectation")

    # 5. SWE values must normalize to the four known stages plus None.
    swe_values = set(df["swe_stage"].dropna().unique())
    assert swe_values == set(SWE_STAGES), f"unexpected SWE values: {swe_values}"
    logger.info(f"[5/5] OK  SWE values normalize to {sorted(swe_values)} (+ None)")

    _print_summary(df, exams, test_df)


def _print_summary(df: pd.DataFrame, exams: pd.DataFrame, test_df: pd.DataFrame) -> None:
    """Print the label-table summary a human should sanity-check before Phase 1."""
    n_exams: int = len(exams)

    print("\n=== Fibrosis label table ===")
    print(f"images (train)   : {len(df)}")
    print(f"subjects         : {df['subject'].nunique()}")
    print(f"exams            : {n_exams}")
    print(f"images (blind test, no target): {len(test_df)}")

    print("\nstage         images   exams   kPa range")
    for stage in STAGES:
        img_rows = df[df["te_stage"] == stage]
        n_ex: int = int((exams["te_stage"] == stage).sum())
        print(
            f"  {stage}        {len(img_rows):6d}  {n_ex:6d}   "
            f"{img_rows['kpa'].min():5.1f} - {img_rows['kpa'].max():5.1f}"
        )

    print("\nexam-level prevalence (the endpoints we actually report)")
    for threshold, name in ((2, ">=F2 significant"), (3, ">=F3 advanced"), (4, "F4 cirrhosis")):
        n_pos: int = int((exams["stage_index"] >= threshold).sum())
        print(f"  {name:18s} {n_pos:4d} / {n_exams}  ({n_pos / n_exams * 100:.1f}%)")

    print("\nimages per exam:", dict(sorted(exams["n_images"].value_counts().items())))
    print("views          :", dict(df["view"].value_counts()))
    print(f"SWE missing    : {int(df['swe_stage'].isna().sum())} rows")

    # Images present on disk but absent from both CSVs -- excluded from all work.
    labelled = set(df["image_name"]) | set(test_df["image_name"])
    orphans: List[str] = sorted(p.stem for p in IMAGES_DIR.glob("*.png") if p.stem not in labelled)
    print(f"unlabelled orphan images: {len(orphans)} (excluded)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fibrosis label table builder and auditor")
    parser.add_argument("--audit", action="store_true", help="Run the Phase 0 verification gate")
    parser.add_argument("--gap_s", type=int, default=DEFAULT_GAP_S, help="Exam clustering time gap (seconds)")
    parser.add_argument("--sweep_gap", action="store_true", help="Show exam counts across candidate gaps")
    parser.add_argument("--out", type=Path, default=None, help="Optional CSV path to write the label table")
    args = parser.parse_args()

    if args.sweep_gap:
        base: pd.DataFrame = load_train_labels(gap_s=args.gap_s)
        print("gap_s   exams   impure_clusters")
        for gap in (60, 120, 180, 300, 600, 1200):
            clustered = assign_exams(base.copy(), gap_s=gap)
            n_clusters = clustered.groupby(["subject", "cluster_idx"]).ngroups
            impure = int((clustered.groupby(["subject", "cluster_idx"])["kpa"].nunique() > 1).sum())
            print(f"{gap:5d}   {clustered['exam_id'].nunique():5d}   {impure:3d}  (raw clusters {n_clusters})")
        return

    if args.audit:
        audit(gap_s=args.gap_s)
    else:
        df = load_train_labels(gap_s=args.gap_s)
        _print_summary(df, exam_table(df), load_test_labels())

    if args.out:
        df = load_train_labels(gap_s=args.gap_s)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(args.out, index=False)
        logger.info(f"Wrote label table to: {args.out}")


if __name__ == "__main__":
    main()
