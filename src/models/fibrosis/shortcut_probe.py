"""Negative controls: measure how much of the model's score could come from shortcuts.

A fibrosis model trained on 730 exams from a handful of scanners has several ways to
look good without learning anything about liver parenchyma. Each probe trains the same
architecture on the same folds, but on an input that contains only one suspect signal:

* **chrome**   -- everything OUTSIDE the ultrasound sector: burned-in vendor text, depth
                  and gain readouts, timestamps. Should be at chance. If it is not, the
                  fan crop is load-bearing and must stay.
* **mask**     -- the binary liver mask alone, no texture. Separates "the U-Net's outline
                  correlates with disease" from "the parenchyma texture does".
* **metadata** -- image dimensions, view and year, no pixels at all. Reuses B3 from
                  baselines.py.

The rule this enforces: a headline result only counts as evidence about fibrosis if it
beats every probe by more than sampling noise, tested with a paired subject-level
bootstrap on fold-standardised scores. Comparing two separately computed confidence
intervals for overlap would be a weaker test, and comparing raw pooled scores would
penalise whichever method varies more between folds.
"""

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

from sklearn.metrics import roc_auc_score

from evaluate import ENDPOINTS, METRICS_DIR, PRED_DIR, evaluate_run, json_safe, load_predictions
from labels import exam_table, load_train_labels
from model import get_device
from splits import load_folds
from train import train_one_fold

BASE_DIR: Path = Path(__file__).resolve().parent

# probe name -> (cached input mode, run name)
PROBES: Dict[str, Tuple[str, str]] = {
    "chrome": ("chrome", "probe_chrome"),
    "mask": ("mask_only", "probe_mask_shape"),
}
METADATA_RUN: str = "B3_metadata"
VERDICT_PATH: Path = METRICS_DIR / "verdict.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger: logging.Logger = logging.getLogger("SmartLiva.FibrosisProbe")


def _repeats_covered(path: Path) -> int:
    """How many consecutive CV repeats, counting from 0, a predictions CSV contains."""
    try:
        present = set(pd.read_csv(path, usecols=["repeat"])["repeat"].astype(int))
    except Exception:
        return 0
    covered: int = 0
    while covered in present:
        covered += 1
    return covered


def run_probe(
    probe: str,
    df: pd.DataFrame,
    exams: pd.DataFrame,
    folds: List[Dict[str, Any]],
    args: argparse.Namespace,
) -> Path:
    """Train one probe over the selected folds and write its predictions."""
    mode, run_name = PROBES[probe]
    path: Path = args.out_dir / f"{run_name}.csv"

    # A probe costs about as much as the headline run, so an existing predictions file is
    # reused by default. Re-running the verdict after changing how it is computed should
    # not retrain the controls.
    #
    # Reuse is only valid if the file already covers every repeat being asked for. A probe
    # measured on fewer folds than the headline is exactly what made the first verdict
    # ambiguous, and reusing a 5-fold CSV under --repeats 3 would report that weaker
    # comparison as though it were the stronger one.
    if path.exists() and not getattr(args, "force_retrain", False):
        covered: int = _repeats_covered(path)
        if covered >= args.repeats:
            logger.info(f"Probe '{probe}': reusing {path} (pass --force_retrain to train again)")
            return path
        logger.info(
            f"Probe '{probe}': {path.name} covers {covered} repeat(s) but {args.repeats} "
            "were requested, so the missing folds will be trained."
        )

    probe_args = argparse.Namespace(**vars(args))
    probe_args.mode = mode
    probe_args.run_name = run_name

    device = get_device()
    logger.info(f"Probe '{probe}': input mode '{mode}', {len(folds)} folds, backbone {args.backbone}")

    predictions: List[pd.DataFrame] = []
    for spec in folds:
        fold_predictions, _ = train_one_fold(spec, df, exams, probe_args, device)
        predictions.append(fold_predictions)

    pd.concat(predictions, ignore_index=True).to_csv(path, index=False)
    logger.info(f"Probe '{probe}' predictions -> {path}")
    return path


def verdict_table(paths: List[Path], headline: Path | None, bootstrap: int) -> None:
    """Print each probe's AUROC beside the headline run and state whether it clears them."""
    rows: List[Tuple[str, Dict[str, Any]]] = []
    for path in paths + ([headline] if headline else []):
        if not path.exists():
            logger.warning(f"Missing predictions: {path}")
            continue
        preds: pd.DataFrame = load_predictions(path)
        name: str = str(preds["run"].iloc[0]) if "run" in preds.columns else path.stem
        rows.append((name, evaluate_run(preds, name, n_bootstrap=bootstrap)))

    print("\n=== Negative controls ===")
    print(f"{'run':24s} " + "  ".join(f"{name:>18s}" for name, _ in ENDPOINTS))
    for name, result in rows:
        cells: List[str] = []
        for endpoint, _ in ENDPOINTS:
            mean: float = result["summary"]["endpoints"][endpoint]["auroc"]["mean"]
            ci = result["bootstrap_ci_subject_level"][endpoint]
            cells.append(f"{mean:.3f} [{ci.get('auroc_ci_low', float('nan')):.2f},{ci.get('auroc_ci_high', float('nan')):.2f}]")
        print(f"{name:24s} " + "  ".join(f"{c:>18s}" for c in cells))


def _fold_standardised_exams(path: Path, repeats: int) -> pd.DataFrame:
    """Load out-of-fold predictions, z-scored within each fold, one row per exam.

    Standardising before pooling is required for a fair comparison. Each fold is a
    separately fitted model with its own output offset, and two exams held out by
    different folds are scored by different models; pooling raw scores mixes that offset
    into the global ranking and penalises whichever method varies more between folds.
    Measured here, that alone moved the network by 0.04 AUROC while leaving gradient
    boosting untouched. Within-fold ranking is unaffected by the transform.
    """
    preds: pd.DataFrame = pd.read_csv(path)
    preds = preds[preds["repeat"] < repeats].copy()
    preds["score"] = preds.groupby(["repeat", "fold"])["pred_log_kpa"].transform(
        lambda s: (s - s.mean()) / (s.std(ddof=0) + 1e-9)
    )
    return preds.groupby("exam_id", as_index=False).agg(
        {"subject": "first", "stage_index": "first", "score": "mean"}
    )


def paired_bootstrap_delta(
    model_exams: pd.DataFrame,
    other_exams: pd.DataFrame,
    n_bootstrap: int = 2000,
    seed: int = 0,
) -> Tuple[float, float, float]:
    """Difference in >=F2 AUROC between two scorers on the same exams, with a 95% CI.

    Both scorers are evaluated on every resampled set, so the interval describes the
    *difference* directly. Comparing two separately computed intervals for overlap would
    be a weaker and more conservative test.
    """
    merged: pd.DataFrame = model_exams.merge(other_exams[["exam_id", "score"]], on="exam_id", suffixes=("_a", "_b"))
    y: np.ndarray = (merged["stage_index"].to_numpy() >= 2).astype(int)
    a, b = merged["score_a"].to_numpy(), merged["score_b"].to_numpy()

    subjects: np.ndarray = merged["subject"].to_numpy()
    unique_subjects: np.ndarray = np.unique(subjects)
    rows_by_subject = {s: np.flatnonzero(subjects == s) for s in unique_subjects}

    rng = np.random.default_rng(seed)
    deltas: List[float] = []
    for _ in range(n_bootstrap):
        drawn = rng.choice(unique_subjects, size=len(unique_subjects), replace=True)
        rows = np.concatenate([rows_by_subject[s] for s in drawn])
        y_boot = y[rows]
        if y_boot.sum() in (0, len(y_boot)):
            continue
        deltas.append(roc_auc_score(y_boot, a[rows]) - roc_auc_score(y_boot, b[rows]))

    low, high = np.percentile(deltas, [2.5, 97.5])
    return float(roc_auc_score(y, a) - roc_auc_score(y, b)), float(low), float(high)


def _run_name(path: Path) -> str:
    """Name a predictions CSV declares for itself, falling back to its filename."""
    preds: pd.DataFrame = pd.read_csv(path, nrows=1)
    return str(preds["run"].iloc[0]) if "run" in preds.columns and len(preds) else path.stem


def verdict(paths: List[Path], headline: Path, repeats: int, n_bootstrap: int) -> Dict[str, Any]:
    """State whether the model beats each control by more than sampling noise.

    Returns the result as well as printing it. The conclusion is what the project is
    judged on, so it has to outlive the stdout of one run: main() writes it to
    verdict.json for README and the API to read rather than re-deriving it by eye.
    """
    model_exams: pd.DataFrame = _fold_standardised_exams(headline, repeats)
    y: np.ndarray = (model_exams["stage_index"].to_numpy() >= 2).astype(int)
    headline_auroc: float = float(roc_auc_score(y, model_exams["score"].to_numpy()))

    print("\n=== Verdict on >=F2, paired subject-level bootstrap ===")
    print(f"headline model AUROC = {headline_auroc:.3f}"
          f"  ({len(model_exams)} exams, repeats < {repeats}, fold-standardised)\n")
    print(f"{'control':22s} {'AUROC':>7s}  {'delta':>7s}  {'95% CI of delta':>20s}   verdict")

    controls: List[Dict[str, Any]] = []
    all_cleared: bool = True
    records: List[Dict[str, Any]] = []
    for path in paths:
        if not path.exists():
            continue
        control: pd.DataFrame = _fold_standardised_exams(path, repeats)
        delta, low, high = paired_bootstrap_delta(model_exams, control, n_bootstrap=n_bootstrap)
        control_auroc: float = roc_auc_score(
            (control["stage_index"].to_numpy() >= 2).astype(int), control["score"].to_numpy()
        )
        cleared: bool = low > 0
        all_cleared = all_cleared and cleared
        records.append({
            "control": path.stem,
            "control_auroc": round(control_auroc, 4),
            "delta_auroc": round(delta, 4),
            "delta_ci_low": round(low, 4),
            "delta_ci_high": round(high, 4),
            "cleared": cleared,
        })
        controls.append({
            "run": _run_name(path),
            "auroc": float(control_auroc),
            "delta": delta,
            "delta_ci_low": low,
            "delta_ci_high": high,
            "cleared": cleared,
            "n_folds": _fold_count(path, repeats),
        })
        print(
            f"{path.stem:22s} {control_auroc:7.3f}  {delta:+7.3f}  [{low:+.3f}, {high:+.3f}]"
            f"   {'CLEARED' if cleared else 'NOT CLEARED'}"
        )

    print()
    if all_cleared:
        print("PASS -- the model beats every shortcut control by more than sampling noise, so its")
        print("        score reflects liver content rather than acquisition artefacts.")
    else:
        print("FAIL -- at least one control is statistically indistinguishable from the model.")
        print("        Do not present the score as a fibrosis result until that gap opens.")

    VERDICT_PATH.parent.mkdir(parents=True, exist_ok=True)
    VERDICT_PATH.write_text(
        json.dumps(
            {
                "endpoint": "ge_f2",
                "headline_run": headline.stem,
                "headline_auroc": round(float(roc_auc_score(y, model_exams["score"].to_numpy())), 4),
                "n_exams": int(len(model_exams)),
                "repeats_probed": repeats,
                "controls": records,
                "all_controls_cleared": all_cleared,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    logger.info(f"Wrote verdict -> {VERDICT_PATH}")

    return {
        "endpoint": "ge_f2",
        "test": "paired subject-level bootstrap on fold-standardised scores; cleared when the 95% CI of the delta excludes 0",
        "repeats": repeats,
        "n_exams": int(len(model_exams)),
        "n_bootstrap": n_bootstrap,
        "headline": {
            "run": _run_name(headline),
            "auroc": headline_auroc,
            "n_folds": _fold_count(headline, repeats),
        },
        "controls": controls,
        "passed": all_cleared,
    }


def _fold_count(path: Path, repeats: int) -> int:
    """How many distinct folds a predictions CSV contributes at this repeat budget."""
    preds: pd.DataFrame = pd.read_csv(path, usecols=["repeat", "fold"])
    return int(preds[preds["repeat"] < repeats].drop_duplicates().shape[0])


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the fibrosis negative controls")
    parser.add_argument("--probes", nargs="+", default=["chrome", "mask", "metadata"], choices=["chrome", "mask", "metadata"])
    parser.add_argument("--headline", type=Path, default=None, help="Predictions CSV of the real model to compare against")
    parser.add_argument("--repeats", type=int, default=1, help="How many CV repeats to probe (1 = 5 folds)")
    parser.add_argument("--backbone", default="resnet18")
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--patience", type=int, default=8)
    parser.add_argument("--batch_size", type=int, default=32)
    parser.add_argument("--img_size", type=int, default=256)
    parser.add_argument("--lr_head", type=float, default=3e-4)
    parser.add_argument("--lr_backbone", type=float, default=3e-5)
    parser.add_argument("--weight_decay", type=float, default=0.01)
    parser.add_argument("--warmup_epochs", type=int, default=3)
    parser.add_argument("--grad_clip", type=float, default=1.0)
    parser.add_argument("--ema_decay", type=float, default=0.999)
    parser.add_argument("--dropout", type=float, default=0.3)
    parser.add_argument("--corn_weight", type=float, default=0.3)
    parser.add_argument("--swe_weight", type=float, default=0.1)
    parser.add_argument("--use_view", action="store_true", default=False, help="Probes exclude view metadata by default")
    parser.add_argument("--tta", action="store_true", default=True)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--resume", action="store_true", help="Reuse existing per-fold probe checkpoints instead of retraining them")
    parser.add_argument("--force_retrain", action="store_true", help="Retrain a probe even when its predictions CSV already covers the requested repeats")
    parser.add_argument("--bootstrap", type=int, default=2000)
    parser.add_argument("--out_dir", type=Path, default=PRED_DIR)
    parser.add_argument("--verdict_out", type=Path, default=VERDICT_PATH)
    args = parser.parse_args()

    df: pd.DataFrame = load_train_labels()
    exams: pd.DataFrame = exam_table(df)
    all_folds: List[Dict[str, Any]] = load_folds()
    folds: List[Dict[str, Any]] = [f for f in all_folds if f["repeat"] < args.repeats]

    if len(folds) < len(all_folds):
        logger.warning(
            f"Probing {len(folds)} of {len(all_folds)} folds (repeats < {args.repeats}) to bound cost. "
            "A negative control only has to answer 'clearly above chance or not', but the probe "
            "AUROCs below are therefore noisier than the headline run's."
        )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    paths: List[Path] = []
    for probe in args.probes:
        if probe == "metadata":
            path: Path = args.out_dir / f"{METADATA_RUN}.csv"
            if not path.exists():
                logger.warning(f"{path} not found -- run: python baselines.py --which {METADATA_RUN}")
                continue
            logger.info(f"Probe 'metadata': reusing {path}")
            paths.append(path)
            continue
        paths.append(run_probe(probe, df, exams, folds, args))

    verdict_table(paths, args.headline, args.bootstrap)
    if args.headline and args.headline.exists():
        result: Dict[str, Any] = verdict(paths, args.headline, args.repeats, args.bootstrap)
        args.verdict_out.parent.mkdir(parents=True, exist_ok=True)
        args.verdict_out.write_text(json.dumps(json_safe(result), indent=2), encoding="utf-8")
        logger.info(f"Wrote verdict -> {args.verdict_out}")
    else:
        logger.warning("No --headline given, so no verdict was computed or written.")


if __name__ == "__main__":
    main()
