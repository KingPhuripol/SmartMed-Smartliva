"""Quick standalone test script for MedSAM2 inference."""

import os
import sys
from pathlib import Path
import cv2
import matplotlib.pyplot as plt
import numpy as np
import torch

BASE_DIR = Path(__file__).resolve().parent.parent
medsam_pkg = BASE_DIR / "third_party" / "MedSAM2"
if str(medsam_pkg) not in sys.path:
    sys.path.insert(0, str(medsam_pkg))

from sam2.build_sam import build_sam2
from sam2.sam2_image_predictor import SAM2ImagePredictor


def main():
    if torch.backends.mps.is_available():
        device = "mps"
    elif torch.cuda.is_available():
        device = "cuda"
    else:
        device = "cpu"
    print(f"Using device: {device}")

    checkpoint_path = BASE_DIR / "weights" / "medsam2" / "MedSAM2_latest.pt"
    model_cfg = "configs/sam2.1_hiera_t512.yaml"

    print("Loading MedSAM2 model...")
    sam2_model = build_sam2(model_cfg, str(checkpoint_path), device=device)
    predictor = SAM2ImagePredictor(sam2_model)

    # Pick an ultrasound test image
    sample_images = list(BASE_DIR.glob("data/**/*.jpg"))
    if not sample_images:
        print("No sample images found in data/")
        return

    img_path = str(sample_images[0])
    print(f"Loading image from {img_path}...")
    image = cv2.imread(img_path)
    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

    predictor.set_image(image_rgb)
    H, W = image.shape[:2]
    box = np.array([[W * 0.2, H * 0.2, W * 0.8, H * 0.8]])

    masks, scores, logits = predictor.predict(
        point_coords=None,
        point_labels=None,
        box=box,
        multimask_output=False,
    )

    score = scores[0]
    print(f"Prediction complete! Confidence Score: {score:.4f}")

    # Visualize and save to outputs/visuals
    out_dir = BASE_DIR / "outputs" / "visuals"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "medsam2_test_output.png"

    plt.figure(figsize=(10, 10))
    plt.imshow(image_rgb)
    mask = masks[0]
    color = np.array([30 / 255, 144 / 255, 255 / 255, 0.6])
    h, w = mask.shape[-2:]
    mask_image = mask.reshape(h, w, 1) * color.reshape(1, 1, -1)
    plt.gca().imshow(mask_image)
    plt.axis("off")
    plt.title(f"MedSAM2 Prediction (Score: {score:.4f})")
    plt.savefig(str(out_path), bbox_inches="tight", pad_inches=0)
    plt.close()
    print(f"✅ Saved visualization to {out_path}")


if __name__ == "__main__":
    main()
