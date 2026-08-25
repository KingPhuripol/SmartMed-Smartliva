"""Train FibrosisNet across the frozen cross-validation folds.

Protocol, which exists to keep the reported numbers honest:

* Each outer fold's training exams are split again. The model early-stops on that
  *inner* split and calibrates its stage cutoffs there. The outer validation fold is
  predicted exactly once, at the end, and never influences any choice.
* Predictions are aggregated image -> exam before any metric is computed.
* Weights are exponentially averaged; with ~580 training exams per fold, the EMA is
  noticeably steadier than the last raw checkpoint.

Emits one predictions CSV that evaluate.py, the baselines and the negative controls all
share, so every number in the final table is computed the same way on the same folds.
"""

import argparse
import copy
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import roc_auc_score
from torch.utils.data import DataLoader

from dataset import FibrosisDataset
from evaluate import PRED_DIR, aggregate_to_exam, calibrate_thresholds
from labels import exam_table, load_train_labels
from model import FibrosisLoss, FibrosisNet, corn_cumulative_probs, get_device
from splits import inner_folds, load_folds

BASE_DIR: Path = Path(__file__).resolve().parent
CHECKPOINT_DIR: Path = BASE_DIR / "checkpoints"

# MPS lacks a few kernels used by the augmentation stack; fall back silently to CPU.
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger: logging.Logger = logging.getLogger("SmartLiva.FibrosisTrain")


class ModelEMA:
    """Exponential moving average of model weights, evaluated in place of the raw model.

    The decay is warmed up as `min(decay, (1 + step) / (10 + step))`. Without that, a fold
    here runs only ~35 optimizer steps per epoch, so a fixed decay of 0.999 would leave
    the average still a quarter randomly-initialised after 40 epochs -- the averaged model
    would score below chance and early stopping would select noise.
    """

    def __init__(self, model: torch.nn.Module, decay: float = 0.999) -> None:
        self.module: torch.nn.Module = copy.deepcopy(model).eval()
        for parameter in self.module.parameters():
            parameter.requires_grad_(False)
        self.decay: float = decay
        self.step: int = 0

    @torch.no_grad()
    def update(self, model: torch.nn.Module) -> None:
        decay: float = min(self.decay, (1.0 + self.step) / (10.0 + self.step))
        self.step += 1
        for shadow, current in zip(self.module.state_dict().values(), model.state_dict().values()):
            if shadow.dtype.is_floating_point:
                shadow.mul_(decay).add_(current.detach(), alpha=1.0 - decay)
            else:
                shadow.copy_(current)


def make_loader(
    df: pd.DataFrame,
    mode: str,
    img_size: int,
    train: bool,
    batch_size: int,
    use_view: bool,
    workers: int,
) -> DataLoader:
    """Build a dataloader over an image-level slice of the label table."""
    dataset = FibrosisDataset(df, mode=mode, img_size=img_size, train=train, use_view=use_view)
    return DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=train,
        num_workers=workers,
        drop_last=train and len(dataset) > batch_size,
        persistent_workers=workers > 0,
    )


@torch.no_grad()
def predict(
    model: torch.nn.Module,
    loader: DataLoader,
    device: torch.device,
    tta: bool = True,
) -> Tuple[np.ndarray, np.ndarray]:
    """Predict log-kPa and P(stage >= F2) for every image, optionally flip-averaged."""
    model.eval()
    log_kpa_batches: List[np.ndarray] = []
    prob_batches: List[np.ndarray] = []

    for batch in loader:
        image: torch.Tensor = batch["image"].to(device)
        view: torch.Tensor = batch["view_index"].to(device)

        outputs = model(image, view)
        log_kpa: torch.Tensor = outputs["log_kpa"]
        cumulative: torch.Tensor = corn_cumulative_probs(outputs["corn"])

        if tta:
            flipped = model(torch.flip(image, dims=[3]), view)
            log_kpa = 0.5 * (log_kpa + flipped["log_kpa"])
            cumulative = 0.5 * (cumulative + corn_cumulative_probs(flipped["corn"]))

        log_kpa_batches.append(log_kpa.float().cpu().numpy())
        prob_batches.append(cumulative[:, 1].float().cpu().numpy())  # P(stage >= 2)

    return np.concatenate(log_kpa_batches), np.concatenate(prob_batches)


def exam_auroc_ge_f2(df: pd.DataFrame, predictions: np.ndarray) -> float:
    """Exam-level AUROC for significant fibrosis -- the early-stopping criterion."""
    exams: pd.DataFrame = aggregate_to_exam(df, predictions)
    y: np.ndarray = (exams["stage_index"].to_numpy() >= 2).astype(int)
    if y.sum() == 0 or y.sum() == len(y):
        return float("nan")
    return float(roc_auc_score(y, exams["pred_log_kpa"].to_numpy()))


def _predictions_from_checkpoint(
    checkpoint_path: Path,
    spec: Dict[str, Any],
    tag: str,
    outer_val_df: pd.DataFrame,
    outer_val_loader: DataLoader,
    args: argparse.Namespace,
    device: torch.device,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Regenerate one fold's outer-validation predictions from an existing checkpoint.

    The stage cutoffs are read back from the checkpoint rather than refitted, so a
    resumed fold is byte-for-byte the same experiment as the original run.
    """
    checkpoint: Dict[str, Any] = torch.load(str(checkpoint_path), map_location=device, weights_only=False)

    model = FibrosisNet(
        backbone=checkpoint["backbone"], pretrained=False, use_view=checkpoint["use_view"]
    ).to(device)
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()

    predictions, probabilities = predict(model, outer_val_loader, device, tta=args.tta)
    fold_predictions: pd.DataFrame = aggregate_to_exam(outer_val_df, predictions, prob_ge_f2=probabilities)
    fold_predictions["run"] = args.run_name
    fold_predictions["repeat"] = spec["repeat"]
    fold_predictions["fold"] = spec["fold"]
    for i, cutoff in enumerate(checkpoint["cutoffs_log_kpa"], start=1):
        fold_predictions[f"thr_f{i}"] = cutoff

    outer_score: float = exam_auroc_ge_f2(outer_val_df, predictions)
    logger.info(f"[{tag}] resumed from {checkpoint_path.name}: outer {outer_score:.4f}")

    return fold_predictions, {
        "tag": tag,
        "best_epoch": -1,
        "inner_auroc_ge_f2": float(checkpoint.get("inner_auroc_ge_f2", float("nan"))),
        "outer_auroc_ge_f2": outer_score,
        "history": [],
        "resumed": True,
    }


def train_one_fold(
    spec: Dict[str, Any],
    df: pd.DataFrame,
    exams: pd.DataFrame,
    args: argparse.Namespace,
    device: torch.device,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Train on one outer fold and return its outer-validation predictions."""
    tag: str = f"r{spec['repeat']}f{spec['fold']}"
    checkpoint_path: Path = CHECKPOINT_DIR / f"{args.run_name}_{tag}.pt"

    # Hold out one inner split for early stopping and threshold calibration. The outer
    # validation exams are untouched until the very last prediction call.
    inner_train_exams, inner_val_exams = inner_folds(exams, spec["train_exams"], seed=args.seed)[0]

    inner_train_df: pd.DataFrame = df[df["exam_id"].isin(set(inner_train_exams))]
    inner_val_df: pd.DataFrame = df[df["exam_id"].isin(set(inner_val_exams))]
    outer_val_df: pd.DataFrame = df[df["exam_id"].isin(set(spec["val_exams"]))]

    outer_val_loader = make_loader(outer_val_df, args.mode, args.img_size, False, args.batch_size, args.use_view, args.workers)

    # Predictions live only in the final CSV, so an interrupted run loses them while its
    # per-fold checkpoints survive. Resuming regenerates the predictions from those
    # checkpoints instead of retraining folds that already finished.
    if getattr(args, "resume", False) and checkpoint_path.exists():
        return _predictions_from_checkpoint(checkpoint_path, spec, tag, outer_val_df, outer_val_loader, args, device)

    train_loader = make_loader(inner_train_df, args.mode, args.img_size, True, args.batch_size, args.use_view, args.workers)
    inner_val_loader = make_loader(inner_val_df, args.mode, args.img_size, False, args.batch_size, args.use_view, args.workers)

    model = FibrosisNet(
        backbone=args.backbone, pretrained=True, use_view=args.use_view, dropout=args.dropout
    ).to(device)
    criterion = FibrosisLoss(corn_weight=args.corn_weight, swe_weight=args.swe_weight)
    optimizer = torch.optim.AdamW(
        model.parameter_groups(head_lr=args.lr_head, backbone_lr=args.lr_backbone), weight_decay=args.weight_decay
    )

    steps_per_epoch: int = max(len(train_loader), 1)
    warmup_steps: int = args.warmup_epochs * steps_per_epoch
    total_steps: int = args.epochs * steps_per_epoch

    def lr_scale(step: int) -> float:
        if step < warmup_steps:
            return (step + 1) / max(warmup_steps, 1)
        progress: float = (step - warmup_steps) / max(total_steps - warmup_steps, 1)
        return 0.5 * (1.0 + np.cos(np.pi * min(progress, 1.0)))

    scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lr_scale)
    ema = ModelEMA(model, decay=args.ema_decay)

    best_score: float = -np.inf
    best_state: Optional[Dict[str, torch.Tensor]] = None
    best_epoch: int = 0
    epochs_without_improvement: int = 0
    history: List[Dict[str, float]] = []

    for epoch in range(1, args.epochs + 1):
        model.train()
        running_loss: float = 0.0
        n_seen: int = 0
        started: float = time.time()

        for batch in train_loader:
            batch = {k: v.to(device) for k, v in batch.items()}
            optimizer.zero_grad(set_to_none=True)
            losses = criterion(model(batch["image"], batch["view_index"]), batch)
            losses["total"].backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), args.grad_clip)
            optimizer.step()
            scheduler.step()
            ema.update(model)

            running_loss += float(losses["total"].detach()) * batch["image"].size(0)
            n_seen += batch["image"].size(0)

        train_loss: float = running_loss / max(n_seen, 1)
        inner_predictions, _ = predict(ema.module, inner_val_loader, device, tta=False)
        score: float = exam_auroc_ge_f2(inner_val_df, inner_predictions)
        history.append({"epoch": epoch, "train_loss": train_loss, "inner_auroc_ge_f2": score})

        marker: str = ""
        if score > best_score:
            best_score, best_epoch = score, epoch
            best_state = copy.deepcopy(ema.module.state_dict())
            epochs_without_improvement = 0
            marker = " *"
        else:
            epochs_without_improvement += 1

        logger.info(
            f"[{tag}] epoch {epoch:03d}/{args.epochs:03d} loss {train_loss:.4f} "
            f"inner_auroc_ge_f2 {score:.4f} ({time.time() - started:.0f}s){marker}"
        )

        if epochs_without_improvement >= args.patience:
            logger.info(f"[{tag}] early stop at epoch {epoch} (best {best_score:.4f} @ {best_epoch})")
            break

    assert best_state is not None, f"[{tag}] training produced no valid checkpoint"
    ema.module.load_state_dict(best_state)

    # Cutoffs come from the inner split only -- regression shrinks toward the mean, so
    # the fixed clinical cutoffs systematically under-call the high stages.
    inner_predictions, _ = predict(ema.module, inner_val_loader, device, tta=args.tta)
    inner_exams: pd.DataFrame = aggregate_to_exam(inner_val_df, inner_predictions)
    cutoffs: List[float] = calibrate_thresholds(
        inner_exams["stage_index"].to_numpy(), inner_exams["pred_log_kpa"].to_numpy()
    )

    outer_predictions, outer_probs = predict(ema.module, outer_val_loader, device, tta=args.tta)
    fold_predictions: pd.DataFrame = aggregate_to_exam(outer_val_df, outer_predictions, prob_ge_f2=outer_probs)
    fold_predictions["run"] = args.run_name
    fold_predictions["repeat"] = spec["repeat"]
    fold_predictions["fold"] = spec["fold"]
    for i, cutoff in enumerate(cutoffs, start=1):
        fold_predictions[f"thr_f{i}"] = cutoff

    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "state_dict": best_state,
            "backbone": args.backbone,
            "mode": args.mode,
            "img_size": args.img_size,
            "use_view": args.use_view,
            "cutoffs_log_kpa": cutoffs,
            "inner_auroc_ge_f2": best_score,
            "repeat": spec["repeat"],
            "fold": spec["fold"],
        },
        checkpoint_path,
    )

    outer_score: float = exam_auroc_ge_f2(outer_val_df, outer_predictions)
    logger.info(f"[{tag}] inner {best_score:.4f} -> outer {outer_score:.4f}  saved {checkpoint_path.name}")

    return fold_predictions, {
        "tag": tag,
        "best_epoch": best_epoch,
        "inner_auroc_ge_f2": best_score,
        "outer_auroc_ge_f2": outer_score,
        "history": history,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Train FibrosisNet with grouped cross-validation")
    parser.add_argument("--backbone", default="convnext_tiny", help="torchvision backbone name")
    parser.add_argument("--mode", default="roi_masked_bbox", help="Cached input mode")
    parser.add_argument("--folds", default="all", help="'all' or comma-separated repeat:fold pairs, e.g. 0:0,0:1")
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
    parser.add_argument("--no_view", dest="use_view", action="store_false", help="Ablate the view embedding")
    parser.add_argument("--no_tta", dest="tta", action="store_false", help="Disable flip test-time augmentation")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--run_name", default=None)
    parser.add_argument("--resume", action="store_true", help="Reuse existing per-fold checkpoints instead of retraining them")
    parser.add_argument("--out_dir", type=Path, default=PRED_DIR)
    args = parser.parse_args()

    if args.run_name is None:
        args.run_name = f"{args.backbone}_{args.mode}" + ("" if args.use_view else "_noview")

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    device: torch.device = get_device()
    logger.info(f"Run '{args.run_name}' on device {device} (backbone {args.backbone}, mode {args.mode})")

    df: pd.DataFrame = load_train_labels()
    exams: pd.DataFrame = exam_table(df)
    folds: List[Dict[str, Any]] = load_folds()

    if args.folds != "all":
        wanted = {tuple(int(x) for x in pair.split(":")) for pair in args.folds.split(",")}
        folds = [f for f in folds if (f["repeat"], f["fold"]) in wanted]
    logger.info(f"Training {len(folds)} fold(s) over {len(exams)} exams")

    all_predictions: List[pd.DataFrame] = []
    fold_reports: List[Dict[str, Any]] = []
    for spec in folds:
        predictions, report = train_one_fold(spec, df, exams, args, device)
        all_predictions.append(predictions)
        fold_reports.append(report)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    predictions_path: Path = args.out_dir / f"{args.run_name}.csv"
    pd.concat(all_predictions, ignore_index=True).to_csv(predictions_path, index=False)

    history_path: Path = BASE_DIR / "reports" / f"train_{args.run_name}.json"
    history_path.write_text(json.dumps({"args": vars(args) | {"out_dir": str(args.out_dir)}, "folds": fold_reports}, indent=2, default=str), encoding="utf-8")

    outer_scores = [r["outer_auroc_ge_f2"] for r in fold_reports if not np.isnan(r["outer_auroc_ge_f2"])]
    logger.info(f"Mean outer AUROC >=F2 across {len(outer_scores)} folds: {np.mean(outer_scores):.4f}")
    logger.info(f"Predictions -> {predictions_path}")
    print(f"\nScore with:\n  python evaluate.py --preds {predictions_path}")


if __name__ == "__main__":
    main()
