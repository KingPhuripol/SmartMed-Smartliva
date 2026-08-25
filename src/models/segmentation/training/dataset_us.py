"""Dataset over the cached corpus, with the split read from disk rather than drawn.

Written as a new module rather than an edit to dataset.py, which loads the old
data/7272660 corpus in a different annotation format and is the provenance of the
checkpoint the fibrosis path is pinned to. That file stays as the historical record.

Three defects in the existing training path are fixed here by construction:

1. `train.py:70-78` splits with `random_split` over images, with no patient key
   available at all. Here the split is read from the frozen seg_splits.json, so
   train and val cannot share a patient.

2. `train.py:73` builds one dataset with `augment=True` and only then calls
   random_split, so the validation subset inherits random horizontal flips and
   val_dice is non-deterministic epoch to epoch. Here train and val are separate
   instances and `augment` is a constructor argument, not a property of a shared
   parent.

3. Augmentation was a horizontal flip and nothing else. Ultrasound gain and depth
   settings vary far more than left-right orientation does, so brightness/contrast
   jitter and small rotations are added -- those are the real domain shift between
   one scanner session and the next.

The 178 annotation-gap images are dropped from TRAINING only. They carry a
gallbladder polygon and no liver polygon, but the liver is in frame (measured: the
model's predicted liver area on them matches the annotated area on comparable
labelled images). Training on them as all-background liver targets would teach the
model to suppress liver that is genuinely there. They stay in val and test, where
the evaluator reports them as a diagnostic and excludes them from Dice.
"""

import logging
import random
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
import torch
from torch.utils.data import Dataset

from cache import load_index, open_arrays
from views import LIVER

IMAGENET_MEAN: np.ndarray = np.array([0.485, 0.456, 0.406], np.float32)
IMAGENET_STD: np.ndarray = np.array([0.229, 0.224, 0.225], np.float32)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger: logging.Logger = logging.getLogger("SmartLiva.SegDataset")


def worker_init_fn(worker_id: int) -> None:
    """Reseed every RNG a worker might touch.

    DataLoader reseeds torch's per-worker generator but not Python's `random` or
    NumPy's global RNG. Forked workers otherwise inherit the parent's state and can
    draw correlated augmentations for different images in the same step.
    """
    info = torch.utils.data.get_worker_info()
    seed: int = int(info.seed) % (2**32) if info is not None else worker_id
    random.seed(seed)
    np.random.seed(seed)


class UltrasoundSegDataset(Dataset):
    """Cached ultrasound frames and their {0,1,2} masks for one split.

    Args:
        split: "train", "val" or "test", matched against the frozen assignment.
        augment: apply training augmentation. Must be False for val and test.
        grayscale: emit 1 channel scaled to [0,1] instead of 3-channel ImageNet-
            normalized RGB. Arm C's U-Net takes 1 channel; arms A and B take 3.
        binary_liver: collapse the mask to {0,1} liver-vs-rest. Arm C is liver-only.
        drop_annotation_gaps: exclude images with no liver polygon. Defaults to True
            for training splits and is forced False elsewhere.
    """

    def __init__(
        self,
        split: str,
        augment: bool = False,
        grayscale: bool = False,
        binary_liver: bool = False,
        drop_annotation_gaps: Optional[bool] = None,
        seed: int = 42,
    ) -> None:
        if augment and split != "train":
            raise ValueError(
                f"augment=True with split={split!r}. Augmenting a held-out split makes its "
                f"score non-deterministic -- this is the exact defect at train.py:73."
            )

        index = load_index()
        self.images, self.masks = open_arrays()
        self.augment: bool = augment
        self.grayscale: bool = grayscale
        self.binary_liver: bool = binary_liver
        self.rng: random.Random = random.Random(seed)

        if drop_annotation_gaps is None:
            drop_annotation_gaps = split == "train"
        if drop_annotation_gaps and split != "train":
            raise ValueError("annotation gaps are only dropped from training")

        self.rows: List[Dict] = []
        self.indices: List[int] = []
        for position, row in enumerate(index["rows"]):
            if row["split"] != split:
                continue
            if drop_annotation_gaps and not row["has_liver"]:
                continue
            self.rows.append(row)
            self.indices.append(position)

        n_dropped = sum(
            1 for row in index["rows"] if row["split"] == split and not row["has_liver"]
        )
        logger.info(
            f"{split}: {len(self.indices)} images"
            + (f" ({n_dropped} annotation gaps dropped)" if drop_annotation_gaps else "")
            + f", augment={augment}, grayscale={grayscale}, binary_liver={binary_liver}"
        )

    def __len__(self) -> int:
        return len(self.indices)

    def _augment(self, image: np.ndarray, mask: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Horizontal flip, small rotation, and brightness/contrast jitter."""
        if self.rng.random() < 0.5:
            image = np.ascontiguousarray(image[:, ::-1])
            mask = np.ascontiguousarray(mask[:, ::-1])

        if self.rng.random() < 0.5:
            angle: float = self.rng.uniform(-10.0, 10.0)
            scale: float = self.rng.uniform(0.92, 1.08)
            size: int = image.shape[0]
            matrix = cv2.getRotationMatrix2D((size / 2, size / 2), angle, scale)
            image = cv2.warpAffine(image, matrix, (size, size), flags=cv2.INTER_LINEAR,
                                   borderMode=cv2.BORDER_CONSTANT, borderValue=0)
            mask = cv2.warpAffine(mask, matrix, (size, size), flags=cv2.INTER_NEAREST,
                                  borderMode=cv2.BORDER_CONSTANT, borderValue=0)

        if self.rng.random() < 0.5:
            # Gain and dynamic-range variation, the realest shift between sessions.
            gain: float = self.rng.uniform(0.85, 1.15)
            bias: float = self.rng.uniform(-18.0, 18.0)
            image = np.clip(image.astype(np.float32) * gain + bias, 0, 255).astype(np.uint8)

        return image, mask

    def __getitem__(self, position: int) -> Tuple[torch.Tensor, torch.Tensor]:
        row_index: int = self.indices[position]
        image: np.ndarray = np.asarray(self.images[row_index])
        mask: np.ndarray = np.asarray(self.masks[row_index])

        if self.augment:
            image, mask = self._augment(image, mask)

        if self.binary_liver:
            mask = (mask == LIVER).astype(np.uint8)

        if self.grayscale:
            gray: np.ndarray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
            tensor = torch.from_numpy(gray).unsqueeze(0)
        else:
            normalized: np.ndarray = (image.astype(np.float32) / 255.0 - IMAGENET_MEAN) / IMAGENET_STD
            tensor = torch.from_numpy(normalized.transpose(2, 0, 1).astype(np.float32))

        return tensor, torch.from_numpy(mask.astype(np.int64))
