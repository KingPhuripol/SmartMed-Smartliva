"""Evaluation protocol for fibrosis staging. Every model and baseline is scored here.

Design decisions that are not negotiable, and why:

* **Exam-level metrics.** Per-image predictions are averaged into per-exam predictions
  before anything is measured. The clinical unit is the exam, and image-level scores
  would count a 3-view exam three times.

* **AUROC/AUPRC on the ordered endpoints are the headline.** Five-class accuracy is
  buried in the tertiary section because predicting "F0" unconditionally already scores
  0.68 at exam level -- an accuracy of 0.70 is compatible with a model that has learned
  nothing about fibrosis.

* **Bootstrap at the subject level.** Subjects are whole clinic sessions and their exams
  are correlated; resampling exams would report confidence intervals that are too narrow.

* **AUPRC is reported next to every AUROC.** At 5.9% F4 prevalence an AUROC of 0.85 can
  coexist with an AUPRC of 0.25, and only one of those numbers tells a clinician
  anything useful.

Input is a predictions CSV with one row per exam and columns:
    run, repeat, fold, exam_id, subject, kpa, stage_index, pred_log_kpa
plus optionally prob_ge_f2 (enables calibration metrics) and thr_f1..thr_f4
(per-fold thresholds that the producer fitted on inner folds only).
"""

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    cohen_kappa_score,
    confusion_matrix,
    f1_score,
    roc_auc_score,
    roc_curve,
)

from labels import STAGE_EDGES, STAGES

BASE_DIR: Path = Path(__file__).resolve().parent
PRED_DIR: Path = BASE_DIR / "reports" / "preds"
METRICS_DIR: Path = BASE_DIR / "reports"

# The three endpoints hepatology actually acts on.
ENDPOINTS: Tuple[Tuple[str, int], ...] = (("ge_f2", 2), ("ge_f3", 3), ("f4", 4))
N_BOOTSTRAP: int = 2000
TARGET_SPECIFICITY: float = 0.90

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger: logging.Logger = logging.getLogger("SmartLiva.FibrosisEval")


def aggregate_to_exam(
    image_df: pd.DataFrame,
    pred_log_kpa: np.ndarray,
    prob_ge_f2: Optional[np.ndarray] = None,
) -> pd.DataFrame:
    """Average image-level predictions into one prediction per exam."""
    frame: pd.DataFrame = image_df[["exam_id", "subject", "kpa", "stage_index"]].copy()
    frame["pred_log_kpa"] = pred_log_kpa
    if prob_ge_f2 is not None:
        frame["prob_ge_f2"] = prob_ge_f2

    aggregation: Dict[str, str] = {
        "subject": "first",
        "kpa": "first",
        "stage_index": "first",
        "pred_log_kpa": "mean",
    }
    if prob_ge_f2 is not None:
        aggregation["prob_ge_f2"] = "mean"

    return frame.groupby("exam_id", as_index=False).agg(aggregation)


def stage_from_thresholds(kpa: np.ndarray, edges: Sequence[float] = STAGE_EDGES) -> np.ndarray:
    """Assign ordinal stage indices 0..4 from stiffness values.

    Uses the midpoint bin edges (5.95/7.05/8.65/10.25) rather than the clinical cutoffs
    themselves, so that a value landing exactly on a cutoff -- 6.0 kPa is F1, not F0 --
    is binned the same way `labels.kpa_to_stage` bins the ground truth.
    """
    return np.searchsorted(np.asarray(edges, dtype=float), kpa, side="left")


def calibrate_thresholds(
    calib_true_stage: np.ndarray,
    calib_score: np.ndarray,
) -> List[float]:
    """Fit stage cutoffs on a score by matching the observed stage prevalence.

    A regression fit shrinks predictions toward the mean, so the fixed clinical cutoffs
    systematically under-call the high stages. Matching quantiles restores the marginal
    distribution and is stable even when a stage has only a few dozen exams -- unlike
    directly optimising a metric, which would overfit at these counts.

    Must be called with *inner-fold* data only.
    """
    n: int = len(calib_score)
    cumulative: float = 0.0
    cutoffs: List[float] = []
    for stage_index in range(len(STAGES) - 1):
        cumulative += float((calib_true_stage == stage_index).sum()) / max(n, 1)
        cutoffs.append(float(np.quantile(calib_score, min(cumulative, 1.0))))
    return cutoffs


def _sens_spec_at_specificity(
    y_true: np.ndarray, score: np.ndarray, target: float = TARGET_SPECIFICITY
) -> Tuple[float, float]:
    """Sensitivity at the operating point whose specificity first reaches `target`."""
    fpr, tpr, _ = roc_curve(y_true, score)
    feasible = np.flatnonzero((1.0 - fpr) >= target)
    if feasible.size == 0:
        return float("nan"), float("nan")
    idx: int = int(feasible[np.argmax(tpr[feasible])])
    return float(tpr[idx]), float(1.0 - fpr[idx])


def _youden(y_true: np.ndarray, score: np.ndarray) -> Tuple[float, float]:
    """Sensitivity and specificity at the point maximising Youden's J."""
    fpr, tpr, _ = roc_curve(y_true, score)
    idx: int = int(np.argmax(tpr - fpr))
    return float(tpr[idx]), float(1.0 - fpr[idx])


def endpoint_metrics(stage_index: np.ndarray, score: np.ndarray) -> Dict[str, Dict[str, float]]:
    """AUROC, AUPRC, prevalence and operating points for each binary endpoint."""
    out: Dict[str, Dict[str, float]] = {}
    for name, threshold in ENDPOINTS:
        y: np.ndarray = (stage_index >= threshold).astype(int)
        if y.sum() == 0 or y.sum() == len(y):
            out[name] = {"auroc": float("nan"), "auprc": float("nan"), "n_pos": int(y.sum())}
            continue

        sens_at_spec, spec_at_spec = _sens_spec_at_specificity(y, score)
        sens_j, spec_j = _youden(y, score)
        out[name] = {
            "auroc": float(roc_auc_score(y, score)),
            "auprc": float(average_precision_score(y, score)),
            "prevalence": float(y.mean()),
            "n_pos": int(y.sum()),
            "sens_at_spec90": sens_at_spec,
            "spec_at_spec90": spec_at_spec,
            "sens_youden": sens_j,
            "spec_youden": spec_j,
        }
    return out


def regression_metrics(true_kpa: np.ndarray, pred_log_kpa: np.ndarray) -> Dict[str, float]:
    """Rank correlation and absolute error on the continuous stiffness target.

    `exp` of a mean prediction in log space estimates the conditional *median*, so the
    median absolute error is the better-matched summary and is reported alongside MAE.
    """
    pred_kpa: np.ndarray = np.exp(pred_log_kpa)
    errors: np.ndarray = np.abs(pred_kpa - true_kpa)
    constant_prediction: bool = float(np.std(pred_log_kpa)) < 1e-12

    return {
        "spearman": float("nan") if constant_prediction else float(spearmanr(true_kpa, pred_log_kpa).statistic),
        "pearson": float("nan") if constant_prediction else float(pearsonr(true_kpa, pred_kpa).statistic),
        "mae_kpa": float(errors.mean()),
        "medae_kpa": float(np.median(errors)),
        "rmse_kpa": float(np.sqrt(((pred_kpa - true_kpa) ** 2).mean())),
    }


def staging_metrics(
    stage_index: np.ndarray,
    pred_stage: np.ndarray,
) -> Dict[str, Any]:
    """Five-class metrics. Always read these next to the per-fold minority counts."""
    labels: List[int] = list(range(len(STAGES)))
    return {
        "accuracy": float((pred_stage == stage_index).mean()),
        "accuracy_within_1": float((np.abs(pred_stage - stage_index) <= 1).mean()),
        "macro_f1": float(f1_score(stage_index, pred_stage, labels=labels, average="macro", zero_division=0)),
        "quadratic_kappa": float(cohen_kappa_score(stage_index, pred_stage, labels=labels, weights="quadratic")),
        "confusion": confusion_matrix(stage_index, pred_stage, labels=labels).tolist(),
        "support": {stage: int((stage_index == i).sum()) for i, stage in enumerate(STAGES)},
    }


def fold_metrics(exams: pd.DataFrame) -> Dict[str, Any]:
    """Full metric suite for one validation fold."""
    stage_index: np.ndarray = exams["stage_index"].to_numpy()
    score: np.ndarray = exams["pred_log_kpa"].to_numpy()
    true_kpa: np.ndarray = exams["kpa"].to_numpy()
    pred_kpa: np.ndarray = np.exp(score)

    metrics: Dict[str, Any] = {
        "n_exams": len(exams),
        "n_subjects": int(exams["subject"].nunique()),
        "endpoints": endpoint_metrics(stage_index, score),
        "regression": regression_metrics(true_kpa, score),
        "staging_fixed_thresholds": staging_metrics(
            stage_index, stage_from_thresholds(pred_kpa)
        ),
    }

    threshold_columns: List[str] = ["thr_f1", "thr_f2", "thr_f3", "thr_f4"]
    if all(column in exams.columns for column in threshold_columns):
        cutoffs: List[float] = [float(exams[column].iloc[0]) for column in threshold_columns]
        metrics["staging_calibrated_thresholds"] = staging_metrics(
            stage_index, np.searchsorted(np.asarray(cutoffs), score, side="left")
        )
        metrics["calibrated_cutoffs_log_kpa"] = cutoffs

    if "prob_ge_f2" in exams.columns:
        y_ge_f2: np.ndarray = (stage_index >= 2).astype(int)
        metrics["calibration_ge_f2"] = {
            "brier": float(brier_score_loss(y_ge_f2, exams["prob_ge_f2"].to_numpy())),
            "mean_predicted": float(exams["prob_ge_f2"].mean()),
            "observed_rate": float(y_ge_f2.mean()),
        }

    return metrics


def bootstrap_endpoint_ci(
    exams: pd.DataFrame,
    n_bootstrap: int = N_BOOTSTRAP,
    seed: int = 42,
) -> Dict[str, Dict[str, float]]:
    """Subject-level bootstrap confidence intervals for each endpoint's AUROC and AUPRC.

    Subjects are resampled with replacement and each carries all of its exams, so the
    interval reflects the real correlation structure of the data.
    """
    rng = np.random.default_rng(seed)
    subjects: np.ndarray = exams["subject"].to_numpy()
    unique_subjects: np.ndarray = np.unique(subjects)
    index_by_subject: Dict[Any, np.ndarray] = {s: np.flatnonzero(subjects == s) for s in unique_subjects}

    samples: Dict[str, Dict[str, List[float]]] = {name: {"auroc": [], "auprc": []} for name, _ in ENDPOINTS}
    stage_index: np.ndarray = exams["stage_index"].to_numpy()
    score: np.ndarray = exams["pred_log_kpa"].to_numpy()

    for _ in range(n_bootstrap):
        drawn = rng.choice(unique_subjects, size=len(unique_subjects), replace=True)
        rows: np.ndarray = np.concatenate([index_by_subject[s] for s in drawn])
        y_all, s_all = stage_index[rows], score[rows]

        for name, threshold in ENDPOINTS:
            y: np.ndarray = (y_all >= threshold).astype(int)
            if y.sum() == 0 or y.sum() == len(y):
                continue
            samples[name]["auroc"].append(float(roc_auc_score(y, s_all)))
            samples[name]["auprc"].append(float(average_precision_score(y, s_all)))

    out: Dict[str, Dict[str, float]] = {}
    for name, metric_samples in samples.items():
        out[name] = {}
        for metric, values in metric_samples.items():
            if not values:
                out[name][f"{metric}_ci_low"] = float("nan")
                out[name][f"{metric}_ci_high"] = float("nan")
                continue
            low, high = np.percentile(values, [2.5, 97.5])
            out[name][f"{metric}_ci_low"] = float(low)
            out[name][f"{metric}_ci_high"] = float(high)
            out[name][f"{metric}_ci_width"] = float(high - low)
    return out


def _mean_sd(values: List[float]) -> Dict[str, float]:
    """Mean and standard deviation over folds, ignoring undefined entries."""
    clean: np.ndarray = np.array([v for v in values if not np.isnan(v)], dtype=float)
    if clean.size == 0:
        return {"mean": float("nan"), "sd": float("nan"), "n_folds": 0}
    return {"mean": float(clean.mean()), "sd": float(clean.std(ddof=0)), "n_folds": int(clean.size)}


def evaluate_run(preds: pd.DataFrame, run_name: str, n_bootstrap: int = N_BOOTSTRAP) -> Dict[str, Any]:
    """Score every fold of one run, then summarise across folds and bootstrap the pool."""
    per_fold: List[Dict[str, Any]] = []
    for (repeat, fold), group in preds.groupby(["repeat", "fold"], sort=True):
        metrics: Dict[str, Any] = fold_metrics(group)
        metrics["repeat"], metrics["fold"] = int(repeat), int(fold)
        per_fold.append(metrics)

    summary: Dict[str, Any] = {"endpoints": {}, "regression": {}, "staging_fixed_thresholds": {}}
    for name, _ in ENDPOINTS:
        summary["endpoints"][name] = {
            metric: _mean_sd([f["endpoints"][name].get(metric, float("nan")) for f in per_fold])
            for metric in ("auroc", "auprc", "sens_at_spec90", "sens_youden")
        }
    for metric in ("spearman", "pearson", "mae_kpa", "medae_kpa", "rmse_kpa"):
        summary["regression"][metric] = _mean_sd([f["regression"][metric] for f in per_fold])
    for metric in ("accuracy", "accuracy_within_1", "macro_f1", "quadratic_kappa"):
        summary["staging_fixed_thresholds"][metric] = _mean_sd(
            [f["staging_fixed_thresholds"][metric] for f in per_fold]
        )
    if "staging_calibrated_thresholds" in per_fold[0]:
        summary["staging_calibrated_thresholds"] = {
            metric: _mean_sd([f["staging_calibrated_thresholds"][metric] for f in per_fold])
            for metric in ("accuracy", "accuracy_within_1", "macro_f1", "quadratic_kappa")
        }

    # Pool one prediction per exam (averaged over repeats) before bootstrapping, so the
    # interval describes the estimator rather than the repeat-to-repeat noise.
    pooled: pd.DataFrame = preds.groupby("exam_id", as_index=False).agg(
        {"subject": "first", "kpa": "first", "stage_index": "first", "pred_log_kpa": "mean"}
    )

    # Ranking across folds requires standardising each fold's scores first. Every fold is
    # a separately trained model with its own output offset, and two exams held out by
    # different folds are scored by different models -- pooling the raw values mixes that
    # offset noise into the global ranking. Measured here: it costs the neural network
    # 0.04 AUROC while leaving the gradient-boosting baseline unchanged, purely as an
    # artefact. It is also not what deployment looks like, where one ensemble scores
    # everyone. Within-fold ranking, and therefore every per-fold metric, is untouched.
    ranked: pd.DataFrame = preds.copy()
    ranked["pred_log_kpa"] = ranked.groupby(["repeat", "fold"])["pred_log_kpa"].transform(
        lambda s: (s - s.mean()) / (s.std(ddof=0) + 1e-9)
    )
    pooled_ranking: pd.DataFrame = ranked.groupby("exam_id", as_index=False).agg(
        {"subject": "first", "kpa": "first", "stage_index": "first", "pred_log_kpa": "mean"}
    )

    return {
        "run": run_name,
        "n_folds": len(per_fold),
        "n_exams_pooled": len(pooled),
        "summary": summary,
        "bootstrap_ci_subject_level": bootstrap_endpoint_ci(pooled_ranking, n_bootstrap=n_bootstrap),
        "pooled_ranking_auroc": {
            name: float(endpoint_metrics(
                pooled_ranking["stage_index"].to_numpy(), pooled_ranking["pred_log_kpa"].to_numpy()
            )[name]["auroc"])
            for name, _ in ENDPOINTS
        },
        "pooled": fold_metrics(pooled),
        "per_fold": per_fold,
    }


def print_report(result: Dict[str, Any]) -> None:
    """Print the headline / secondary / tertiary blocks with their caveats attached."""
    summary, ci = result["summary"], result["bootstrap_ci_subject_level"]

    print(f"\n=== {result['run']} ===  ({result['n_folds']} folds, {result['n_exams_pooled']} exams pooled)")
    print("\nHEADLINE -- discrimination on the clinical endpoints")
    print(f"{'endpoint':10s} {'AUROC (mean+-sd)':22s} {'95% CI (subject boot)':24s} {'AUPRC':16s} prevalence")
    for name, _ in ENDPOINTS:
        auroc, auprc = summary["endpoints"][name]["auroc"], summary["endpoints"][name]["auprc"]
        interval: str = f"[{ci[name].get('auroc_ci_low', float('nan')):.3f}, {ci[name].get('auroc_ci_high', float('nan')):.3f}]"
        prevalence: float = result["pooled"]["endpoints"][name].get("prevalence", float("nan"))
        print(
            f"{name:10s} {auroc['mean']:.3f} +- {auroc['sd']:.3f}       {interval:24s} "
            f"{auprc['mean']:.3f} +- {auprc['sd']:.3f}   {prevalence * 100:.1f}%"
        )

    print("\nSECONDARY -- agreement with the stiffness measurement")
    for metric in ("spearman", "pearson", "mae_kpa", "medae_kpa", "rmse_kpa"):
        entry = summary["regression"][metric]
        print(f"  {metric:12s} {entry['mean']:.3f} +- {entry['sd']:.3f}")

    print("\nTERTIARY -- 5-class staging (fixed clinical cutoffs)")
    for metric in ("accuracy", "accuracy_within_1", "macro_f1", "quadratic_kappa"):
        entry = summary["staging_fixed_thresholds"][metric]
        print(f"  {metric:18s} {entry['mean']:.3f} +- {entry['sd']:.3f}")
    if "staging_calibrated_thresholds" in summary:
        print("           (with thresholds recalibrated on inner folds)")
        for metric in ("accuracy", "macro_f1", "quadratic_kappa"):
            entry = summary["staging_calibrated_thresholds"][metric]
            print(f"  {metric:18s} {entry['mean']:.3f} +- {entry['sd']:.3f}")

    support = result["pooled"]["staging_fixed_thresholds"]["support"]
    print(
        f"\n  CAVEAT: exam support per stage {support}. Split across 5 folds this is roughly "
        f"{support['F3'] // 5} F3 and {support['F4'] // 5} F4 exams per validation fold -- "
        "per-class F1 from counts this small is not a stable estimate. Predicting F0 for "
        "every exam already scores accuracy 0.68 here, so read AUROC/AUPRC, not accuracy."
    )
    print("  CAVEAT: operating points (sens@spec90, Youden) are chosen on the same fold they are")
    print("          reported on, so they are optimistic; the AUROC/AUPRC columns are not.")


def json_safe(value: Any) -> Any:
    """Recursively replace NaN/Inf with None so the output is valid JSON.

    Undefined metrics are real here -- a constant-prediction baseline has no Spearman
    correlation, and an endpoint with no positives in a fold has no AUROC. Python's
    json module happily writes a bare `NaN`, which no strict JSON parser accepts and
    which makes the metrics file unservable over HTTP.
    """
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, float) and not np.isfinite(value):
        return None
    if isinstance(value, (np.floating, np.integer)):
        return json_safe(float(value))
    return value


def load_predictions(path: Path) -> pd.DataFrame:
    """Read a predictions CSV emitted by train.py, baselines.py or shortcut_probe.py."""
    preds: pd.DataFrame = pd.read_csv(path)
    required = {"repeat", "fold", "exam_id", "subject", "kpa", "stage_index", "pred_log_kpa"}
    missing = required - set(preds.columns)
    if missing:
        raise ValueError(f"{path} is missing required columns: {sorted(missing)}")
    return preds


def main() -> None:
    parser = argparse.ArgumentParser(description="Score fibrosis predictions")
    parser.add_argument("--preds", type=Path, nargs="+", required=True, help="Prediction CSV(s) to score")
    parser.add_argument("--report", type=Path, default=METRICS_DIR / "metrics.json")
    parser.add_argument("--bootstrap", type=int, default=N_BOOTSTRAP)
    args = parser.parse_args()

    results: Dict[str, Any] = {}
    for path in args.preds:
        preds: pd.DataFrame = load_predictions(path)
        run_name: str = str(preds["run"].iloc[0]) if "run" in preds.columns else path.stem
        result: Dict[str, Any] = evaluate_run(preds, run_name, n_bootstrap=args.bootstrap)
        print_report(result)
        results[run_name] = result

    if len(results) > 1:
        print("\n=== Comparison (mean AUROC across folds) ===")
        print(f"{'run':28s} " + "  ".join(f"{name:>10s}" for name, _ in ENDPOINTS))
        for run_name, result in results.items():
            row = "  ".join(
                f"{result['summary']['endpoints'][name]['auroc']['mean']:10.3f}" for name, _ in ENDPOINTS
            )
            print(f"{run_name:28s} {row}")

    args.report.parent.mkdir(parents=True, exist_ok=True)
    existing: Dict[str, Any] = {}
    if args.report.exists():
        existing = json.loads(args.report.read_text(encoding="utf-8"))
    existing.update(results)
    args.report.write_text(json.dumps(json_safe(existing), indent=2), encoding="utf-8")
    logger.info(f"Wrote metrics for {len(results)} run(s) -> {args.report}")


if __name__ == "__main__":
    main()
