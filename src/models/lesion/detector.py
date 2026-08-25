"""YOLOv8 Lesion & Liver Bounding Box Model Loader."""

import logging
from pathlib import Path
from typing import Optional
from ultralytics import YOLO

from src.config import YOLO_LESION_PATH, YOLO_LIVER_PATH

logger = logging.getLogger("SmartLiva.LesionDetector")


def load_lesion_model(weights_path: Path = YOLO_LESION_PATH) -> Optional[YOLO]:
    """Load the fine-tuned YOLOv8 Focal Lesion Detection model."""
    if not weights_path.exists():
        logger.warning(f"YOLO Lesion model checkpoint missing at: {weights_path}")
        return None
    try:
        model = YOLO(str(weights_path))
        logger.info(f"Successfully loaded YOLO Lesion model from {weights_path}")
        return model
    except Exception as err:
        logger.error(f"Failed to load YOLO Lesion model: {err}")
        return None


def load_liver_box_model(weights_path: Path = YOLO_LIVER_PATH) -> Optional[YOLO]:
    """Load the YOLOv8 Liver Bounding Box detector for smart prompt generation."""
    if not weights_path.exists():
        logger.info(f"YOLO Liver box checkpoint missing at {weights_path}")
        return None
    try:
        model = YOLO(str(weights_path))
        logger.info(f"Successfully loaded YOLO Liver box model from {weights_path}")
        return model
    except Exception as err:
        logger.warning(f"Failed to load YOLO Liver box model: {err}")
        return None
