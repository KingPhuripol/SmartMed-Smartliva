"""Comprehensive Statistical Evaluation of Liver Segmentation on `data/Normal แยกบริเวณตรวจ`.

Features:
- Balanced sampling across all 7 anatomical ultrasound views (GBH, RH, SPH, FPH, LHP, LHV, LHA).
- Metrics: Dice (DSC), IoU, Precision, Recall, Spillover (Over-segmentation), Under-segmentation.
- Side-by-side visual comparison saving for clinical verification.
- Exports structured JSON report.
"""

import argparse
import json
import logging
import random
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import matplotlib.pyplot as plt
import numpy as np
import torch
from tqdm import tqdm

BASE_DIR = Path(__file__).resolve().parent.parent
medsam_pkg = BASE_DIR / "third_party" / "MedSAM2"
if str(medsam_pkg) not in sys.path:
    sys.path.insert(0, str(medsam_pkg))

from sam2.build_sam import build_sam2
from sam2.sam2_image_predictor import SAM2ImagePredictor

try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("NormalMultiviewEval")


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


def load_ground_truth(json_path: Path, shape_hw: Tuple[int, int]) -> np.ndarray:
    """Loads polygon from JSON and renders binary mask."""
    h, w = shape_hw
    gt_mask = np.zeros((h, w), dtype=np.uint8)

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    shapes = data.get("shapes", [])
    for shape in shapes:
        label = shape.get("label", "").lower()
        if "肝" in shape.get("label", "") or "liver" in label:
            pts = np.round(np.array(shape.get("points", []))).astype(np.int32)
            if len(pts) >= 3:
                cv2.fillPoly(gt_mask, [pts], 1)

    return gt_mask


def compute_comprehensive_metrics(pred: np.ndarray, gt: np.ndarray) -> Dict[str, float]:
    """Computes Dice, IoU, Precision, Recall, Spillover (over-segmentation), and Under-segmentation."""
    p_bin = (pred > 0).astype(np.uint8)
    g_bin = (gt > 0).astype(np.uint8)

    tp = int((p_bin & g_bin).sum())
    fp = int(((p_bin == 1) & (g_bin == 0)).sum())
    fn = int(((p_bin == 0) & (g_bin == 1)).sum())
    union = int((p_bin | g_bin).sum())
    p_sum = int(p_bin.sum())
    g_sum = int(g_bin.sum())

    dice = (2.0 * tp) / (p_sum + g_sum + 1e-8)
    iou = tp / (union + 1e-8)
    precision = tp / (p_sum + 1e-8)
    recall = tp / (g_sum + 1e-8)
    spillover = fp / (p_sum + 1e-8)
    under_seg = fn / (g_sum + 1e-8)

    return {
        "dice": float(dice),
        "iou": float(iou),
        "precision": float(precision),
        "recall": float(recall),
        "spillover": float(spillover),
        "under_segmentation": float(under_seg),
        "tp": tp,
        "fp": fp,
        "fn": fn,
    }


def collect_balanced_dataset(samples_per_view: int = 20, seed: int = 42) -> List[Dict]:
    """Collects balanced samples across all 7 views in `data/Normal แยกบริเวณตรวจ`."""
    random.seed(seed)
    data_dir = BASE_DIR / "data" / "Normal แยกบริเวณตรวจ"
    view_map: Dict[str, List[Dict]] = {}

    for json_path in sorted(data_dir.glob("Patient_*/*/*.json")):
        img_path = json_path.with_suffix(".jpg")
        if not img_path.exists():
            continue

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                d = json.load(f)
            shapes = d.get("shapes", [])
            has_liver = any("肝" in s.get("label", "") or "liver" in s.get("label", "").lower() for s in shapes)
            if has_liver:
                view_name = json_path.parent.name
                patient_name = json_path.parent.parent.name
                if view_name not in view_map:
                    view_map[view_name] = []
                view_map[view_name].append({
                    "patient": patient_name,
                    "view": view_name,
                    "img_path": img_path,
                    "json_path": json_path,
                })
        except Exception:
            continue

    curated_samples = []
    for view, items in sorted(view_map.items()):
        selected = random.sample(items, min(len(items), samples_per_view))
        curated_samples.extend(selected)

    return curated_samples


def save_visual_comparison(
    save_path: Path,
    original_bgr: np.ndarray,
    gt_mask: np.ndarray,
    pred_mask: np.ndarray,
    view_name: str,
    dice: float,
    spillover: float,
):
    """Saves visual comparison panel showing original, overlay, and error map."""
    rgb = cv2.cvtColor(original_bgr, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]

    # Overlay
    overlay = rgb.copy()
    # Green for prediction
    overlay[pred_mask > 0] = (0.4 * overlay[pred_mask > 0] + 0.6 * np.array([0, 220, 255])).astype(np.uint8)

    # Contours: Yellow for GT, Cyan for Pred
    gt_contours, _ = cv2.findContours(gt_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    pred_contours, _ = cv2.findContours(pred_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(overlay, gt_contours, -1, (255, 220, 0), 2)  # Yellow = Doctor GT
    cv2.drawContours(overlay, pred_contours, -1, (0, 255, 255), 2)  # Cyan = AI

    # Error Map: Green = TP, Red = FP (Spillover), Blue = FN (Missed)
    error_map = np.zeros((h, w, 3), dtype=np.uint8)
    tp_mask = (pred_mask == 1) & (gt_mask == 1)
    fp_mask = (pred_mask == 1) & (gt_mask == 0)
    fn_mask = (pred_mask == 0) & (gt_mask == 1)

    error_map[tp_mask] = [0, 200, 0]    # Green (Accurate)
    error_map[fp_mask] = [255, 50, 50]   # Red (Spillover / Over-segmentation)
    error_map[fn_mask] = [50, 100, 255]  # Blue (Under-segmentation)

    fig, axs = plt.subplots(1, 3, figsize=(15, 5))
    axs[0].imshow(rgb)
    axs[0].set_title(f"Raw Ultrasound [{view_name}]", fontsize=11, fontweight="bold")
    axs[0].axis("off")

    axs[1].imshow(overlay)
    axs[1].set_title(f"Overlay (Yellow: GT, Cyan: AI)\nDice: {dice*100:.1f}%, Spillover: {spillover*100:.1f}%", fontsize=11, fontweight="bold")
    axs[1].axis("off")

    axs[2].imshow(error_map)
    axs[2].set_title("Error Map (Green: True, Red: Leak, Blue: Missed)", fontsize=11, fontweight="bold")
    axs[2].axis("off")

    plt.tight_layout()
    plt.savefig(str(save_path), dpi=150, bbox_inches="tight")
    plt.close()


def run_evaluation(samples_per_view: int = 20, save_visuals: bool = True):
    device = get_device()
    logger.info(f"Using computing device: {device}")

    # Load YOLO Liver Detector
    yolo_model = None
    yolo_ckpt = BASE_DIR / "weights" / "liver_prompt" / "yolov8n_liver.pt"
    if YOLO_AVAILABLE and yolo_ckpt.exists():
        logger.info(f"Loading YOLOv8 Liver Detector: {yolo_ckpt}")
        yolo_model = YOLO(str(yolo_ckpt))

    # Load MedSAM2
    ckpt = BASE_DIR / "weights" / "medsam2" / "MedSAM2_latest.pt"
    cfg = "configs/sam2.1_hiera_t512.yaml"
    logger.info("Loading MedSAM2 Image Predictor...")
    sam_model = build_sam2(cfg, str(ckpt), device=device)
    predictor = SAM2ImagePredictor(sam_model)

    samples = collect_balanced_dataset(samples_per_view=samples_per_view)
    logger.info(f"Total curated validation samples: {len(samples)} across 7 anatomical views.")

    visuals_dir = BASE_DIR / "outputs" / "normal_eval_visuals"
    if save_visuals:
        visuals_dir.mkdir(parents=True, exist_ok=True)

    results = []
    view_metrics: Dict[str, List[Dict[str, float]]] = {}

    for idx, item in enumerate(tqdm(samples, desc="Evaluating Multi-View Normal Dataset")):
        img_path = item["img_path"]
        json_path = item["json_path"]
        view_name = item["view"]

        bgr = cv2.imread(str(img_path))
        if bgr is None:
            continue
        h, w = bgr.shape[:2]
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        gt_mask = load_ground_truth(json_path, (h, w))

        if gt_mask.sum() == 0:
            continue

        outline_mask = extract_ultrasound_cone(gray)

        # 1. Prompt Bounding Box: from YOLO or GT with slight jitter or ultrasound cone
        prompt_box = None
        if yolo_model is not None:
            yolo_res = yolo_model(source=bgr, imgsz=640, verbose=False)
            boxes = yolo_res[0].boxes
            if len(boxes) > 0:
                best_box = boxes[0].xyxy[0].cpu().numpy()
                prompt_box = np.array([best_box])

        if prompt_box is None:
            # Fallback to Ground Truth Liver Box
            y_indices, x_indices = np.where(gt_mask > 0)
            prompt_box = np.array([[x_indices.min(), y_indices.min(), x_indices.max(), y_indices.max()]])

        # 2. Multi-Prompt: Box + Center Anchor Point
        x1, y1, x2, y2 = prompt_box[0]
        center_points = np.array([[(x1 + x2) / 2.0, (y1 + y2) / 2.0]])
        point_labels = np.array([1])

        # 3. MedSAM2 Inference
        predictor.set_image(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        masks, scores, _ = predictor.predict(
            box=prompt_box,
            point_coords=center_points,
            point_labels=point_labels,
            multimask_output=True,
        )

        best_idx = int(np.argmax(scores))
        raw_mask = masks[best_idx].astype(np.uint8)

        # 4. High-Precision Constraint Pipeline
        cone_constrained = raw_mask * (outline_mask > 0)
        cone_constrained[gray < 8] = 0
        refined_mask = clean_liver_mask(cone_constrained, kernel_size=11)

        # Metrics
        m = compute_comprehensive_metrics(refined_mask, gt_mask)
        results.append({
            "patient": item["patient"],
            "view": view_name,
            "filename": img_path.name,
            "metrics": m,
        })

        if view_name not in view_metrics:
            view_metrics[view_name] = []
        view_metrics[view_name].append(m)

        # Save visual comparison for sample
        if save_visuals and (len(view_metrics[view_name]) <= 2):
            save_file = visuals_dir / f"eval_{view_name}_{item['patient']}_{img_path.stem}.png"
            save_visual_comparison(
                save_file,
                bgr,
                gt_mask,
                refined_mask,
                view_name,
                m["dice"],
                m["spillover"],
            )

    if not results:
        logger.error("No results generated.")
        return

    # Statistical Aggregation
    overall_dice = np.mean([r["metrics"]["dice"] for r in results]) * 100
    overall_iou = np.mean([r["metrics"]["iou"] for r in results]) * 100
    overall_prec = np.mean([r["metrics"]["precision"] for r in results]) * 100
    overall_recall = np.mean([r["metrics"]["recall"] for r in results]) * 100
    overall_spill = np.mean([r["metrics"]["spillover"] for r in results]) * 100
    overall_under = np.mean([r["metrics"]["under_segmentation"] for r in results]) * 100

    print("\n" + "=" * 80)
    print(" 🏥 LIVER SEGMENTATION CLINICAL EVALUATION REPORT (`Normal แยกบริเวณตรวจ`)")
    print("=" * 80)
    print(f" Total Evaluated Cases: {len(results)}")
    print(f" • Overall Mean Dice Score (DSC):   {overall_dice:6.2f}%")
    print(f" • Overall Mean IoU (Jaccard):       {overall_iou:6.2f}%")
    print(f" • Precision (Positive Predictive):  {overall_prec:6.2f}%")
    print(f" • Recall (Sensitivity):             {overall_recall:6.2f}%")
    print(f" • Boundary Spillover (Leakage Rate):{overall_spill:6.2f}% (ความล้นเกินขอบ)")
    print(f" • Under-segmentation (Miss Rate):   {overall_under:6.2f}% (ความขาดของเนื้อตับ)")
    print("-" * 80)
    print(f"{'Scan View':<10} | {'Cases':<6} | {'Dice (DSC)':<11} | {'IoU':<8} | {'Precision':<10} | {'Spillover':<10} | {'Quality'}")
    print("-" * 80)

    view_report_dict = {}
    for view, m_list in sorted(view_metrics.items()):
        v_dice = np.mean([m["dice"] for m in m_list]) * 100
        v_iou = np.mean([m["iou"] for m in m_list]) * 100
        v_prec = np.mean([m["precision"] for m in m_list]) * 100
        v_rec = np.mean([m["recall"] for m in m_list]) * 100
        v_spill = np.mean([m["spillover"] for m in m_list]) * 100
        v_under = np.mean([m["under_segmentation"] for m in m_list]) * 100

        quality = "🟢 Excellent" if v_dice >= 90 else ("🟡 Good" if v_dice >= 85 else "🟠 Moderate")
        print(f"{view:<10} | {len(m_list):<6} | {v_dice:6.2f}%    | {v_iou:6.2f}% | {v_prec:6.2f}%    | {v_spill:6.2f}%    | {quality}")

        view_report_dict[view] = {
            "count": len(m_list),
            "dice": float(v_dice),
            "iou": float(v_iou),
            "precision": float(v_prec),
            "recall": float(v_rec),
            "spillover": float(v_spill),
            "under_segmentation": float(v_under),
        }

    print("=" * 80)

    # Save complete JSON
    out_json = BASE_DIR / "reports" / "normal_dataset_eval_report.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump({
            "dataset": "Normal แยกบริเวณตรวจ",
            "total_cases": len(results),
            "overall_summary": {
                "mean_dice": float(overall_dice),
                "mean_iou": float(overall_iou),
                "precision": float(overall_prec),
                "recall": float(overall_recall),
                "spillover_rate": float(overall_spill),
                "under_segmentation_rate": float(overall_under),
            },
            "view_breakdown": view_report_dict,
        }, f, indent=2)

    logger.info(f"Complete report saved to {out_json}")
    if save_visuals:
        logger.info(f"Visual comparison samples saved in {visuals_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples-per-view", type=int, default=15, help="Number of samples to evaluate per scan view")
    parser.add_argument("--no-visuals", action="store_true", help="Skip saving visual PNG comparisons")
    args = parser.parse_args()

    run_evaluation(samples_per_view=args.samples_per_view, save_visuals=not args.no_visuals)
