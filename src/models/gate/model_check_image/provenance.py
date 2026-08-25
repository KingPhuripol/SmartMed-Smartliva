"""Did this file come off the scanner, or is it a photograph of a scanner's screen?

This is a different question from the one physics.py answers, and it has to be asked
separately. Photographing a monitor preserves speckle statistics well enough that a
re-photographed frame passes the modality gate confidently: in the first build of the
base dataset, an estimated 156 of the 7,778 admitted frames were camera photos of a
display, including frames showing focal lesions.

They must not seed a dataset. The physical scale is lost (the on-screen depth ruler no
longer maps to the pixel grid), the texture carries the display's pixel structure and
the camera's own demosaicing, and the geometry is off-axis. A model trained on a mix of
exports and re-photographs can learn to tell them apart and use that instead of anatomy
-- the same class of shortcut that made the previous system's gate useless.

The signal
----------
Colourfulness of the frame as a whole would be the obvious test and is the wrong one:
colour Doppler is genuine ultrasound and is genuinely colourful. What separates the two
is *where* the colour sits. A scanner writes its un-imaged surround as true black, so
the darkest pixels of an export have no chroma at all -- measured across 700 exports from
four scanners, the 95th percentile of background tint is 0.00 of 255 and the maximum is
2.52. A camera records room light and the panel's own tint there instead; the same
measurement on 250 confirmed photographs of a monitor has a median of 3.64 and reaches
23.94. Doppler colour lives in the bright sector and never enters this measurement.
"""
from __future__ import annotations

import numpy as np

# Which pixels count as "the surround". Originally the darkest quarter of the frame, which
# was wrong for two reasons that only showed up once a fourth scanner arrived: on a tightly
# cropped frame the darkest quarter reaches into tissue, and on a sepia-toned export that
# tissue carries chroma. The result was 9.5% of genuine Dhaka scanner exports hard-rejected
# as photographs of a screen. Taking only the darkest 5% keeps the measurement inside the
# true background.
DARK_PERCENTILE = 5.0

# Measured at DARK_PERCENTILE = 5 on 700 confirmed scanner exports spanning four sources
# (Dhaka sepia, Thai machine-tagged, BEHSOF, fibrosis-TE) and 250 confirmed photographs of
# a monitor (the Thai mapping.xlsx Source=mobile column):
#
#     background tint        p50     p95     p99     max
#     scanner exports       0.00    0.00    0.50    2.52
#     photographed screen   3.64   15.41   21.42   23.94
#
# Thresholds sit in the gap between those two populations rather than being inherited from
# the old percentile. Against the previous settings (darkest 25%, 2.0/6.0) this is better
# on both axes at once: exports falsely rejected 9.5% -> 0.00%, photographs detected
# 76.5% -> 82.0%.
#
# Caveat worth keeping in mind: the photographed-screen side is ground-truthed from one
# source only, because no other corpus here labels capture method.
TINT_SUSPECT = 0.8   # -> borderline, a human should look
TINT_REPHOTOGRAPHED = 3.0   # -> rejected


def background_tint(image) -> float:
    """Mean chroma of the darkest DARK_PERCENTILE of the frame, in grey levels (0-255).

    Returns 0.0 for a greyscale file: a single-channel image has no chroma to measure,
    so this check simply abstains rather than pretending the frame is clean.
    """
    from PIL import Image

    if not isinstance(image, Image.Image):
        image = Image.open(image)
    if image.mode in ("L", "1", "I", "F"):
        return 0.0
    if image.mode in ("RGBA", "LA", "P"):
        rgba = image.convert("RGBA")
        flat = Image.new("RGBA", rgba.size, (0, 0, 0, 255))
        flat.alpha_composite(rgba)
        image = flat

    arr = np.asarray(image.convert("RGB").resize((200, 200)), dtype=np.float32)
    luminance = arr.mean(axis=2)
    dark = arr[luminance <= np.percentile(luminance, DARK_PERCENTILE)]
    if dark.size == 0:
        return 0.0
    return float(np.mean(dark.max(axis=1) - dark.min(axis=1)))


def assess(image) -> dict:
    """Judge capture provenance. Never raises; abstains on greyscale input."""
    tint = background_tint(image)
    if tint >= TINT_REPHOTOGRAPHED:
        status = "rephotographed"
        note = (f"พื้นหลังนอกช่องสแกนมีสีเจือ {tint:.1f} — เป็นภาพถ่ายจากหน้าจอเครื่อง "
                "ไม่ใช่ไฟล์ที่ export จากเครื่องโดยตรง")
    elif tint >= TINT_SUSPECT:
        status = "suspect"
        note = f"พื้นหลังมีสีเจือเล็กน้อย {tint:.1f} — อาจถ่ายจากหน้าจอ ควรให้คนดูก่อนใช้"
    else:
        status = "exported"
        note = "พื้นหลังดำสนิทไม่มีสีเจือ สอดคล้องกับไฟล์ที่ export จากเครื่อง"
    return {"status": status, "background_tint": round(tint, 3), "note": note}
