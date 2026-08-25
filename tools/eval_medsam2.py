"""Comprehensive evaluation of MedSAM2 Liver Segmentation on Multiview Clinical Ultrasound.

Evaluates:
- Dice Similarity Coefficient (DSC)
- Intersection over Union (IoU)
- Boundary Spillover Rate (% of prediction outside true liver)
- View-by-view breakdown (GBH, RH, SPH, FPH, LHP, LHV, LHA)
"""

import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
import torch
from tqdm import tqdm

BASE_DIR = Path(__file__).resolve().parent.parent
medsam_pkg = BASE_DIR / "third_party" / "MedSAM2"
if str(medsam_pkg) not in sys.path:
    sys.path.insert(0, str(medsam_pkg))

from sam2.build_sam import build_sam2
from sam2.sam2_image_predictor import SAM2ImagePredictor

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("EvalMedSAM2")


def get_device() -> torch.device:
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def clean_liver_mask(mask: np.ndarray, kernel_size: int = 11) -> np.ndarray:
    """Anatomical morphology refinement: close, keep largest connected component, and fill internal holes."""
    binary: np.ndarray = (mask > 0).astype(np.uint8)
    if binary.sum() == 0:
        return binary

    element = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, element)

    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(closed, connectivity=8)
    if n_labels <= 1:
        return closed

    largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    primary = (labels == largest).astype(np.uint8)

    h, w = primary.shape[:2]
    flood = primary.copy()
    scratch = np.zeros((h + 2, w + 2), dtype=np.uint8)
    cv2.floodFill(flood, scratch, (0, 0), 1)
    holes = (flood == 0).astype(np.uint8)
    return ((primary > 0) | (holes > 0)).astype(np.uint8)


def extract_ultrasound_cone(gray_image: np.ndarray) -> np.ndarray:
    """Extract valid ultrasound fan/cone area to prevent mask spill-over."""
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


def load_sample_gt(img_path: Path, json_path: Path) -> Tuple[np.ndarray, np.ndarray]:
    """Loads image and parses liver polygon from JSON."""
    img = cv2.imread(str(img_path))
    if img is None:
        raise ValueError(f"Could not read image {img_path}")

    h, w = img.shape[:2]
    gt_mask = np.zeros((h, w), dtype=np.uint8)

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        # Format: [[x, y], [x, y], ...]
        polygon = np.round(np.array(data)).astype(np.int32)
        cv2.fillPoly(gt_mask, [polygon], 1)
    elif isinstance(data, dict):
        # Labelme / AnyLabeling JSON format
        for shape in data.get("shapes", []):
            label = shape.get("label", "").lower()
            if "肝" in shape.get("label", "") or "liver" in label:
                pts = np.round(np.array(shape.get("points", []))).astype(np.int32)
                if len(pts) >= 3:
                    cv2.fillPoly(gt_mask, [pts], 1)

    return img, gt_mask


def compute_metrics(pred: np.ndarray, gt: np.ndarray) -> Dict[str, float]:
    """Computes Dice, IoU, and Spillover (over-segmentation rate)."""
    p_bin = (pred > 0).astype(np.uint8)
    g_bin = (gt > 0).astype(np.uint8)

    inter = (p_bin & g_bin).sum()
    union = (p_bin | g_bin).sum()
    p_sum = p_bin.sum()
    g_sum = g_bin.sum()

    dice = float((2.0 * inter) / (p_sum + g_sum + 1e-8))
    iou = float(inter / (union + 1e-8))

    # Spillover: pixels predicted as liver that are actually NOT liver
    spillover = float(((p_bin == 1) & (g_bin == 0)).sum() / (p_sum + 1e-8))

    # Under-segmentation: pixels of true liver missed
    under_seg = float(((p_bin == 0) & (g_bin == 1)).sum() / (g_sum + 1e-8))

    return {
        "dice": dice,
        "iou": iou,
        "spillover": spillover,
        "under_segmentation": under_seg,
    }


def collect_multiview_samples(max_per_view: int = 15) -> List[Tuple[str, Path, Path]]:
    """Collects samples across anatomical scan views from `data/Normal แยกบริเวณตรวจ`."""
    normal_dir = BASE_DIR / "data" / "Normal แยกบริเวณตรวจ"
    samples = []

    if not normal_dir.exists():
        logger.warning(f"Directory {normal_dir} does not exist.")
        return samples

    for patient_dir in sorted(normal_dir.glob("Patient_*")):
        for view_dir in sorted(patient_dir.iterdir()):
            if not view_dir.is_dir():
                continue
            view_name = view_dir.name
            count_view = sum(1 for v, _, _ in samples if v == view_name)
            if count_view >= max_per_view:
                continue

            for img_path in sorted(view_dir.glob("*.jpg")):
                json_path = img_path.with_suffix(".json")
                if json_path.exists():
                    samples.append((view_name, img_path, json_path))
                    break

    return samples


def main(num_samples: int = 50):
    device = get_device()
    logger.info(f"Using device: {device}")

    ckpt = BASE_DIR / "weights" / "medsam2" / "MedSAM2_latest.pt"
    cfg = "configs/sam2.1_hiera_t512.yaml"

    logger.info("Initializing MedSAM2 Foundation Model...")
    sam_model = build_sam2(cfg, str(ckpt), device=device)
    predictor = SAM2ImagePredictor(sam_model)

    samples = collect_multiview_samples(max_per_view=10)[:num_samples]
    logger.info(f"Evaluating on {len(samples)} curated ultrasound scan views...")

    results = []
    view_stats: Dict[str, List[Dict[str, float]]] = {}

    for view_name, img_path, json_path in tqdm(samples, desc="Evaluating"):
        try:
            img, gt_mask = load_sample_gt(img_path, json_path)
            if gt_mask.sum() == 0:
                continue

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            h, w = img.shape[:2]

            # Bounding box prompt
            y_indices, x_indices = np.where(gt_mask > 0)
            x1, y1, x2, y2 = x_indices.min(), y_indices.min(), x_indices.max(), y_indices.max()
            prompt_box = np.array([[x1, y1, x2, y2]])

            # Center anchor point prompt
            center_points = np.array([[(x1 + x2) / 2.0, (y1 + y2) / 2.0]])
            point_labels = np.array([1])

            predictor.set_image(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
            masks, scores, _ = predictor.predict(
                box=prompt_box,
                point_coords=center_points,
                point_labels=point_labels,
                multimask_output=True,
            )

            best_idx = int(np.argmax(scores))
            raw_mask = masks[best_idx].astype(np.uint8)

            # High-Precision Constraint Pipeline
            cone_mask = extract_ultrasound_cone(gray)
            cone_constrained = raw_mask * (cone_mask > 0)
            cone_constrained[gray < 8] = 0
            refined_mask = clean_liver_mask(cone_constrained, kernel_size=11)

            metrics_raw = compute_metrics(raw_mask, gt_mask)
            metrics_refined = compute_metrics(refined_mask, gt_mask)

            sample_record = {
                "view": view_name,
                "file": img_path.name,
                "raw": metrics_raw,
                "refined": metrics_refined,
            }
            results.append(sample_record)

            if view_name not in view_stats:
                view_stats[view_name] = []
            view_stats[view_name].append(metrics_refined)

        except Exception as e:
            logger.error(f"Error evaluating {img_path}: {e}")

    if not results:
        logger.error("No valid samples evaluated.")
        return

    # Aggregate overall metrics
    mean_dice = np.mean([r["refined"]["dice"] for r in results]) * 100
    mean_iou = np.mean([r["refined"]["iou"] for r in results]) * 100
    mean_spill = np.mean([r["refined"]["spillover"] for r in results]) * 100

    print("\n" + "=" * 65)
    print(" 🏥 MEDSAM2 HIGH-PRECISION LIVER SEGMENTATION BENCHMARK REPORT")
    print("=" * 65)
    print(f" Total Evaluated Cases: {len(results)}")
    print(f" Overall Mean Dice Score: {mean_dice:.2f}%")
    print(f" Overall Mean IoU:        {mean_iou:.2f}%")
    print(f" Mean Boundary Spillover: {mean_spill:.2f}% (Over-segmentation rate)")
    print("-" * 65)
    print(" View Breakdown:")
    for view, m_list in view_stats.items():
        v_dice = np.mean([m["dice"] for m in m_list]) * 100
        v_iou = np.mean([m["iou"] for m in m_list]) * 100
        v_spill = np.mean([m["spillover"] for m in m_list]) * 100
        print(f"  - [{view:<5}]: Dice = {v_dice:6.2f}% | IoU = {v_iou:6.2f}% | Spillover = {v_spill:5.2f}% (n={len(m_list)})")
    print("=" * 65)

    # Save results to JSON
    out_file = BASE_DIR / "reports" / "medsam2_multiview_eval_results.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "overall_dice": mean_dice,
                "overall_iou": mean_iou,
                "overall_spillover": mean_spill,
                "total_samples": len(results),
                "view_breakdown": {
                    v: {
                        "dice": float(np.mean([m["dice"] for m in m_list]) * 100),
                        "iou": float(np.mean([m["iou"] for m in m_list]) * 100),
                        "spillover": float(np.mean([m["spillover"] for m in m_list]) * 100),
                        "count": len(m_list),
                    }
                    for v, m_list in view_stats.items()
                },
            },
            f,
            indent=2,
        )
    logger.info(f"Evaluation report saved to {out_file}")


if __name__ == "__main__":
    main(num_samples=30)
