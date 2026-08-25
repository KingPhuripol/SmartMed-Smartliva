"""Baselines for fibrosis staging -- including the negative control that gates the project.

Four reference points, all scored through evaluate.py on the same frozen folds:

* **B0 majority** -- always predict F0. Establishes that accuracy is a worthless headline
  metric here (it already scores ~0.68 at exam level).
* **B1 mean-kPa** -- always predict the training fold's mean stiffness. The MAE floor.
* **B2 classical texture** -- Haralick/GLCM and first-order statistics over the liver ROI,
  fed to gradient boosting. This is the bar a convolutional network must clear to justify
  its existence.
* **B3 metadata-only** -- image height, width, aspect ratio, view and acquisition year.
  **No pixels at all.**

B3 is the important one. Image resolution is confounded with the label in this dataset
(mean 5.10 kPa at 720x1000 versus 6.75 kPa at 730x1020; F4 rate 0.0% versus 11.9%), and
resolution is a scanner and era fingerprint that a network can read from aspect ratio and
interpolation texture even after resizing. Whatever AUROC B3 reaches is the floor above
which a deep model must clear its own confidence interval before its score counts as
evidence about fibrosis rather than about scanners.
"""

import argparse
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor

from cache_build import CACHE_ROOT, cache_path
from evaluate import PRED_DIR, aggregate_to_exam, calibrate_thresholds
from labels import STAGES, VIEWS, exam_table, load_train_labels
from splits import inner_folds, load_folds

BASE_DIR: Path = Path(__file__).resolve().parent
FEATURE_CACHE: Path = BASE_DIR / "reports" / "baseline_features.npz"

GLCM_LEVELS: int = 32
GLCM_DISTANCES: Tuple[int, ...] = (1, 3)
GLCM_OFFSETS: Tuple[Tuple[int, int], ...] = ((0, 1), (1, 0), (1, 1), (1, -1))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger: logging.Logger = logging.getLogger("SmartLiva.FibrosisBaselines")


def _shift_pair(arr: np.ndarray, oy: int, ox: int) -> Tuple[np.ndarray, np.ndarray]:
    """Return the two overlapping views of `arr` separated by the offset (oy, ox)."""
    h, w = arr.shape
    rows_a = slice(max(0, -oy), h - max(0, oy))
    rows_b = slice(max(0, oy), h - max(0, -oy))
    cols_a = slice(max(0, -ox), w - max(0, ox))
    cols_b = slice(max(0, ox), w - max(0, -ox))
    return arr[rows_a, cols_a], arr[rows_b, cols_b]


def glcm_features(gray: np.ndarray, valid: np.ndarray) -> List[float]:
    """Haralick descriptors from grey-level co-occurrence matrices over valid pixels only.

    Pairs touching background are excluded, so the masked-out region cannot manufacture
    a spurious uniform texture.
    """
    quantized: np.ndarray = np.minimum((gray.astype(np.int32) * GLCM_LEVELS) // 256, GLCM_LEVELS - 1)
    indices: np.ndarray = np.arange(GLCM_LEVELS, dtype=np.float64)
    grid_i, grid_j = np.meshgrid(indices, indices, indexing="ij")
    difference_squared: np.ndarray = (grid_i - grid_j) ** 2

    features: List[float] = []
    for distance in GLCM_DISTANCES:
        for dy, dx in GLCM_OFFSETS:
            a, b = _shift_pair(quantized, dy * distance, dx * distance)
            valid_a, valid_b = _shift_pair(valid, dy * distance, dx * distance)
            both: np.ndarray = valid_a & valid_b

            if both.sum() < 64:
                features.extend([0.0] * 5)
                continue

            i, j = a[both], b[both]
            counts: np.ndarray = np.bincount(
                i * GLCM_LEVELS + j, minlength=GLCM_LEVELS * GLCM_LEVELS
            ).astype(np.float64).reshape(GLCM_LEVELS, GLCM_LEVELS)
            matrix: np.ndarray = counts + counts.T
            matrix /= matrix.sum()

            mean_i: float = float((matrix * grid_i).sum())
            mean_j: float = float((matrix * grid_j).sum())
            std_i: float = float(np.sqrt((matrix * (grid_i - mean_i) ** 2).sum())) + 1e-9
            std_j: float = float(np.sqrt((matrix * (grid_j - mean_j) ** 2).sum())) + 1e-9

            features.extend(
                [
                    float((matrix * difference_squared).sum()),                       # contrast
                    float((matrix / (1.0 + difference_squared)).sum()),               # homogeneity
                    float((matrix ** 2).sum()),                                       # energy
                    float(-(matrix * np.log(matrix + 1e-12)).sum()),                  # entropy
                    float((matrix * (grid_i - mean_i) * (grid_j - mean_j)).sum() / (std_i * std_j)),
                ]
            )
    return features


def texture_features(image_name: str) -> List[float]:
    """B2 feature vector for one image: GLCM + first-order + sharpness + hepatorenal proxy."""
    roi: Optional[np.ndarray] = cv2.imread(str(cache_path("roi_masked_bbox", image_name)), cv2.IMREAD_GRAYSCALE)
    fan: Optional[np.ndarray] = cv2.imread(str(cache_path("fan", image_name)), cv2.IMREAD_GRAYSCALE)
    if roi is None or fan is None:
        raise FileNotFoundError(f"Missing cache for {image_name}; run cache_build.py first")

    valid: np.ndarray = roi > 0
    foreground: np.ndarray = roi[valid].astype(np.float64)
    if foreground.size < 64:
        return [0.0] * (len(GLCM_DISTANCES) * len(GLCM_OFFSETS) * 5 + 7)

    mean: float = float(foreground.mean())
    std: float = float(foreground.std()) + 1e-9
    centred: np.ndarray = foreground - mean

    # Liver brightness relative to the whole sector -- a scale-free stand-in for the
    # hepatorenal index, which rises with steatosis and tracks fibrosis indirectly.
    sector: np.ndarray = fan[fan > 0]
    hepatorenal: float = mean / (float(sector.mean()) + 1e-9) if sector.size > 0 else 0.0

    return glcm_features(roi, valid) + [
        mean,
        std,
        float((centred ** 3).mean() / std ** 3),                       # skewness
        float((centred ** 4).mean() / std ** 4),                       # kurtosis
        float(cv2.Laplacian(roi, cv2.CV_64F).var()),                   # sharpness / speckle
        float(valid.mean()),                                           # ROI fill fraction
        hepatorenal,
    ]


def metadata_features(row: pd.Series) -> List[float]:
    """B3 feature vector: everything about an image EXCEPT its pixels."""
    height, width = row["orig_h"], row["orig_w"]
    view_onehot: List[float] = [1.0 if row["view"] == v else 0.0 for v in VIEWS]
    year: float = float(pd.to_datetime(int(row["ts"]), unit="s").year)
    return [float(height), float(width), float(width) / max(float(height), 1.0), height * width, year] + view_onehot


def build_feature_table(df: pd.DataFrame, rebuild: bool = False) -> Tuple[np.ndarray, np.ndarray]:
    """Compute (or load) the B2 texture and B3 metadata matrices for every training image."""
    if FEATURE_CACHE.exists() and not rebuild:
        cached = np.load(FEATURE_CACHE, allow_pickle=True)
        if list(cached["image_names"]) == list(df["image_name"]):
            logger.info(f"Loaded cached baseline features from {FEATURE_CACHE}")
            return cached["texture"], cached["metadata"]
        logger.warning("Cached features do not match the current label table; rebuilding")

    logger.info(f"Extracting baseline features for {len(df)} images (this takes a few minutes)")
    texture_rows: List[List[float]] = []
    for i, name in enumerate(df["image_name"], 1):
        texture_rows.append(texture_features(name))
        if i % 400 == 0:
            logger.info(f"  {i}/{len(df)}")

    metadata_rows: List[List[float]] = [metadata_features(row) for _, row in df.iterrows()]

    texture: np.ndarray = np.asarray(texture_rows, dtype=np.float64)
    metadata: np.ndarray = np.asarray(metadata_rows, dtype=np.float64)
    np.nan_to_num(texture, copy=False, nan=0.0, posinf=0.0, neginf=0.0)

    FEATURE_CACHE.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        FEATURE_CACHE, texture=texture, metadata=metadata, image_names=df["image_name"].to_numpy()
    )
    logger.info(f"Cached baseline features -> {FEATURE_CACHE}")
    return texture, metadata


def _fit_predict(
    features: np.ndarray,
    target: np.ndarray,
    train_rows: np.ndarray,
    predict_rows: np.ndarray,
    seed: int,
) -> np.ndarray:
    """Fit gradient boosting on log-kPa and predict. Small trees: 528 sessions is not a lot."""
    model = GradientBoostingRegressor(
        n_estimators=300, learning_rate=0.05, max_depth=3, subsample=0.8, random_state=seed
    )
    model.fit(features[train_rows], target[train_rows])
    return model.predict(features[predict_rows])


def run_baseline(
    name: str,
    df: pd.DataFrame,
    exams: pd.DataFrame,
    folds: List[Dict[str, Any]],
    features: Optional[np.ndarray],
    seed: int = 42,
) -> pd.DataFrame:
    """Produce exam-level out-of-fold predictions for one baseline across all folds."""
    log_kpa: np.ndarray = np.log(df["kpa"].to_numpy())
    exam_of_image: np.ndarray = df["exam_id"].to_numpy()
    stage_of_exam: Dict[str, int] = dict(zip(exams["exam_id"], exams["stage_index"]))

    outputs: List[pd.DataFrame] = []
    for spec in folds:
        train_exams, val_exams = set(spec["train_exams"]), set(spec["val_exams"])
        train_rows: np.ndarray = np.flatnonzero(np.isin(exam_of_image, list(train_exams)))
        val_rows: np.ndarray = np.flatnonzero(np.isin(exam_of_image, list(val_exams)))

        if name == "B0_majority":
            # Always F0: predict the median stiffness of the training fold's F0 exams.
            majority_kpa = np.median(df["kpa"].to_numpy()[train_rows][df["te_stage"].to_numpy()[train_rows] == "F0"])
            predictions: np.ndarray = np.full(len(val_rows), np.log(majority_kpa))
            cutoffs: Optional[List[float]] = None
        elif name == "B1_mean_kpa":
            predictions = np.full(len(val_rows), float(log_kpa[train_rows].mean()))
            cutoffs = None
        else:
            assert features is not None
            predictions = _fit_predict(features, log_kpa, train_rows, val_rows, seed)

            # Thresholds are calibrated on inner folds only -- never on the outer fold
            # we are about to score.
            inner_scores: List[np.ndarray] = []
            inner_stages: List[np.ndarray] = []
            for inner_train, inner_val in inner_folds(exams, spec["train_exams"], seed=seed):
                inner_train_rows = np.flatnonzero(np.isin(exam_of_image, inner_train))
                inner_val_rows = np.flatnonzero(np.isin(exam_of_image, inner_val))
                inner_predictions = _fit_predict(features, log_kpa, inner_train_rows, inner_val_rows, seed)
                inner_frame = aggregate_to_exam(df.iloc[inner_val_rows], inner_predictions)
                inner_scores.append(inner_frame["pred_log_kpa"].to_numpy())
                inner_stages.append(inner_frame["stage_index"].to_numpy())
            cutoffs = calibrate_thresholds(np.concatenate(inner_stages), np.concatenate(inner_scores))

        fold_predictions: pd.DataFrame = aggregate_to_exam(df.iloc[val_rows], predictions)
        fold_predictions["stage_index"] = fold_predictions["exam_id"].map(stage_of_exam)
        fold_predictions["run"] = name
        fold_predictions["repeat"] = spec["repeat"]
        fold_predictions["fold"] = spec["fold"]
        if cutoffs is not None:
            for i, cutoff in enumerate(cutoffs, start=1):
                fold_predictions[f"thr_f{i}"] = cutoff
        outputs.append(fold_predictions)

        logger.info(f"[{name}] repeat {spec['repeat']} fold {spec['fold']}: {len(fold_predictions)} exams")

    return pd.concat(outputs, ignore_index=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run fibrosis baselines on the frozen folds")
    parser.add_argument(
        "--which",
        nargs="+",
        default=["B3_metadata"],
        choices=["B0_majority", "B1_mean_kpa", "B2_texture", "B3_metadata"],
        help="Run B3 first -- it is the shortcut floor every later result is judged against",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--rebuild_features", action="store_true")
    parser.add_argument("--out_dir", type=Path, default=PRED_DIR)
    args = parser.parse_args()

    if not CACHE_ROOT.exists():
        raise FileNotFoundError(f"Image cache missing at {CACHE_ROOT}. Run cache_build.py first.")

    df: pd.DataFrame = load_train_labels()
    exams: pd.DataFrame = exam_table(df)
    folds: List[Dict[str, Any]] = load_folds()

    needs_features: bool = any(name in ("B2_texture", "B3_metadata") for name in args.which)
    texture: Optional[np.ndarray] = None
    metadata: Optional[np.ndarray] = None
    if needs_features:
        shapes: List[Tuple[int, int]] = []
        for path in df["img_path"]:
            image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
            shapes.append(image.shape[:2] if image is not None else (0, 0))
        df["orig_h"] = [s[0] for s in shapes]
        df["orig_w"] = [s[1] for s in shapes]
        texture, metadata = build_feature_table(df, rebuild=args.rebuild_features)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    for name in args.which:
        features: Optional[np.ndarray] = {
            "B2_texture": texture,
            "B3_metadata": metadata,
        }.get(name)
        predictions: pd.DataFrame = run_baseline(name, df, exams, folds, features, seed=args.seed)
        path: Path = args.out_dir / f"{name}.csv"
        predictions.to_csv(path, index=False)
        logger.info(f"Wrote {len(predictions)} predictions -> {path}")

    print("\nScore them with:")
    print("  python evaluate.py --preds " + " ".join(f"reports/preds/{n}.csv" for n in args.which))


if __name__ == "__main__":
    main()
