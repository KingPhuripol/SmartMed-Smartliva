"""Frozen cross-validation folds for fibrosis staging.

Grouping is by `subject`, not by exam and never by image. A subject is one clinic
session, so its images share a scanner, an operator, a gain preset and a day -- all of
which are label-correlated in this dataset. Grouping by subject is a strict superset of
grouping by exam and is the conservative choice.

Stratification is on the exam-level stage, because with 37 F3 and 43 F4 exams an
unstratified split would produce validation folds containing almost none of them.

The folds are written once to reports/folds.json and never regenerated. Every model,
baseline, ablation and negative control reads that file, which is the only thing that
makes their scores comparable at this sample size.
"""

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedGroupKFold

from labels import STAGES, exam_table, load_train_labels

BASE_DIR: Path = Path(__file__).resolve().parent
FOLDS_PATH: Path = BASE_DIR / "reports" / "folds.json"

N_SPLITS: int = 5
N_REPEATS: int = 3
SEED: int = 42
INNER_SPLITS: int = 4

# Minimum minority-class exams a validation fold must contain for its AUROC to mean
# anything. 5-fold over 37 F3 / 43 F4 exams gives roughly 7 and 9.
MIN_VAL_F3: int = 5
MIN_VAL_F4: int = 6

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger: logging.Logger = logging.getLogger("SmartLiva.FibrosisSplits")


def make_folds(
    exams: pd.DataFrame,
    n_splits: int = N_SPLITS,
    n_repeats: int = N_REPEATS,
    seed: int = SEED,
) -> List[Dict[str, Any]]:
    """Build repeated stratified group folds over exams, returning exam-id lists."""
    exam_ids: np.ndarray = exams["exam_id"].to_numpy()
    y: np.ndarray = exams["stage_index"].to_numpy()
    groups: np.ndarray = exams["subject"].to_numpy()

    folds: List[Dict[str, Any]] = []
    for repeat in range(n_repeats):
        splitter = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=seed + repeat)
        for fold, (train_idx, val_idx) in enumerate(splitter.split(exam_ids, y, groups)):
            folds.append(
                {
                    "repeat": repeat,
                    "fold": fold,
                    "train_exams": exam_ids[train_idx].tolist(),
                    "val_exams": exam_ids[val_idx].tolist(),
                }
            )
    return folds


def inner_folds(
    exams: pd.DataFrame,
    train_exam_ids: List[str],
    n_splits: int = INNER_SPLITS,
    seed: int = SEED,
) -> List[Tuple[List[str], List[str]]]:
    """Split one outer training set again, for early stopping and threshold calibration.

    Every hyperparameter, epoch count, threshold and backbone choice is made on these
    inner folds. The outer validation fold is scored exactly once, at the end.
    """
    subset: pd.DataFrame = exams[exams["exam_id"].isin(set(train_exam_ids))]
    exam_ids: np.ndarray = subset["exam_id"].to_numpy()
    y: np.ndarray = subset["stage_index"].to_numpy()
    groups: np.ndarray = subset["subject"].to_numpy()

    splitter = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    return [
        (exam_ids[tr].tolist(), exam_ids[va].tolist())
        for tr, va in splitter.split(exam_ids, y, groups)
    ]


def validate_folds(exams: pd.DataFrame, folds: List[Dict[str, Any]]) -> None:
    """Assert the leakage and minority-coverage guarantees the folds must provide."""
    by_exam: pd.DataFrame = exams.set_index("exam_id")
    all_exam_ids = set(exams["exam_id"])

    for spec in folds:
        tag: str = f"repeat {spec['repeat']} fold {spec['fold']}"
        train_ids, val_ids = set(spec["train_exams"]), set(spec["val_exams"])

        assert not (train_ids & val_ids), f"{tag}: exam overlap between train and val"
        assert train_ids | val_ids == all_exam_ids, f"{tag}: folds do not cover all exams"

        train_subjects = set(by_exam.loc[sorted(train_ids), "subject"])
        val_subjects = set(by_exam.loc[sorted(val_ids), "subject"])
        shared = train_subjects & val_subjects
        assert not shared, f"{tag}: {len(shared)} subjects leak across the split: {sorted(shared)[:5]}"

        val_stages = by_exam.loc[sorted(val_ids), "te_stage"]
        n_f3, n_f4 = int((val_stages == "F3").sum()), int((val_stages == "F4").sum())
        assert n_f3 >= MIN_VAL_F3, f"{tag}: only {n_f3} F3 exams in validation (need {MIN_VAL_F3})"
        assert n_f4 >= MIN_VAL_F4, f"{tag}: only {n_f4} F4 exams in validation (need {MIN_VAL_F4})"

    logger.info(f"All {len(folds)} folds pass leakage and minority-coverage checks")


def load_folds(path: Path = FOLDS_PATH) -> List[Dict[str, Any]]:
    """Read the frozen fold definitions."""
    if not path.exists():
        raise FileNotFoundError(f"Folds not found at {path}. Run: python splits.py --freeze")
    return json.loads(path.read_text(encoding="utf-8"))["folds"]


def exam_ids_to_image_index(df: pd.DataFrame, exam_ids: List[str]) -> np.ndarray:
    """Map a list of exam ids to positional row indices in the image-level table."""
    return np.flatnonzero(df["exam_id"].isin(set(exam_ids)).to_numpy())


def _fold_summary(exams: pd.DataFrame, folds: List[Dict[str, Any]]) -> None:
    """Print per-fold validation composition so minority counts are never a surprise."""
    by_exam: pd.DataFrame = exams.set_index("exam_id")

    print("\nrepeat fold  n_val  " + "  ".join(f"{s:>4s}" for s in STAGES) + "   n_val_subjects")
    for spec in folds:
        val_ids = sorted(spec["val_exams"])
        stages = by_exam.loc[val_ids, "te_stage"]
        counts = "  ".join(f"{int((stages == s).sum()):4d}" for s in STAGES)
        n_subjects = by_exam.loc[val_ids, "subject"].nunique()
        print(f"{spec['repeat']:6d} {spec['fold']:4d}  {len(val_ids):5d}  {counts}   {n_subjects:6d}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and freeze the fibrosis CV folds")
    parser.add_argument("--freeze", action="store_true", help="Write folds.json (refuses to overwrite)")
    parser.add_argument("--force", action="store_true", help="Allow overwriting an existing folds.json")
    parser.add_argument("--n_splits", type=int, default=N_SPLITS)
    parser.add_argument("--n_repeats", type=int, default=N_REPEATS)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--out", type=Path, default=FOLDS_PATH)
    args = parser.parse_args()

    df: pd.DataFrame = load_train_labels()
    exams: pd.DataFrame = exam_table(df)
    logger.info(f"{len(exams)} exams from {exams['subject'].nunique()} subjects")

    if args.out.exists() and not args.force:
        if args.freeze:
            logger.warning(
                f"{args.out} already exists. Folds are frozen by design -- "
                "regenerating them invalidates every score measured so far. Use --force to override."
            )
        folds = load_folds(args.out)
        validate_folds(exams, folds)
        _fold_summary(exams, folds)
        return

    folds: List[Dict[str, Any]] = make_folds(
        exams, n_splits=args.n_splits, n_repeats=args.n_repeats, seed=args.seed
    )
    validate_folds(exams, folds)
    _fold_summary(exams, folds)

    if args.freeze:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        payload: Dict[str, Any] = {
            "created_with": {
                "n_splits": args.n_splits,
                "n_repeats": args.n_repeats,
                "seed": args.seed,
                "group_by": "subject",
                "stratify_by": "exam stage_index",
                "n_exams": len(exams),
                "n_subjects": int(exams["subject"].nunique()),
            },
            "folds": folds,
        }
        args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        logger.info(f"Froze {len(folds)} folds -> {args.out}")


if __name__ == "__main__":
    main()
