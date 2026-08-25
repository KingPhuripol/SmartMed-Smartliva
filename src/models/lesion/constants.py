"""Lesion class definitions and clinical labels."""

from typing import Dict

LESION_CLASSES: Dict[int, str] = {
    0: "FFC",         # Focal Fatty Change
    1: "FFS",         # Focal Fatty Sparing
    2: "HCC",         # Hepatocellular Carcinoma
    3: "Cyst",        # Simple Cyst
    4: "Hemangioma",   # Cavernous Hemangioma
    5: "Dysplastic",  # Dysplastic Nodule
    6: "CCA"          # Cholangiocarcinoma
}
