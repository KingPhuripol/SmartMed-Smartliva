"""Unified Multi-Organ Ultrasound Segmentation Pipeline."""

import logging
from typing import Any, Optional, Tuple
import cv2
import numpy as np
import torch
from PIL import Image

from .morphology import clean_liver_mask
from .prompts import extract_ultrasound_cone
from .multiorgan_sdk import predict_sdk_mask

logger = logging.getLogger("SmartLiva.SegPipeline")


class SegmentationUnavailable(RuntimeError):
    """The segmentation checkpoint did not load, so no mask can be produced."""


def predict_multiorgan_segmentation(
    original_img: np.ndarray,
    gray_img: np.ndarray,
    pil_img: Optional[Image.Image],
    medsam_predictor: Any,
    seg_model_ready: bool,
    device: torch.device,
    yolo_liver_model: Optional[Any] = None,
    multiorgan_model: Optional[Any] = None,
) -> Tuple[np.ndarray, Optional[np.ndarray]]:
    """Infer binary liver and gallbladder masks using Dual-Engine MedSAM2 + Multi-Organ Segmenter.

    Returns:
        (liver_mask, gallbladder_mask)
    """
    if not seg_model_ready or medsam_predictor is None or device is None:
        if multiorgan_model is not None and pil_img is not None:
            logger.info("MedSAM2 not ready, falling back to Multi-Organ UNet model.")
            sdk_mask = predict_sdk_mask(pil_img, multiorgan_model, device, use_fan=True)
            refined_liver = clean_liver_mask((sdk_mask == 1).astype(np.uint8), kernel_size=11)
            refined_gb = clean_liver_mask((sdk_mask == 2).astype(np.uint8), kernel_size=7) if (sdk_mask == 2).sum() > 60 else None
            if refined_gb is not None:
                refined_liver[refined_gb == 1] = 0
            return refined_liver, refined_gb
        raise SegmentationUnavailable("Segmentation model is not loaded or ready.")

    H, W = original_img.shape[:2]
    outline_mask = extract_ultrasound_cone(gray_img)

    # 1. Multi-Organ Seed & Gallbladder Detection via SDK Model
    sdk_liver: Optional[np.ndarray] = None
    sdk_gb: Optional[np.ndarray] = None
    neg_points = []

    if multiorgan_model is not None and pil_img is not None:
        try:
            sdk_mask = predict_sdk_mask(pil_img, multiorgan_model, device, use_fan=True)
            if (sdk_mask == 1).sum() > 100:
                sdk_liver = (sdk_mask == 1).astype(np.uint8)
            if (sdk_mask == 2).sum() > 60:
                sdk_gb = (sdk_mask == 2).astype(np.uint8)
                y_gb, x_gb = np.where(sdk_gb > 0)
                neg_points.append([(x_gb.min() + x_gb.max()) / 2.0, (y_gb.min() + y_gb.max()) / 2.0])
                logger.info(f"Multi-Organ detected Gallbladder ({sdk_gb.sum()} px). Adding negative prompt point.")
        except Exception as e:
            logger.warning(f"Multi-Organ SDK inference failed: {e}")

    # 2. Smart Prompt Box derivation
    prompt_box = None
    if yolo_liver_model is not None:
        liver_results = yolo_liver_model(source=original_img, imgsz=640, verbose=False)
        boxes = liver_results[0].boxes
        if len(boxes) > 0:
            best_box = boxes[0].xyxy[0].cpu().numpy()
            prompt_box = np.array([best_box])
            logger.info(f"Using YOLO Liver Bounding Box Prompt: {prompt_box}")

    if prompt_box is None and sdk_liver is not None:
        y_l, x_l = np.where(sdk_liver > 0)
        prompt_box = np.array([[x_l.min(), y_l.min(), x_l.max(), y_l.max()]])
        logger.info(f"Using Multi-Organ Seed Prompt Box: {prompt_box}")

    if prompt_box is None:
        contours, _ = cv2.findContours(outline_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            prompt_box = np.array([[W * 0.15, H * 0.15, W * 0.85, H * 0.85]])
        else:
            largest_contour = max(contours, key=cv2.contourArea)
            x, y, w, h = cv2.boundingRect(largest_contour)
            prompt_box = np.array([[x, y, x + w, y + h]])
        logger.info(f"Using Cone Bounding Box Prompt: {prompt_box}")

    # 3. Multi-Prompt MedSAM2 Execution (Box + Center Positive Point + Gallbladder Negative Points)
    x1, y1, x2, y2 = prompt_box[0]
    pos_points = [[(x1 + x2) / 2.0, (y1 + y2) / 2.0]]
    all_points = np.array(pos_points + neg_points)
    all_labels = np.array([1] * len(pos_points) + [0] * len(neg_points))

    image_rgb = cv2.cvtColor(original_img, cv2.COLOR_BGR2RGB)

    with torch.no_grad():
        medsam_predictor.set_image(image_rgb)
        masks, scores, logits = medsam_predictor.predict(
            point_coords=all_points,
            point_labels=all_labels,
            box=prompt_box,
            multimask_output=True,
        )

    best_mask_idx = int(np.argmax(scores))
    raw_mask: np.ndarray = masks[best_mask_idx].astype(np.uint8)

    # 4. Mutual Organ Exclusion: Subtract Gallbladder from Liver
    if sdk_gb is not None and sdk_gb.sum() > 60:
        raw_mask[sdk_gb == 1] = 0

    # 5. Hard Geometric Cone Constraint & Shadow Dropping
    cone_constrained = raw_mask * (outline_mask > 0)
    cone_constrained[gray_img < 8] = 0

    # 6. Anatomical Morphology Refinement
    refined_liver: np.ndarray = clean_liver_mask(cone_constrained, kernel_size=11)

    # Final Gallbladder Cleanup if present
    refined_gb: Optional[np.ndarray] = None
    if sdk_gb is not None and sdk_gb.sum() > 60:
        gb_clean = clean_liver_mask(sdk_gb * (outline_mask > 0), kernel_size=7)
        refined_liver[gb_clean == 1] = 0
        refined_gb = gb_clean

    return refined_liver, refined_gb
