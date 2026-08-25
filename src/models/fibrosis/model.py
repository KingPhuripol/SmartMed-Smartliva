"""FibrosisNet: an ImageNet backbone with a regression head and two auxiliary heads.

The primary target is log stiffness, not a class. `TE result` is a deterministic binning
of `TE(kPa)` at 6.0/7.1/8.7/10.3, so regression keeps information that classification
throws away -- an F0 at 2.4 kPa and an F0 at 5.9 kPa are very different, while an F0 at
5.9 and an F1 at 6.0 are physically indistinguishable. It also means every one of the
730 exams contributes graded signal, which matters when F3 has only 37 of them.

Two auxiliary heads ride along:
  * CORN ordinal head -- explicitly shapes decision boundaries at the four clinical
    cutoffs, which pure regression does not, and yields calibrated P(stage >= k).
  * SWE head -- free supervision from a second elastography modality, masked on the
    46 rows where it is missing. It is never an input; it is unavailable at inference.
"""

import logging
import sys
from pathlib import Path
from typing import Dict, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F
import torchvision

from labels import STAGES, SWE_STAGES
from dataset import UNKNOWN_VIEW

BASE_DIR: Path = Path(__file__).resolve().parent
SEGMENTATION_DIR: Path = BASE_DIR.parent / "segmentation"

N_STAGES: int = len(STAGES)
N_CORN_TASKS: int = N_STAGES - 1

logger: logging.Logger = logging.getLogger("SmartLiva.FibrosisModel")


def get_device() -> torch.device:
    """Reuse the project's canonical device selection from models/segmentation/train.py.

    The project imports sibling modules flatly (`from model import UNet`), so importing
    the segmentation package from here would bind the names `dataset`, `model` and
    `train` to the wrong files. The import is therefore performed with the segmentation
    directory temporarily first on the path, and the polluted entries are restored
    afterwards. If anything about that fails, fall back to the same MPS/CUDA/CPU order.
    """
    collide: Tuple[str, ...] = ("dataset", "model", "train")
    saved = {name: sys.modules.pop(name) for name in collide if name in sys.modules}
    sys.path.insert(0, str(SEGMENTATION_DIR))
    try:
        import train as segmentation_train  # noqa: PLC0415 - deliberately scoped

        return segmentation_train.get_device()
    except Exception as err:  # pragma: no cover - defensive
        logger.warning(f"Could not reuse segmentation get_device ({err}); using local fallback")
        if torch.backends.mps.is_available():
            return torch.device("mps")
        if torch.cuda.is_available():
            return torch.device("cuda")
        return torch.device("cpu")
    finally:
        sys.path.remove(str(SEGMENTATION_DIR))
        for name in collide:
            sys.modules.pop(name, None)
        sys.modules.update(saved)


def build_backbone(name: str, pretrained: bool = True) -> Tuple[nn.Module, int]:
    """Load a torchvision backbone with its classifier removed; return (module, feature dim)."""
    weights: str | None = "DEFAULT" if pretrained else None
    net: nn.Module = torchvision.models.get_model(name, weights=weights)

    if hasattr(net, "fc") and isinstance(net.fc, nn.Linear):  # resnet family
        feature_dim: int = net.fc.in_features
        net.fc = nn.Identity()
        return net, feature_dim

    if hasattr(net, "classifier"):
        classifier = net.classifier
        if isinstance(classifier, nn.Linear):  # densenet
            feature_dim = classifier.in_features
            net.classifier = nn.Identity()
            return net, feature_dim
        # efficientnet: Sequential(Dropout, Linear); convnext: Sequential(Norm, Flatten, Linear)
        for i in range(len(classifier) - 1, -1, -1):
            if isinstance(classifier[i], nn.Linear):
                feature_dim = classifier[i].in_features
                classifier[i] = nn.Identity()
                return net, feature_dim

    raise ValueError(f"Unsupported backbone: {name!r}")


class FibrosisNet(nn.Module):
    """Backbone + view embedding, feeding a regression head and two auxiliary heads."""

    def __init__(
        self,
        backbone: str = "convnext_tiny",
        pretrained: bool = True,
        use_view: bool = True,
        dropout: float = 0.3,
        view_dim: int = 8,
    ) -> None:
        super().__init__()
        self.backbone_name: str = backbone
        self.use_view: bool = use_view

        self.backbone, feature_dim = build_backbone(backbone, pretrained)

        # Views carry near-identical label distributions (mean kPa 5.71 / 5.66 / 5.74),
        # so one shared model with a view embedding beats three per-view models each
        # trained on a third of the data.
        head_dim: int = feature_dim
        if use_view:
            self.view_embed = nn.Embedding(UNKNOWN_VIEW + 1, view_dim)
            head_dim += view_dim

        self.dropout = nn.Dropout(dropout)
        self.head_regression = nn.Linear(head_dim, 1)
        self.head_corn = nn.Linear(head_dim, N_CORN_TASKS)
        self.head_swe = nn.Linear(head_dim, len(SWE_STAGES))

    def features(self, image: torch.Tensor, view_index: torch.Tensor) -> torch.Tensor:
        """Pooled backbone features, optionally concatenated with the view embedding."""
        pooled: torch.Tensor = self.backbone(image)
        if self.use_view:
            pooled = torch.cat([pooled, self.view_embed(view_index)], dim=1)
        return self.dropout(pooled)

    def forward(self, image: torch.Tensor, view_index: torch.Tensor) -> Dict[str, torch.Tensor]:
        pooled: torch.Tensor = self.features(image, view_index)
        return {
            "log_kpa": self.head_regression(pooled).squeeze(1),
            "corn": self.head_corn(pooled),
            "swe": self.head_swe(pooled),
        }

    def parameter_groups(self, head_lr: float, backbone_lr: float) -> list:
        """Discriminative learning rates: a pretrained backbone should move slowly."""
        head_parameters = list(self.head_regression.parameters()) + list(self.head_corn.parameters()) + list(self.head_swe.parameters())
        if self.use_view:
            head_parameters += list(self.view_embed.parameters())
        return [
            {"params": self.backbone.parameters(), "lr": backbone_lr},
            {"params": head_parameters, "lr": head_lr},
        ]


def corn_loss(logits: torch.Tensor, stage_index: torch.Tensor) -> torch.Tensor:
    """Conditional ordinal regression loss (CORN, Shi et al.).

    Task k models P(stage > k | stage >= k) and is trained only on the samples that
    actually reach stage k. Unlike CORAL it imposes no shared-weight rank constraint,
    and unlike plain cross-entropy it knows the stages are ordered.
    """
    total: torch.Tensor = logits.new_zeros(())
    counted: int = 0

    for k in range(N_CORN_TASKS):
        subset: torch.Tensor = stage_index >= k
        n: int = int(subset.sum())
        if n == 0:
            continue
        target: torch.Tensor = (stage_index[subset] > k).float()
        total = total + F.binary_cross_entropy_with_logits(logits[subset, k], target, reduction="sum")
        counted += n

    return total / max(counted, 1)


def corn_cumulative_probs(logits: torch.Tensor) -> torch.Tensor:
    """Convert CORN logits to P(stage >= k) for k = 1..4, shape [B, 4].

    The conditional probabilities chain multiplicatively, which is what keeps the
    resulting cumulative probabilities monotonically non-increasing by construction.
    """
    return torch.cumprod(torch.sigmoid(logits), dim=1)


def masked_swe_loss(logits: torch.Tensor, swe_index: torch.Tensor, ignore_index: int = -1) -> torch.Tensor:
    """Cross-entropy over the SWE auxiliary head, skipping rows with no SWE reading."""
    valid: torch.Tensor = swe_index != ignore_index
    if not bool(valid.any()):
        return logits.new_zeros(())
    return F.cross_entropy(logits[valid], swe_index[valid])


class FibrosisLoss(nn.Module):
    """Huber on log-kPa, plus the CORN and SWE auxiliaries at fixed weights."""

    def __init__(self, corn_weight: float = 0.3, swe_weight: float = 0.1, huber_delta: float = 0.3) -> None:
        super().__init__()
        self.corn_weight: float = corn_weight
        self.swe_weight: float = swe_weight
        self.huber_delta: float = huber_delta

    def forward(self, outputs: Dict[str, torch.Tensor], batch: Dict[str, torch.Tensor]) -> Dict[str, torch.Tensor]:
        regression: torch.Tensor = F.huber_loss(outputs["log_kpa"], batch["log_kpa"], delta=self.huber_delta)
        ordinal: torch.Tensor = corn_loss(outputs["corn"], batch["stage_index"]) if self.corn_weight > 0 else regression.new_zeros(())
        swe: torch.Tensor = masked_swe_loss(outputs["swe"], batch["swe_index"]) if self.swe_weight > 0 else regression.new_zeros(())

        return {
            "total": regression + self.corn_weight * ordinal + self.swe_weight * swe,
            "regression": regression,
            "corn": ordinal,
            "swe": swe,
        }
