"""Frozen patient-grouped train/val/test split for liver segmentation.

Grouping is by patient, never by image. This is the single most important property
of the split and the one the previous segmentation training set could not provide:
`models/segmentation/train.py` splits with `random_split` over images and
`collect_samples` carries no subject key at all, so its val_dice is leak-inflated by
an unknown amount. Ultrasound patients contribute 1-21 frames each here (median 3),
all sharing a scanner, a gain preset, an operator and a body -- a model can memorise
that signature and score well on a sibling frame without segmenting anything.

Two refinements on top of a plain group split:

1. Patients are merged before splitting when their DICOM study tokens overlap. The
   9th component of the SOP Instance UID is a study-level counter, and 21 of 4,948
   tokens appear under two different `Patient_XXXX` folders -- almost certainly one
   person exported twice rather than two people allocated consecutive UIDs in one
   session. Merging is the conservative reading: if they are two people the split is
   merely slightly coarser, but if they are one person and we do NOT merge, that
   person appears in both train and test. Union-find is used rather than pairwise
   merging because a token chain can link more than two folders.

2. Stratification is on the scan view. The corpus spans 7 views whose sizes differ
   by 3.3x (GBH 2,559 down to LHV 784), and the headline metric is a macro average
   over all 7 -- so a fold missing LHV, or holding 12 of them, would make the number
   both unstable and incomparable across arms.

The split is written once to reports/seg_splits.json and never regenerated. Every
arm of the bake-off reads that file; it is the only thing that makes A, B and C
comparable. The file stores patient pseudonyms and view names only -- no DICOM UIDs
-- so it can be version-controlled while the manifest it derives from cannot.
"""

import argparse
import csv
import json
import logging
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

import numpy as np
from sklearn.model_selection import StratifiedGroupKFold

from views import EXPECTED_TOTAL_IMAGES, EXPECTED_TOTAL_PATIENTS, REPORTS_DIR, VIEWS
from manifest import MANIFEST_CSV

SPLITS_PATH: Path = REPORTS_DIR / "seg_splits.json"

N_SPLITS: int = 7
SEED: int = 42
TEST_FOLD: int = 0
VAL_FOLD: int = 1

# The 9th dot-separated component of the SOP Instance UID. Verified: all 10,507 UIDs
# have exactly 10 components, and this one is tightly clustered within a patient.
STUDY_TOKEN_INDEX: int = 8

# A held-out fold must carry enough of every view for a per-view Dice to mean
# anything. 1/7 of the smallest view (LHV, 784) is ~112, so 40 leaves ample headroom
# while still failing loudly if a view collapses.
MIN_VIEW_PER_HELDOUT: int = 40

# The 178 no-liver images are the empty-ground-truth safety case. TEST must hold
# enough of them to estimate a false-positive rate at all.
#
# Be honest about what this buys: the realised split puts 16 in test and 28 in val.
# A "90% of no-liver images predict under 1% liver area" gate on n=16 tolerates
# exactly one failure, and its 95% CI spans roughly 60-100% -- it can catch a model
# that hallucinates liver constantly, and cannot distinguish 90% from 99%. Report
# the val figure (n=28) alongside it and state the interval rather than quoting a
# bare percentage. Re-seeding until test held more of them would be split shopping,
# which is exactly what freezing the split exists to prevent.
MIN_NO_LIVER_IN_TEST: int = 15

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger: logging.Logger = logging.getLogger("SmartLiva.SegSplits")


def load_manifest(path: Path = MANIFEST_CSV) -> List[Dict[str, str]]:
    """Read the manifest CSV produced by manifest.py."""
    if not path.exists():
        raise FileNotFoundError(f"manifest not found at {path}. Run: python manifest.py")
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def study_token(uid: str) -> str:
    """Extract the study-level component of a DICOM SOP Instance UID."""
    return uid.split(".")[STUDY_TOKEN_INDEX]


def merge_patients(rows: List[Dict[str, str]]) -> Tuple[Dict[str, str], List[List[str]]]:
    """Union patients that share a DICOM study token.

    Returns (patient -> group representative, list of merged patient clusters). The
    representative is the lexicographically smallest member, so the mapping is
    deterministic across runs.
    """
    parent: Dict[str, str] = {}

    def find(item: str) -> str:
        parent.setdefault(item, item)
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def union(a: str, b: str) -> None:
        root_a, root_b = find(a), find(b)
        if root_a != root_b:
            # Point the larger name at the smaller so the representative is stable.
            low, high = sorted((root_a, root_b))
            parent[high] = low

    by_token: Dict[str, Set[str]] = defaultdict(set)
    for row in rows:
        parent.setdefault(row["patient"], row["patient"])
        by_token[study_token(row["uid"])].add(row["patient"])

    for patients in by_token.values():
        members = sorted(patients)
        for other in members[1:]:
            union(members[0], other)

    mapping: Dict[str, str] = {patient: find(patient) for patient in parent}

    clusters: Dict[str, List[str]] = defaultdict(list)
    for patient, representative in mapping.items():
        clusters[representative].append(patient)
    merged: List[List[str]] = sorted(
        (sorted(members) for members in clusters.values() if len(members) > 1)
    )
    return mapping, merged


def make_split(
    rows: List[Dict[str, str]],
    group_of: Dict[str, str],
    n_splits: int = N_SPLITS,
    seed: int = SEED,
) -> Dict[str, str]:
    """Assign every patient to 'train', 'val' or 'test'.

    StratifiedGroupKFold balances the view distribution across folds while keeping
    every group whole. Fold assignment happens at image level and is then collapsed
    to patients, which is safe precisely because groups are never split.
    """
    view_index: Dict[str, int] = {view: i for i, view in enumerate(VIEWS)}
    y: np.ndarray = np.array([view_index[row["view"]] for row in rows])
    groups: np.ndarray = np.array([group_of[row["patient"]] for row in rows])

    splitter = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    fold_of_row: np.ndarray = np.empty(len(rows), dtype=int)
    for fold, (_, held_out_idx) in enumerate(splitter.split(np.zeros(len(rows)), y, groups)):
        fold_of_row[held_out_idx] = fold

    split_of_patient: Dict[str, str] = {}
    for row, fold in zip(rows, fold_of_row):
        if fold == TEST_FOLD:
            split = "test"
        elif fold == VAL_FOLD:
            split = "val"
        else:
            split = "train"
        split_of_patient[row["patient"]] = split
    return split_of_patient


def validate_split(rows: List[Dict[str, str]], split_of_patient: Dict[str, str],
                   group_of: Dict[str, str]) -> None:
    """Assert the leakage and coverage guarantees. Raises AssertionError on failure."""
    splits: Tuple[str, ...] = ("train", "val", "test")

    # 1. Every image is assigned exactly one split.
    assert len(rows) == EXPECTED_TOTAL_IMAGES, f"manifest has {len(rows)} rows"
    unassigned = [row["patient"] for row in rows if row["patient"] not in split_of_patient]
    assert not unassigned, f"{len(unassigned)} images belong to unassigned patients"
    logger.info(f"[1/5] OK  all {len(rows)} images assigned")

    # 2. No patient appears in two splits -- the property the old split lacked.
    patients_in: Dict[str, Set[str]] = {name: set() for name in splits}
    for row in rows:
        patients_in[split_of_patient[row["patient"]]].add(row["patient"])
    for left in splits:
        for right in splits:
            if left < right:
                shared = patients_in[left] & patients_in[right]
                assert not shared, f"{len(shared)} patients in both {left} and {right}: {sorted(shared)[:5]}"
    total_patients = sum(len(members) for members in patients_in.values())
    assert total_patients == EXPECTED_TOTAL_PATIENTS, f"{total_patients} patients assigned"
    logger.info(f"[2/5] OK  {total_patients} patients, no overlap between splits")

    # 3. Merged groups are never split -- the whole point of the union-find pass.
    group_splits: Dict[str, Set[str]] = defaultdict(set)
    for patient, split in split_of_patient.items():
        group_splits[group_of[patient]].add(split)
    straddling = {group for group, found in group_splits.items() if len(found) > 1}
    assert not straddling, f"{len(straddling)} merged patient groups straddle a split boundary"
    logger.info(f"[3/5] OK  all {len(group_splits)} patient groups kept whole")

    # 4. Both held-out splits carry every view, in usable quantity.
    for held_out in ("val", "test"):
        counts = Counter(
            row["view"] for row in rows if split_of_patient[row["patient"]] == held_out
        )
        missing = set(VIEWS) - set(counts)
        assert not missing, f"{held_out} is missing views: {sorted(missing)}"
        thin = {view: n for view, n in counts.items() if n < MIN_VIEW_PER_HELDOUT}
        assert not thin, f"{held_out} has under {MIN_VIEW_PER_HELDOUT} images for: {thin}"
    logger.info(f"[4/5] OK  val and test each carry all {len(VIEWS)} views (>= {MIN_VIEW_PER_HELDOUT})")

    # 5. Test carries enough empty-ground-truth images to measure the safety metric.
    n_no_liver = sum(
        1
        for row in rows
        if split_of_patient[row["patient"]] == "test" and row["has_liver"] == "0"
    )
    assert n_no_liver >= MIN_NO_LIVER_IN_TEST, (
        f"test holds only {n_no_liver} no-liver images (need {MIN_NO_LIVER_IN_TEST})"
    )
    logger.info(f"[5/5] OK  test holds {n_no_liver} no-liver images")


def load_split(path: Path = SPLITS_PATH) -> Dict[str, str]:
    """Read the frozen patient -> split mapping."""
    if not path.exists():
        raise FileNotFoundError(f"split not found at {path}. Run: python splits_seg.py --freeze")
    return json.loads(path.read_text(encoding="utf-8"))["split_of_patient"]


def _print_summary(rows: List[Dict[str, str]], split_of_patient: Dict[str, str],
                   merged: List[List[str]]) -> None:
    """Print the composition table a human should check before freezing."""
    splits: Tuple[str, ...] = ("train", "val", "test")

    print("\n=== Patient-grouped segmentation split ===")
    print(f"seed {SEED}, {N_SPLITS} folds -> fold {TEST_FOLD} = test, fold {VAL_FOLD} = val, rest = train")

    print("\nsplit    images  patients   w/liver  no-liver  w/gallbladder")
    for name in splits:
        subset = [row for row in rows if split_of_patient[row["patient"]] == name]
        n_patients = len({row["patient"] for row in subset})
        n_liver = sum(1 for row in subset if row["has_liver"] == "1")
        n_gb = sum(1 for row in subset if row["has_gallbladder"] == "1")
        pct = len(subset) / len(rows) * 100
        print(
            f"  {name:6s} {len(subset):6d} ({pct:4.1f}%) {n_patients:6d} "
            f"{n_liver:9d} {len(subset) - n_liver:9d} {n_gb:14d}"
        )

    print("\nview     " + "".join(f"{name:>10s}" for name in splits))
    for view in VIEWS:
        cells = []
        for name in splits:
            n = sum(
                1
                for row in rows
                if row["view"] == view and split_of_patient[row["patient"]] == name
            )
            cells.append(f"{n:10d}")
        print(f"  {view:5s}  " + "".join(cells))

    print(f"\nmerged patient groups: {len(merged)}")
    for members in merged[:25]:
        split_names = sorted({split_of_patient[m] for m in members})
        print(f"  {' + '.join(members):45s} -> {','.join(split_names)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and freeze the segmentation split")
    parser.add_argument("--freeze", action="store_true", help="Write seg_splits.json (refuses to overwrite)")
    parser.add_argument("--force", action="store_true", help="Allow overwriting an existing seg_splits.json")
    parser.add_argument("--validate", action="store_true", help="Validate the frozen split and exit")
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--n_splits", type=int, default=N_SPLITS)
    parser.add_argument("--out", type=Path, default=SPLITS_PATH)
    args = parser.parse_args()

    rows = load_manifest()
    group_of, merged = merge_patients(rows)
    n_groups = len(set(group_of.values()))
    logger.info(
        f"{len(rows)} images, {len({r['patient'] for r in rows})} patients, "
        f"{n_groups} groups after merging {len(merged)} clusters"
    )

    if args.validate or (args.out.exists() and not args.force):
        if args.freeze and args.out.exists():
            logger.warning(
                f"{args.out} already exists. The split is frozen by design -- regenerating "
                "it invalidates every arm measured against it. Use --force to override."
            )
        split_of_patient = load_split(args.out)
        validate_split(rows, split_of_patient, group_of)
        _print_summary(rows, split_of_patient, merged)
        return

    split_of_patient = make_split(rows, group_of, n_splits=args.n_splits, seed=args.seed)
    validate_split(rows, split_of_patient, group_of)
    _print_summary(rows, split_of_patient, merged)

    if args.freeze:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        counts = Counter(split_of_patient.values())
        payload: Dict[str, Any] = {
            "created_with": {
                "seed": args.seed,
                "n_splits": args.n_splits,
                "test_fold": TEST_FOLD,
                "val_fold": VAL_FOLD,
                "group_by": "patient, unioned on shared DICOM study token",
                "stratify_by": "scan view",
                "n_images": len(rows),
                "n_patients": len(split_of_patient),
                "n_groups": n_groups,
                "patients_per_split": dict(sorted(counts.items())),
            },
            "merged_patient_groups": merged,
            "split_of_patient": dict(sorted(split_of_patient.items())),
        }
        args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        logger.info(f"Froze split -> {args.out}")


if __name__ == "__main__":
    main()
