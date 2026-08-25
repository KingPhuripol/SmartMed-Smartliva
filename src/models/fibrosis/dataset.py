"""PyTorch dataset and augmentation pipeline for fibrosis staging.

Reads the 320x320 preprocessed cache built by cache_build.py and crops to the model's
input size, so a training epoch never touches a full-resolution PNG.

The augmentation is doing double duty. Beyond the usual regularisation, the wide-scale
RandomResizedCrop destroys the residual resolution and framing fingerprint that the
metadata-only baseline (B3) proved is correlated with the label in this dataset.
Vertical flips are deliberately absent: depth direction in ultrasound is anatomically
meaningful and mirroring it produces images that cannot occur.
"""

import logging
import random
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
import pandas as pd
import torch
from torch.utils.data import Dataset
from torchvision.transforms import v2

from cache_build import cache_path
from labels import SWE_STAGES, VIEWS

IMAGENET_MEAN: Tuple[float, float, float] = (0.485, 0.456, 0.406)
IMAGENET_STD: Tuple[float, float, float] = (0.229, 0.224, 0.225)

VIEW_TO_INDEX: Dict[str, int] = {view: i for i, view in enumerate(VIEWS)}
UNKNOWN_VIEW: int = len(VIEWS)  # inference may not know the acquisition view
SWE_TO_INDEX: Dict[str, int] = {stage: i for i, stage in enumerate(SWE_STAGES)}
SWE_IGNORE: int = -1  # 46 rows have no SWE reading; masked out of the auxiliary loss

logger: logging.Logger = logging.getLogger("SmartLiva.FibrosisDataset")


class SpeckleNoise(torch.nn.Module):
    """Multiplicative noise approximating ultrasound speckle, applied to [0,1] tensors."""

    def __init__(self, sigma_max: float = 0.03, p: float = 0.3) -> None:
        super().__init__()
        self.sigma_max: float = sigma_max
        self.p: float = p

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if random.random() >= self.p:
            return x
        sigma: float = random.uniform(0.0, self.sigma_max)
        return (x * (1.0 + torch.randn_like(x) * sigma)).clamp_(0.0, 1.0)


def build_transforms(img_size: int = 256, train: bool = False) -> v2.Compose:
    """Return the augmentation pipeline for training or the deterministic one for evaluation."""
    if not train:
        return v2.Compose(
            [
                v2.Resize((img_size, img_size), antialias=True),
                v2.ToDtype(torch.float32, scale=True),
                v2.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
            ]
        )

    return v2.Compose(
        [
            v2.RandomResizedCrop(img_size, scale=(0.6, 1.0), ratio=(0.8, 1.25), antialias=True),
            v2.RandomHorizontalFlip(p=0.5),
            v2.RandomAffine(degrees=7, translate=(0.05, 0.05), shear=5),
            v2.ColorJitter(brightness=0.25, contrast=0.25),
            v2.RandomApply([v2.GaussianBlur(kernel_size=3, sigma=(0.1, 1.5))], p=0.2),
            v2.ToDtype(torch.float32, scale=True),
            SpeckleNoise(sigma_max=0.03, p=0.3),
            v2.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
            v2.RandomErasing(p=0.25, scale=(0.02, 0.1)),
        ]
    )


class FibrosisDataset(Dataset):
    """Image-level dataset over the preprocessed cache.

    Targets returned per item:
        log_kpa      -- primary regression target
        stage_index  -- ordinal 0..4, drives the CORN auxiliary head
        swe_index    -- auxiliary target from the second elastography modality, or -1
        view_index   -- metadata input, embedded by the model
    """

    def __init__(
        self,
        df: pd.DataFrame,
        mode: str = "roi_masked_bbox",
        img_size: int = 256,
        train: bool = False,
        use_view: bool = True,
    ) -> None:
        self.records: List[Dict[str, object]] = df.to_dict("records")
        self.mode: str = mode
        self.img_size: int = img_size
        self.use_view: bool = use_view
        self.transform: v2.Compose = build_transforms(img_size, train=train)

    def __len__(self) -> int:
        return len(self.records)

    def _read(self, image_name: str) -> np.ndarray:
        path: Path = cache_path(self.mode, str(image_name))
        image: Optional[np.ndarray] = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise FileNotFoundError(f"Cached image missing: {path}. Run cache_build.py --modes {self.mode}")
        return image

    def __getitem__(self, idx: int) -> Dict[str, torch.Tensor]:
        record: Dict[str, object] = self.records[idx]

        gray: np.ndarray = self._read(str(record["image_name"]))
        # Replicate to 3 channels rather than averaging the stem, so the ImageNet
        # first-layer filters stay intact.
        tensor: torch.Tensor = torch.from_numpy(gray).unsqueeze(0).repeat(3, 1, 1)
        image: torch.Tensor = self.transform(tensor)

        swe_raw = record.get("swe_stage")
        swe_index: int = SWE_TO_INDEX.get(swe_raw, SWE_IGNORE) if isinstance(swe_raw, str) else SWE_IGNORE
        view_index: int = VIEW_TO_INDEX.get(str(record.get("view")), UNKNOWN_VIEW) if self.use_view else UNKNOWN_VIEW

        return {
            "image": image,
            "log_kpa": torch.tensor(float(np.log(float(record["kpa"]))), dtype=torch.float32),
            "stage_index": torch.tensor(int(record["stage_index"]), dtype=torch.long),
            "swe_index": torch.tensor(swe_index, dtype=torch.long),
            "view_index": torch.tensor(view_index, dtype=torch.long),
            "index": torch.tensor(idx, dtype=torch.long),
        }
