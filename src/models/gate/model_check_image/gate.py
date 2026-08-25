"""Stage 1: decide whether a frame is a B-mode ultrasound image at all.

This is deliberately *not* a learned binary classifier. Training one requires negative
examples, and the only negatives available when the previous system was built were
natural photographs -- which differ from ultrasound in brightness long before they
differ in tissue, so the network learned brightness. We do not have a corpus of
other-organ ultrasound on this machine yet, so rather than train against the wrong
negatives again, this stage tests the frame against the *physics* of B-mode imaging
using an envelope calibrated from real liver scans.

What this stage can and cannot do
---------------------------------
CAN reject: photographs, screenshots, documents, blank frames, smooth gradients,
un-tuned noise, inverted scans, pixel-shuffled frames. Measured: 0.0% of each family is
confidently accepted. Note that for some families "0% accepted" means the frame was
UNMEASURABLE rather than identified as fake -- that still keeps it out of the dataset, but
it is not detection.

CANNOT reject: texture built deliberately to match. Gaussian noise blurred to a
correlation length near the speckle scale (sigma about 2.6-3.0) and pasted inside a real
frame's own sector is accepted 50-56% of the time. An earlier version of this docstring
claimed synthetic noise was rejected; that was measured and found false. Passing this
stage is evidence about texture scale, not evidence that a frame came from a scanner.
There is no adversary in the current dataset-building path, but there would be on any
upload path.

Capture provenance is checked alongside the physics: a photograph of a scanner's
screen has genuine speckle and passes the modality test, but must not seed a dataset.
See provenance.py.

CANNOT reject reliably: an ultrasound of a *different organ*. Separating liver from other
organs needs anatomical learning; that is Stage 2.

An earlier version of this docstring claimed other organs "will pass". That was an
assumption, and measuring it proved it wrong. On 1,980 non-liver scans (scripts/
eval_other_organs.py) the confident-accept rate was:

    liver (calibration source)   76.4%
    thyroid                      89.2%
    breast                       29.2%
    fetal head                   20.6%
    carotid                       9.8%

The rejections are driven almost entirely by autocorrelation coming out *above* the
envelope -- these textures are smoother than liver parenchyma, because a carotid frame is
mostly vessel lumen and wall, and a fetal frame is mostly amniotic fluid and bone surface.
Part of that is anatomy and part is likely resampling by whoever curated those releases,
since interpolation raises spatial correlation.

So the stage does partly discriminate by organ, but as a side effect of texture
smoothness, not by recognising anatomy -- which makes it the wrong thing to lean on. Do
not treat "passed Stage 1" as evidence that a frame is a liver, and do not treat a
rejection as evidence that it is not.

Three outcomes, not two
-----------------------
A frame sitting on the envelope boundary is not knowledge, and reporting it as a
confident accept or reject would be inventing certainty. Frames inside the calibrated
core are ACCEPTED, frames beyond the outer bounds are REJECTED, and the band between
is BORDERLINE -- routed to a human rather than resolved by rounding.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from . import provenance
from .physics import NotMeasurable, SpeckleFeatures, measure

ENVELOPE_PATH = Path(__file__).resolve().parent / "calibration" / "envelope.json"

# Share of the frame above the tissue threshold, beyond which the un-imaged surround
# cannot be confirmed to exist.
#
# A B-mode frame is formed by sweeping a sector, and the corners outside that sector
# receive no echo, so they arrive black. If essentially every pixel sits above the tissue
# threshold, one of two things is true: the frame was cropped tight to the sector, or the
# image is not a B-mode frame at all -- an inverted scan turns the black surround white and
# lands here, as does heavily blurred noise.
#
# Measured (60 frames per site): genuine liver runs 0.186-0.997 with medians 0.42 Thai /
# 0.37 Korean / 0.70 Dhaka; inverted scans run 0.995-1.000; blurred noise sits at 1.000.
# At this cut-off, 100% of inverted frames and 100% of blurred noise are caught, and 2.8%
# of genuine liver -- the tightly-cropped tail -- is caught with them.
#
# Those two populations are genuinely inseparable on this axis, so this must NOT reject.
# It withholds confident admission and sends the frame to a human, which is the honest
# verdict when the evidence cannot distinguish a corrupted frame from a cropped one.
SURROUND_UNVERIFIABLE = 0.95

# Features whose accepted range is FITTED from real scans. cv is deliberately not one of
# them any more -- see CONTRAST_FLOOR below.
ENVELOPE_FEATURES = ("autocorr_lag1", "autocorr_lag4")

# Minimum speckle contrast for a frame to be tissue at all.
#
# cv used to be a fitted envelope feature like the other two, and it was the single
# largest cause of genuine liver being rejected at a hospital the envelope had not seen:
# 12.0% of held-out scans failed on "cv too low" alone. The reason is that cv measures the
# *size* of the intensity fluctuation, which vendors change directly through log
# compression and speckle reduction. Measured medians differ 2.5-fold across our three
# sites (Thai 0.264, Korean 0.341, Dhaka 0.134), so a percentile fitted on two sites
# systematically excludes the third.
#
# But cv cannot simply be dropped: it is the only feature that rejects images too smooth
# to be tissue. With cv removed entirely, 100% of linear gradient images were accepted.
#
# The resolution is that cv's lower bound is not a property of our calibration sample, it
# is a property of ultrasound. Real speckle has contrast; a near-flat patch does not.
# Measured across all three sites including every tone augmentation, the lowest genuine
# liver cv was 0.0632, while the highest cv among smooth non-tissue images (gradients,
# near-flat frames, heavily blurred ramps) was 0.0402. This floor sits in that gap.
#
# Effect of the change, leave-one-site-out: held-out liver accepted 61.8% -> 76.7%, with
# every negative family rejected at exactly the same rate as before.
#
# cv's upper bound was dropped as redundant: high-contrast noise is already rejected by
# autocorr_lag1 falling below its own lower bound.
CONTRAST_FLOOR = 0.05

# Minimum asymmetry between lateral and axial speckle correlation.
#
# A B-mode resolution cell is not round: axial resolution is set by the transmitted pulse
# length, lateral resolution by the beam width, and the two are not equal. Every real scan
# measured here shows it, across five scanners:
#
#     |lateral - axial| autocorrelation at lag 1, median (minimum)
#     Thai 0.088 (0.028) | Korean 0.140 (0.048) | Dhaka 0.159 (0.103)
#     BEHSOF 0.098 (0.058) | fibrosis-TE 0.112 (0.070)
#
# Gaussian smoothing is isotropic, so noise tuned to match cv, lag1 and lag4 exactly still
# comes out round: median 0.014-0.017 across smoothing scales, 95th percentile 0.033.
# That closes the one hole the three texture statistics could not, because matching it
# would require a forger to reproduce beam geometry rather than just a correlation length.
#
# The two populations overlap slightly (real minimum 0.0284, fake maximum 0.0540), so this
# threshold is set for margin rather than for maximum catch: at 0.020 no genuine scan from
# any of the five sources is lost and 76.5% of tuned noise is caught; raising it to 0.025
# would catch 88% but leaves only 12% headroom above the lowest real scan.
#
# Heavily downscaled scans can fall below this -- resampling to 224x224 pulled the Korean
# derived set down to a minimum of 0.0122. That is a true statement about the frame: the
# resolution-cell asymmetry has been interpolated away and can no longer be verified.
ISOTROPY_FLOOR = 0.020


class Decision(str, Enum):
    ACCEPTED = "accepted"        # confidently a B-mode ultrasound frame
    BORDERLINE = "borderline"    # inside the outer bounds but off-centre; needs a human
    REJECTED = "rejected"        # texture is not speckle
    UNMEASURABLE = "unmeasurable"  # cannot be characterised; not a verdict on content


@dataclass(frozen=True)
class Verdict:
    decision: Decision
    reason: str
    features: dict | None
    checks: dict          # per-feature value, bands and where it landed
    capture: dict = field(default_factory=dict)   # provenance: export vs photo of a screen

    @property
    def usable_for_dataset(self) -> bool:
        """Only confidently-accepted frames may seed the training corpus.

        Borderline frames are not silently included: a base dataset assembled from
        uncertain admissions inherits that uncertainty everywhere downstream.
        """
        return self.decision is Decision.ACCEPTED

    def as_dict(self) -> dict:
        return {
            "decision": self.decision.value,
            "reason": self.reason,
            "features": self.features,
            "checks": self.checks,
            "capture": self.capture,
        }


class Envelope:
    """Calibrated ranges for each speckle statistic, with a confident core."""

    def __init__(self, bounds: dict, core: dict, meta: dict | None = None):
        self.bounds = bounds
        self.core = core
        self.meta = meta or {}

    @classmethod
    def load(cls, path: Path | None = None) -> "Envelope":
        path = path or ENVELOPE_PATH
        if not path.exists():
            raise FileNotFoundError(
                f"no calibration at {path} -- run scripts/calibrate_gate.py first. "
                "The gate refuses to run on hard-coded thresholds: the accepted range "
                "depends on the scanners and post-processing in your own data."
            )
        blob = json.loads(path.read_text())
        if "core" not in blob:
            raise ValueError(
                f"{path} predates the three-band verdict; re-run scripts/calibrate_gate.py"
            )
        missing = [n for n in ENVELOPE_FEATURES if n not in blob["core"]]
        if missing:
            raise ValueError(
                f"{path} is missing {missing}; re-run scripts/calibrate_gate.py"
            )
        return cls(blob["bounds"], blob["core"], blob.get("meta", {}))

    def classify(self, f: SpeckleFeatures) -> tuple[Decision, dict]:
        checks: dict = {}
        outside_bounds, outside_core = [], []
        for name in ENVELOPE_FEATURES:
            value = getattr(f, name)
            lo, hi = self.bounds[name]
            clo, chi = self.core[name]
            if value < lo or value > hi:
                where = "outside"
                outside_bounds.append(name)
            elif value < clo or value > chi:
                where = "margin"
                outside_core.append(name)
            else:
                where = "core"
            checks[name] = {"value": round(value, 4), "core": [clo, chi],
                            "bounds": [lo, hi], "where": where}

        # Reported for the record, but judged against a physical floor rather than a
        # fitted band. See CONTRAST_FLOOR.
        checks["cv"] = {"value": round(f.cv, 4), "floor": CONTRAST_FLOOR,
                        "where": "core" if f.cv >= CONTRAST_FLOOR else "outside"}
        checks["anisotropy"] = {"value": round(f.anisotropy, 4), "floor": ISOTROPY_FLOOR,
                                "where": "core" if f.anisotropy >= ISOTROPY_FLOOR else "outside"}
        if f.cv < CONTRAST_FLOOR:
            return Decision.REJECTED, checks
        if f.anisotropy < ISOTROPY_FLOOR:
            return Decision.REJECTED, checks

        if outside_bounds:
            return Decision.REJECTED, checks
        if outside_core:
            return Decision.BORDERLINE, checks
        return Decision.ACCEPTED, checks


def inspect(image, envelope: Envelope | None = None) -> Verdict:
    """Judge one frame. Never raises for ordinary bad input -- returns a Verdict."""
    envelope = envelope or Envelope.load()

    from PIL import Image as _Image
    if not isinstance(image, _Image.Image):
        image = _Image.open(image)

    # Read provenance from the colour file before physics discards the channels.
    capture = provenance.assess(image)

    try:
        features = measure(image)
    except NotMeasurable as exc:
        return Verdict(
            decision=Decision.UNMEASURABLE,
            reason=f"ประเมินไม่ได้: {exc}",
            features=None,
            checks={},
            capture=capture,
        )

    decision, checks = envelope.classify(features)

    if decision is Decision.ACCEPTED:
        reason = "ลายเซ็น speckle อยู่ในช่วงกลางของภาพอัลตราซาวด์จริง"
    elif decision is Decision.BORDERLINE:
        edge = ", ".join(n for n, c in checks.items() if c["where"] == "margin")
        reason = f"ก้ำกึ่ง — {edge} อยู่ริมขอบช่วงที่ยอมรับ ควรให้คนตรวจก่อนใช้"
    else:
        if checks["cv"]["where"] == "outside":
            reason = (f"ลายผิวเรียบเกินกว่าจะเป็นเนื้อเยื่อ: cv={checks['cv']['value']} "
                      f"ต่ำกว่าพื้นขั้นต่ำ {CONTRAST_FLOOR}")
        elif checks["anisotropy"]["where"] == "outside":
            reason = (f"ลายผิวกลมเกินไป ({checks['anisotropy']['value']} ต่ำกว่า "
                      f"{ISOTROPY_FLOOR}) — speckle จริงต้องยืดตามแนว เพราะความละเอียด "
                      "แนวลึกกับแนวข้างของเครื่องไม่เท่ากัน")
        else:
            detail = ", ".join(
                f"{n}={checks[n]['value']} (ต้องอยู่ {checks[n]['bounds'][0]}–{checks[n]['bounds'][1]})"
                for n in ENVELOPE_FEATURES if checks[n]["where"] == "outside"
            )
            reason = f"ไม่ใช่ลายเซ็นของภาพอัลตราซาวด์: {detail}"

    if (decision is Decision.ACCEPTED
            and features.tissue_fraction > SURROUND_UNVERIFIABLE):
        decision = Decision.BORDERLINE
        reason = (
            f"เกือบทั้งเฟรมสว่างเหนือระดับเนื้อเยื่อ ({features.tissue_fraction:.1%}) "
            "จึงยืนยันไม่ได้ว่ามีพื้นที่นอกช่องสแกนที่ควรมืด — อาจเป็นภาพที่ crop ชิดจริง "
            "หรือภาพที่ถูกกลับสี ต้องให้คนดูก่อนใช้"
        )

    # Provenance may only downgrade a verdict, never rescue one. A frame that fails the
    # physics test is out regardless of how cleanly it was exported.
    if capture["status"] == "rephotographed" and decision is not Decision.REJECTED:
        decision, reason = Decision.REJECTED, capture["note"]
    elif capture["status"] == "suspect" and decision is Decision.ACCEPTED:
        decision, reason = Decision.BORDERLINE, capture["note"]

    return Verdict(decision=decision, reason=reason,
                   features=features.as_dict(), checks=checks, capture=capture)
