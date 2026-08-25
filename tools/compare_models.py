import os
import sys
import cv2
import numpy as np
import matplotlib.pyplot as plt
import torch
from pathlib import Path

# === 1. Setup paths ===
BASE_DIR = Path("/Users/king_phuripol/AI-Engineer/01_Projects/Aong-Task/SmartMed/New-SmartLiva")
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "MedSAM2"))

# Import U-Net
SEGMENTATION_DIR = BASE_DIR / "models" / "segmentation"
sys.path.insert(0, str(SEGMENTATION_DIR))
from model import UNet
from train import get_device

sys.path.insert(0, str(BASE_DIR))
from combined_infer import predict_mask

# Import MedSAM2
from sam2.build_sam import build_sam2
from sam2.sam2_image_predictor import SAM2ImagePredictor

def main():
    img_path_str = str(BASE_DIR / "data/Normal แยกบริเวณตรวจ/Patient_0001/GBH/1.2.826.0.1.3680043.2.461.12739068.1596961029.jpg")
    
    # === 2. Run U-Net (Old Model) ===
    print("Loading U-Net (Old Model)...")
    device_unet = get_device()
    unet_model = UNet(in_ch=1, out_ch=1).to(device_unet)
    unet_ckpt = BASE_DIR / "models/segmentation/checkpoints/liver_unet_best.pt"
    unet_model.load_state_dict(torch.load(str(unet_ckpt), map_location=device_unet, weights_only=True))
    unet_model.eval()
    
    print("Predicting with U-Net...")
    gray_img, unet_mask = predict_mask(unet_model, device_unet, Path(img_path_str))
    
    # === 3. Run MedSAM2 (New Model) ===
    print("Loading MedSAM2 (New Model)...")
    if torch.backends.mps.is_available():
        device_sam = "mps"
    elif torch.cuda.is_available():
        device_sam = "cuda"
    else:
        device_sam = "cpu"
        
    sam2_ckpt = BASE_DIR / "models/medsam2/checkpoints/MedSAM2_latest.pt"
    sam2_cfg = "configs/sam2.1_hiera_t512.yaml"
    
    sam2_model = build_sam2(sam2_cfg, str(sam2_ckpt), device=device_sam)
    sam_predictor = SAM2ImagePredictor(sam2_model)
    
    image = cv2.imread(img_path_str)
    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    
    sam_predictor.set_image(image_rgb)
    H, W = image.shape[:2]
    # Use bounding box prompt
    box = np.array([[W * 0.2, H * 0.2, W * 0.8, H * 0.8]])
    
    print("Predicting with MedSAM2...")
    sam_masks, sam_scores, _ = sam_predictor.predict(
        point_coords=None,
        point_labels=None,
        box=box,
        multimask_output=False,
    )
    sam_mask = sam_masks[0]
    sam_score = sam_scores[0]
    
    # === 4. Visualize and Compare ===
    print("Generating comparison visualization...")
    fig, axes = plt.subplots(1, 2, figsize=(16, 8))
    
    # Color overlays
    color_unet = np.array([0/255, 200/255, 0/255, 0.5]) # Green
    color_sam = np.array([30/255, 144/255, 255/255, 0.5]) # Blue
    
    # Plot U-Net
    axes[0].imshow(image_rgb)
    mask_unet_vis = unet_mask.reshape(H, W, 1) * color_unet.reshape(1, 1, -1)
    axes[0].imshow(mask_unet_vis)
    axes[0].set_title("U-Net (Current SmartLiva Model)\nFully Automatic", fontsize=14)
    axes[0].axis('off')
    
    # Plot MedSAM2
    axes[1].imshow(image_rgb)
    mask_sam_vis = sam_mask.reshape(H, W, 1) * color_sam.reshape(1, 1, -1)
    axes[1].imshow(mask_sam_vis)
    # Draw prompt box
    x0, y0, x1, y1 = box[0]
    axes[1].add_patch(plt.Rectangle((x0, y0), x1-x0, y1-y0, edgecolor='yellow', facecolor=(0,0,0,0), lw=2, linestyle='--'))
    axes[1].set_title(f"MedSAM2 (New Model)\nBox Prompted (Score: {sam_score:.2f})", fontsize=14)
    axes[1].axis('off')
    
    plt.tight_layout()
    out_path = str(BASE_DIR / "model_comparison.png")
    plt.savefig(out_path, bbox_inches='tight', dpi=150)
    print(f"✅ Saved comparison to {out_path}")

if __name__ == "__main__":
    main()
