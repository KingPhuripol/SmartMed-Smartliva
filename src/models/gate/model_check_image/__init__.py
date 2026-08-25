"""Model Check Image V.1 Mild -- an input gate for B-mode ultrasound.

Answers two questions about an image file, and deliberately refuses to answer more:

    1. Is this a B-mode ultrasound frame at all?
    2. Did it come off a scanner, or is it a photograph of a scanner's screen?

It is not a trained model. It measures the physics of speckle formation against an
envelope calibrated from real scans, so there is no weights file, no inference engine,
and no opportunity for the gate to learn a shortcut from whatever data it was shown.

Basic use::

    from model_check_image import inspect

    verdict = inspect("scan.jpg")
    if verdict.usable_for_dataset:
        ...                       # ACCEPTED: confidently a scanner-exported ultrasound
    print(verdict.decision)       # ACCEPTED / BORDERLINE / REJECTED / UNMEASURABLE
    print(verdict.reason)         # human-readable, in Thai
    print(verdict.checks)         # every measurement with the band it was judged against

What it will NOT tell you
-------------------------
* whether the organ is a liver -- kidney passes at 96.5%, thyroid at 94.5%
* whether the liver is healthy -- malignant cases pass at 95.9%, normal at 100%

Both would need a stage that does not exist yet. Treating "ACCEPTED" as either claim is
the single most likely way to misuse this package.

Calibration
-----------
The bundled envelope was fitted on liver ultrasound from five sources. For a new fleet of
scanners, refit it -- the accepted range depends on the log compression and speckle
reduction of the machines in your own data. Without a calibration file the gate raises
rather than defaulting to pass.
"""
from .gate import (  # noqa: F401
    CONTRAST_FLOOR,
    ENVELOPE_PATH,
    ISOTROPY_FLOOR,
    SURROUND_UNVERIFIABLE,
    Decision,
    Envelope,
    Verdict,
    inspect,
)
from .physics import NotMeasurable, SpeckleFeatures, measure  # noqa: F401
from .provenance import assess as assess_provenance  # noqa: F401

__version__ = "1.0.0"

__all__ = [
    "inspect",
    "Decision",
    "Verdict",
    "Envelope",
    "measure",
    "SpeckleFeatures",
    "NotMeasurable",
    "assess_provenance",
    "CONTRAST_FLOOR",
    "ISOTROPY_FLOOR",
    "SURROUND_UNVERIFIABLE",
    "ENVELOPE_PATH",
    "__version__",
]
