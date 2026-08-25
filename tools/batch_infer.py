"""
Batch run liver segmentation on raw ultrasound datasets.
This script traverses patient directories, runs the U-Net model,
and saves the binary masks as `<image_name>_mask.png`.
"""

import argparse
import sys
import logging
from pathlib import Path
from tqdm import tqdm
import cv2
import numpy as np
import torch

BASE_DIR = Path(__file__).resolve().parent.parent
SEGMENTATION_DIR = BASE_DIR / "models" / "segmentation"
sys.path.insert(0, str(SEGMENTATION_DIR))

try:
    from model import UNet
    from train import get_device
except ImportError:
    print("Error: Ensure models/segmentation/model.py exists.")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("SmartLiva.BatchSegment")

IMG_EXTS = (".jpg", ".jpeg", ".png", ".bmp")
SEG_CKPT = BASE_DIR / "models" / "segmentation" / "checkpoints" / "liver_unet_best.pt"

def extract_ultrasound_cone(gray_image: np.ndarray) -> np.ndarray:
    _, thresh = cv2.threshold(gray_image, 10, 255, cv2.THRESH_BINARY)
    kernel = np.ones((15, 15), np.uint8)
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
    opened = cv2.morphologyEx(closed, cv2.MORPH_OPEN, kernel)
    
    contours, _ = cv2.findContours(opened, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    outline_mask = np.zeros_like(gray_image)
    if contours:
        largest_contour = max(contours, key=cv2.contourArea)
        cv2.drawContours(outline_mask, [largest_contour], -1, 1, thickness=cv2.FILLED)
    else:
        outline_mask.fill(1)
    return outline_mask

def predict_mask(seg_model: UNet, device: torch.device, img_path: Path, img_size: int = 256) -> np.ndarray:
    gray = cv2.imread(str(img_path), cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise ValueError(f"Failed to read image at: {img_path}")

    resized = cv2.resize(gray, (img_size, img_size), interpolation=cv2.INTER_LINEAR)
    x = torch.from_numpy(resized.astype(np.float32) / 255.0).unsqueeze(0).unsqueeze(0).to(device)

    with torch.no_grad():
        pred_prob = torch.sigmoid(seg_model(x))[0, 0].cpu().numpy()

    mask = (pred_prob > 0.5).astype(np.uint8)
    mask_full = cv2.resize(mask, (gray.shape[1], gray.shape[0]), interpolation=cv2.INTER_NEAREST)
    
    outline_mask = extract_ultrasound_cone(gray)
    mask_full = mask_full & outline_mask
    
    return mask_full

def get_image_paths(root_dir: Path) -> list[Path]:
    paths = []
    # Recursively find all images
    for ext in IMG_EXTS:
        for p in root_dir.rglob(f"*{ext}"):
            # Skip already generated masks
            if not p.name.endswith("_mask.png"):
                paths.append(p)
    return sorted(paths)

def main():
    parser = argparse.ArgumentParser(description="Batch Liver Segmentation (U-Net)")
    parser.add_argument("--data_dir", type=Path, default=BASE_DIR / "data" / "Normal แยกบริเวณตรวจ", help="Root directory containing patient folders")
    parser.add_argument("--img_size", type=int, default=256, help="Input size for U-Net")
    parser.add_argument("--limit", type=int, default=None, help="Process only first N images for testing")
    parser.add_argument("--force", action="store_true", help="Overwrite existing masks")
    args = parser.parse_args()

    if not args.data_dir.exists():
        logger.error(f"Data directory not found: {args.data_dir}")
        return

    logger.info(f"Scanning directory: {args.data_dir}")
    all_images = get_image_paths(args.data_dir)
    if args.limit:
        all_images = all_images[:args.limit]
        
    logger.info(f"Found {len(all_images)} images to process.")
    
    # Check for existing masks to resume
    if not args.force:
        pending_images = []
        for p in all_images:
            mask_path = p.with_name(f"{p.stem}_mask.png")
            if not mask_path.exists():
                pending_images.append(p)
        logger.info(f"Skipping {len(all_images) - len(pending_images)} already processed images.")
        all_images = pending_images
        
    if not all_images:
        logger.info("All images are already segmented. Exiting.")
        return

    # Load Model
    device = get_device()
    logger.info(f"Loading U-Net on device: {device}")
    seg_model = UNet(in_ch=1, out_ch=1).to(device)
    
    if not SEG_CKPT.exists():
        logger.error(f"Model checkpoint not found: {SEG_CKPT}")
        return
        
    seg_model.load_state_dict(torch.load(str(SEG_CKPT), map_location=device, weights_only=True))
    seg_model.eval()

    logger.info("Starting batch segmentation...")
    success_count = 0
    error_count = 0
    
    for img_path in tqdm(all_images, desc="Segmenting", unit="img"):
        mask_path = img_path.with_name(f"{img_path.stem}_mask.png")
        try:
            mask = predict_mask(seg_model, device, img_path, args.img_size)
            # Save binary mask (0 and 255)
            cv2.imwrite(str(mask_path), mask * 255)
            success_count += 1
        except Exception as e:
            logger.error(f"Error processing {img_path}: {e}")
            error_count += 1

    logger.info(f"Batch segmentation completed. Success: {success_count}, Errors: {error_count}")

if __name__ == "__main__":
    main()
