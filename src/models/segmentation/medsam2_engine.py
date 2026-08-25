"""MedSAM2 Predictor Engine Wrapper."""

import logging
import sys
from pathlib import Path
from typing import Optional, Tuple
import torch

from src.config import BASE_DIR, MEDSAM_CFG, MEDSAM_CKPT, MEDSAM2_DIR

logger = logging.getLogger("SmartLiva.MedSAM2Engine")

# Ensure third_party/MedSAM2 is on sys.path
if str(MEDSAM2_DIR) not in sys.path:
    sys.path.insert(0, str(MEDSAM2_DIR))

try:
    from sam2.build_sam import build_sam2
    from sam2.sam2_image_predictor import SAM2ImagePredictor
    MEDSAM2_IMPORT_OK = True
except Exception as e:
    logger.warning(f"Could not import sam2 library from {MEDSAM2_DIR}: {e}")
    build_sam2 = None
    SAM2ImagePredictor = None
    MEDSAM2_IMPORT_OK = False


def load_medsam2_predictor(
    weights_path: Path = MEDSAM_CKPT,
    config_name: str = MEDSAM_CFG,
    device: Optional[torch.device] = None,
) -> Tuple[Optional[SAM2ImagePredictor], bool, Optional[str]]:
    """Load MedSAM2 model and return a SAM2ImagePredictor instance."""
    if not MEDSAM2_IMPORT_OK:
        return None, False, f"sam2 library not found in {MEDSAM2_DIR}"

    if not weights_path.exists():
        err_msg = f"MedSAM2 weights not found at {weights_path}"
        logger.error(err_msg)
        return None, False, err_msg

    try:
        sam2_model = build_sam2(config_name, str(weights_path), device=device)
        predictor = SAM2ImagePredictor(sam2_model)
        logger.info(f"Successfully initialized MedSAM2 predictor from {weights_path}")
        return predictor, True, None
    except Exception as err:
        err_msg = f"Failed to initialize MedSAM2: {err}"
        logger.error(err_msg)
        return None, False, err_msg
