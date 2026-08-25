"""Fibrosis Staging Sub-Package."""

import sys
from pathlib import Path

FIBROSIS_DIR = Path(__file__).resolve().parent

# Ensure local imports inside models/fibrosis resolve correctly
if str(FIBROSIS_DIR) not in sys.path:
    sys.path.insert(0, str(FIBROSIS_DIR))

try:
    from infer import load_ensemble, predict_fibrosis, ENSEMBLE_PATH
    from preprocess import clean_mask
    FIBROSIS_AVAILABLE = True
except Exception as _err:
    load_ensemble = None
    predict_fibrosis = None
    clean_mask = None
    ENSEMBLE_PATH = FIBROSIS_DIR / "checkpoints" / "fibrosis_ensemble.pt"
    FIBROSIS_AVAILABLE = False

__all__ = ["load_ensemble", "predict_fibrosis", "clean_mask", "ENSEMBLE_PATH", "FIBROSIS_AVAILABLE"]
