"""Train a segmentation arm against the frozen split, and write down what happened.

The existing `train.py` printed val_dice to stdout and nothing else. There is no log
file, no metrics JSON and no TensorBoard anywhere in the project, so the score of the
checkpoint currently in production is unrecoverable -- the single most consequential
gap found while surveying this codebase. Every run here appends to a JSONL log and
writes a metrics JSON beside its checkpoint, so this month's numbers survive.

Two arms:

  B  fine-tune the SDK 3-class checkpoint (RGB, ImageNet-normalized, bg/liver/GB)
     at a low LR. Arm A measured that checkpoint at 0.9323 macro liver Dice without
     any training, so this asks what 7,378 in-domain images add on top.

  C  train the project's own 1-channel, 1-class U-Net from scratch on the same
     split, liver only. The control: if C matches B, the SDK weights add nothing and
     the pipeline can be owned outright with no licence question attached.

The bar is set by arm A, not by zero. Per the plan's anti-sunk-cost rule, a trained
arm must beat 0.9323 by at least 0.01 macro Dice on val to be worth shipping over a
checkpoint that costs nothing to run.

Validation during training is a fast proxy: mean per-image liver Dice at 256px on
the cached val masks, not the full native-resolution per-view evaluation. Model
selection uses it; the reported benchmark always comes from evaluate_seg.py, which
scores at native resolution through the same path every arm is measured on.
"""

import argparse
import json
import logging
import random
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader

from dataset_us import UltrasoundSegDataset, worker_init_fn
from views import LIVER, REPORTS_DIR

CHECKPOINT_DIR: Path = Path(__file__).resolve().parent / "checkpoints"
LOG_PATH: Path = REPORTS_DIR / "train_log.jsonl"

# Arm A's measured macro liver Dice on val, and the margin a trained arm must add.
ARM_A_MACRO_DICE: float = 0.9323
MIN_IMPROVEMENT: float = 0.01

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger: logging.Logger = logging.getLogger("SmartLiva.SegTrain")


def seed_everything(seed: int) -> None:
    """Seed every RNG in play, including Python's -- which train.py never did."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def get_device() -> torch.device:
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def soft_dice_loss(logits: torch.Tensor, target: torch.Tensor, n_classes: int,
                   eps: float = 1.0) -> torch.Tensor:
    """Mean soft Dice loss over the non-background classes.

    Background is excluded because it is 80%+ of every frame; including it lets a
    model that predicts nothing but background score well on the Dice term.
    """
    probs: torch.Tensor = F.softmax(logits, dim=1)
    onehot: torch.Tensor = F.one_hot(target, n_classes).permute(0, 3, 1, 2).float()
    dims = (0, 2, 3)
    intersection: torch.Tensor = (probs * onehot).sum(dims)
    cardinality: torch.Tensor = probs.sum(dims) + onehot.sum(dims)
    dice_per_class: torch.Tensor = (2.0 * intersection + eps) / (cardinality + eps)
    return 1.0 - dice_per_class[1:].mean()


class CEDiceLoss(nn.Module):
    """Weighted cross-entropy plus soft Dice.

    Class weights counter area imbalance: liver covers ~18% of a frame and
    gallbladder ~2.4%, so an unweighted CE is dominated by background pixels.
    """

    def __init__(self, n_classes: int, class_weights: Optional[torch.Tensor] = None) -> None:
        super().__init__()
        self.n_classes = n_classes
        self.ce = nn.CrossEntropyLoss(weight=class_weights)

    def forward(self, logits: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        return self.ce(logits, target) + soft_dice_loss(logits, target, self.n_classes)


def build_arm(arm: str, device: torch.device) -> Tuple[nn.Module, Dict[str, Any]]:
    """Construct the model and the arm's configuration."""
    if arm == "B":
        from model_sdk import SDKUNet, SDK_WEIGHTS

        model = SDKUNet(n_classes=3, base=32)
        state = torch.load(str(SDK_WEIGHTS), map_location="cpu", weights_only=True)
        model.load_state_dict(state)
        config: Dict[str, Any] = {
            "n_classes": 3,
            "grayscale": False,
            "binary_liver": False,
            "lr": 1e-4,  # fine-tuning: 1e-3 would wash out what the checkpoint knows
            "class_weights": [0.3, 1.0, 1.5],
            "init": f"SDK checkpoint {SDK_WEIGHTS.name}",
        }
        logger.info("arm B: fine-tuning the SDK 3-class checkpoint")
    elif arm == "C":
        from model import UNet

        model = UNet(in_ch=1, out_ch=2)
        config = {
            "n_classes": 2,
            "grayscale": True,
            "binary_liver": True,
            "lr": 1e-3,  # from scratch
            "class_weights": [0.3, 1.0],
            "init": "random",
        }
        logger.info("arm C: training the project U-Net from scratch, liver only")
    else:
        raise ValueError(f"unknown arm {arm!r}. Known: B, C")

    return model.to(device), config


@torch.no_grad()
def validate(model: nn.Module, loader: DataLoader, device: torch.device) -> float:
    """Mean per-image liver Dice at cache resolution -- the model-selection proxy."""
    model.eval()
    scores: list = []
    for images, masks in loader:
        images = images.to(device)
        pred: torch.Tensor = model(images).argmax(1).cpu()
        for p, t in zip(pred, masks):
            truth = t == LIVER
            if not truth.any():
                continue  # Dice undefined on empty ground truth
            predicted = p == LIVER
            total = int(truth.sum()) + int(predicted.sum())
            scores.append(2.0 * float((predicted & truth).sum()) / total)
    return float(np.mean(scores)) if scores else 0.0


def train(arm: str, epochs: int, batch_size: int, workers: int, seed: int,
          out: Optional[Path] = None) -> Dict[str, Any]:
    """Train one arm and return its run record."""
    seed_everything(seed)
    device = get_device()
    model, config = build_arm(arm, device)

    train_ds = UltrasoundSegDataset(
        "train", augment=True, grayscale=config["grayscale"],
        binary_liver=config["binary_liver"], seed=seed,
    )
    val_ds = UltrasoundSegDataset(
        "val", augment=False, grayscale=config["grayscale"],
        binary_liver=config["binary_liver"], seed=seed,
    )
    train_loader = DataLoader(
        train_ds, batch_size=batch_size, shuffle=True, num_workers=workers,
        worker_init_fn=worker_init_fn, drop_last=True,
    )
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False, num_workers=workers,
                            worker_init_fn=worker_init_fn)

    weights = torch.tensor(config["class_weights"], dtype=torch.float32, device=device)
    criterion = CEDiceLoss(config["n_classes"], class_weights=weights)
    optimizer = torch.optim.AdamW(model.parameters(), lr=config["lr"], weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    checkpoint_path: Path = out or CHECKPOINT_DIR / f"arm_{arm}_best.pt"
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    best_dice: float = 0.0
    best_epoch: int = -1
    history: list = []
    started: float = time.time()

    for epoch in range(epochs):
        model.train()
        epoch_loss: float = 0.0
        n_batches: int = 0
        epoch_started: float = time.time()

        for images, masks in train_loader:
            images, masks = images.to(device), masks.to(device)
            optimizer.zero_grad(set_to_none=True)
            loss = criterion(model(images), masks)
            loss.backward()
            optimizer.step()
            epoch_loss += float(loss.item())
            n_batches += 1

        scheduler.step()
        val_dice: float = validate(model, val_loader, device)
        record: Dict[str, Any] = {
            "arm": arm,
            "epoch": epoch,
            "train_loss": round(epoch_loss / max(n_batches, 1), 6),
            "val_liver_dice_256": round(val_dice, 6),
            "lr": round(scheduler.get_last_lr()[0], 8),
            "epoch_s": round(time.time() - epoch_started, 1),
            "seed": seed,
        }
        history.append(record)
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")

        marker: str = ""
        if val_dice > best_dice:
            best_dice, best_epoch = val_dice, epoch
            torch.save(model.state_dict(), checkpoint_path)
            marker = "  <- best"
        logger.info(
            f"arm {arm} epoch {epoch:3d}  loss {record['train_loss']:.4f}  "
            f"val_dice(256) {val_dice:.4f}  {record['epoch_s']:.0f}s{marker}"
        )

    elapsed: float = time.time() - started
    summary: Dict[str, Any] = {
        "arm": arm,
        "config": config,
        "epochs": epochs,
        "batch_size": batch_size,
        "seed": seed,
        "n_train": len(train_ds),
        "n_val": len(val_ds),
        "best_epoch": best_epoch,
        "best_val_liver_dice_256": round(best_dice, 6),
        "checkpoint": str(checkpoint_path),
        "elapsed_s": round(elapsed, 1),
        "device": str(device),
        "history": history,
        "note": (
            "val_liver_dice_256 is a model-selection proxy computed at cache resolution. "
            "The reported benchmark comes from evaluate_seg.py at native resolution."
        ),
    }
    metrics_path: Path = REPORTS_DIR / f"train_{arm}_metrics.json"
    metrics_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    logger.info(
        f"arm {arm} done in {elapsed / 60:.1f} min. best val_dice(256) {best_dice:.4f} "
        f"at epoch {best_epoch} -> {checkpoint_path}"
    )
    logger.info(
        f"arm A reference is {ARM_A_MACRO_DICE:.4f} macro at native resolution; this arm "
        f"must clear {ARM_A_MACRO_DICE + MIN_IMPROVEMENT:.4f} there to be worth shipping."
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a segmentation arm")
    parser.add_argument("--arm", required=True, choices=("B", "C"))
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch_size", type=int, default=16)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    train(args.arm, args.epochs, args.batch_size, args.workers, args.seed, args.out)


if __name__ == "__main__":
    main()
