"""Multi-Organ (Liver + Gallbladder) Segmenter Engine."""

import logging
from pathlib import Path
from typing import Optional
import cv2
import numpy as np
import torch
import torch.nn as nn
from PIL import Image

from src.config import MULTIORGAN_SDK_PATH

logger = logging.getLogger("SmartLiva.MultiOrganSDK")

SEG_SIZE: int = 256
IMAGENET_MEAN: np.ndarray = np.array([0.485, 0.456, 0.406], np.float32)
IMAGENET_STD: np.ndarray = np.array([0.229, 0.224, 0.225], np.float32)
N_CLASSES: int = 3


def conv_block(in_ch: int, out_ch: int) -> nn.Sequential:
    """Two 3x3 convolutions with BN and ReLU."""
    return nn.Sequential(
        nn.Conv2d(in_ch, out_ch, 3, padding=1, bias=False),
        nn.BatchNorm2d(out_ch),
        nn.ReLU(inplace=True),
        nn.Conv2d(out_ch, out_ch, 3, padding=1, bias=False),
        nn.BatchNorm2d(out_ch),
        nn.ReLU(inplace=True),
    )


class SDKUNet(nn.Module):
    """4-level U-Net for 3-class segmentation (Background, Liver, Gallbladder)."""

    def __init__(self, n_classes: int = N_CLASSES, base: int = 32) -> None:
        super().__init__()
        self.d1 = conv_block(3, base)
        self.d2 = conv_block(base, base * 2)
        self.d3 = conv_block(base * 2, base * 4)
        self.d4 = conv_block(base * 4, base * 8)
        self.pool = nn.MaxPool2d(2)
        self.bott = conv_block(base * 8, base * 16)
        self.up4 = nn.ConvTranspose2d(base * 16, base * 8, 2, stride=2)
        self.u4 = conv_block(base * 16, base * 8)
        self.up3 = nn.ConvTranspose2d(base * 8, base * 4, 2, stride=2)
        self.u3 = conv_block(base * 8, base * 4)
        self.up2 = nn.ConvTranspose2d(base * 4, base * 2, 2, stride=2)
        self.u2 = conv_block(base * 4, base * 2)
        self.up1 = nn.ConvTranspose2d(base * 2, base, 2, stride=2)
        self.u1 = conv_block(base * 2, base)
        self.head = nn.Conv2d(base, n_classes, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        c1 = self.d1(x)
        c2 = self.d2(self.pool(c1))
        c3 = self.d3(self.pool(c2))
        c4 = self.d4(self.pool(c3))
        bottleneck = self.bott(self.pool(c4))
        x = self.u4(torch.cat([self.up4(bottleneck), c4], 1))
        x = self.u3(torch.cat([self.up3(x), c3], 1))
        x = self.u2(torch.cat([self.up2(x), c2], 1))
        x = self.u1(torch.cat([self.up1(x), c1], 1))
        return self.head(x)


def load_sdk_model(
    weights: Path = MULTIORGAN_SDK_PATH,
    device: Optional[torch.device] = None,
) -> Optional[nn.Module]:
    """Load Multi-Organ U-Net checkpoint."""
    if not weights.is_file():
        logger.info(f"Multi-Organ SDK checkpoint not found at {weights}")
        return None
    try:
        model = SDKUNet(N_CLASSES, base=32)
        state = torch.load(str(weights), map_location=device, weights_only=True)
        model.load_state_dict(state)
        logger.info(f"Successfully loaded Multi-Organ SDK weights from {weights}")
        return model.to(device).eval()
    except Exception as err:
        logger.warning(f"Could not load Multi-Organ SDK model: {err}")
        return None


def fan_mask(gray: np.ndarray, threshold: int = 10) -> np.ndarray:
    """Extract ultrasound fan sector mask."""
    binary: np.ndarray = (gray > threshold).astype(np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary, 8)
    if n_labels <= 1:
        return np.ones_like(binary)
    biggest: int = 1 + int(stats[1:, cv2.CC_STAT_AREA].argmax())
    fan: np.ndarray = (labels == biggest).astype(np.uint8)
    fan = cv2.morphologyEx(fan, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))
    return cv2.morphologyEx(fan, cv2.MORPH_DILATE, np.ones((5, 5), np.uint8))


def predict_sdk_mask(
    image: Image.Image,
    model: nn.Module,
    device: torch.device,
    use_fan: bool = True,
) -> np.ndarray:
    """Predict a {0: Background, 1: Liver, 2: Gallbladder} mask at native resolution."""
    width, height = image.size
    resized: np.ndarray = np.asarray(image.resize((SEG_SIZE, SEG_SIZE)), np.float32)
    normalized: np.ndarray = (resized / 255.0 - IMAGENET_MEAN) / IMAGENET_STD
    tensor: torch.Tensor = torch.from_numpy(normalized.transpose(2, 0, 1).astype(np.float32))

    with torch.no_grad():
        logits: torch.Tensor = model(tensor[None].to(device))
        small: np.ndarray = logits.argmax(1)[0].cpu().numpy().astype(np.uint8)

    mask: np.ndarray = np.asarray(Image.fromarray(small).resize((width, height), Image.NEAREST))

    if not use_fan:
        return mask
    gray: np.ndarray = np.asarray(image.convert("L"))
    return (mask * fan_mask(gray)).astype(np.uint8)
