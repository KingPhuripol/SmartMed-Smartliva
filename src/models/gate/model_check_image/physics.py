"""Physical signatures of B-mode ultrasound, computed without any trained model.

Why this module exists
----------------------
The previous system's input gate was a CNN trained on liver ultrasound as positives
and natural photographs (CIFAR-10) as negatives. Because clinical ultrasound has a
black background and natural photographs do not, the network learned *brightness*
rather than *tissue*. Measured on the deployed weights: inverting a liver scan --
identical structure, inverted greyscale -- dropped its score from 0.371 to 0.049,
while a pixel-shuffled version of the same scan scored 0.914. Correlation between
the gate score and mean image brightness was -0.897.

Every feature here is a **ratio or a normalised correlation**, so an affine change in
brightness cancels out. That is not a tuning choice; it is the reason the shortcut
cannot be learned in the first place.

The physics
-----------
B-mode images are formed by coherent summation of echoes from sub-resolution
scatterers. The random interference produces *speckle*: a texture whose amplitude is
Rayleigh-distributed in fully-developed regions, giving a coefficient of variation of
sqrt(4/pi - 1) ~ 0.523 before processing. Clinical scanners then apply log
compression, scan conversion and proprietary speckle reduction, which lowers the
observed CV -- measured median on our data is ~0.22, not 0.52. We therefore calibrate
the accepted envelope from real scans rather than from the textbook constant.

Speckle also has a characteristic spatial correlation length set by the resolution
cell, so neighbouring pixels are strongly correlated while pixels a few samples apart
are much less so. That decay profile is what separates real speckle from smoothed
noise, which correlates at lag 1 almost as strongly but collapses by lag 4.

Finally, the resolution cell is not round. Axial resolution comes from the transmitted
pulse length and lateral resolution from the beam width, and they are not equal, so real
speckle is elongated along one axis. That asymmetry is the one property a forger cannot
get for free: Gaussian smoothing is isotropic by construction, so noise blurred to exactly
the right correlation length still comes out round. See anisotropy below.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np

# Absolute floor for "there is no echo here at all". Only used to find the pixels that
# carry signal before the adaptive split below; JPEG ringing rarely pushes true black
# above 2/255.
NOISE_FLOOR = 2.0

# Fraction of the median lit intensity below which a pixel counts as background.
# This has to be relative: an absolute cut-off is itself a brightness dependency, and
# an earlier version of this file used one. Halving the exposure then pushed genuine
# tissue under the line, the sampled patches moved, and the verdict flipped on 6 of 50
# scans -- the same class of bug this module exists to prevent, reintroduced by the fix.
BACKGROUND_RATIO = 0.22

PATCH = 32          # resolution cells are a few pixels; 32 px holds enough of them
MIN_PATCHES = 8     # below this the estimate is too noisy to act on

# Patches are laid out on a fixed, non-overlapping grid rather than sampled at random.
#
# Random sampling made the verdict depend on which patches happened to be drawn: measured
# across 25 seeds on 80 frames, 27.5% of images changed verdict, one of them swinging all
# the way from ACCEPTED to REJECTED, and the median cv moved by 0.098 between seeds -- a
# spread comparable to the width of the band being judged against. Freezing the seed hid
# that from users but left every reported rate carrying several points of unstated noise.
#
# A grid removes the randomness entirely instead of hiding it. Stride equals the patch
# size, so every pixel contributes to exactly one patch: complete coverage, no region
# weighted twice, and the same answer on every run of every machine.
PATCH_STRIDE = PATCH


@dataclass(frozen=True)
class SpeckleFeatures:
    """Brightness-invariant descriptors of a candidate ultrasound frame."""

    cv: float               # median coefficient of variation across tissue patches
    autocorr_lag1: float    # normalised spatial autocorrelation, 1 sample apart (lateral)
    autocorr_lag4: float    # same, 4 samples apart -- captures the decay profile
    anisotropy: float       # |lateral - axial| autocorrelation at lag 1; see below
    tissue_fraction: float  # share of the frame above the adaptive background level
    n_patches: int          # how many patches the estimate is based on

    def as_dict(self) -> dict:
        return asdict(self)


class NotMeasurable(Exception):
    """Raised when the frame has too little tissue to characterise.

    This is a *refusal*, not a negative verdict: a blank frame, an extreme crop or a
    frame whose sector is unrecognisable cannot be judged either way, and the caller
    must not silently treat it as "not ultrasound".
    """


def to_grey(image, max_side: int = 700) -> np.ndarray:
    """Greyscale array, downscaled only if very large.

    Downscaling changes the speckle correlation length, so the cap must match the one
    used during calibration -- see scripts/calibrate_gate.py.
    """
    from PIL import Image

    if not isinstance(image, Image.Image):
        image = Image.open(image)
    # Composite onto black first: RGBA with transparent regions otherwise converts to
    # arbitrary greys and fabricates texture that was never in the scan.
    if image.mode in ("RGBA", "LA", "P"):
        rgba = image.convert("RGBA")
        flat = Image.new("RGBA", rgba.size, (0, 0, 0, 255))
        flat.alpha_composite(rgba)
        image = flat
    grey = image.convert("L")
    longest = max(grey.size)
    if longest > max_side:
        scale = max_side / longest
        grey = grey.resize((max(1, int(grey.size[0] * scale)),
                            max(1, int(grey.size[1] * scale))))
    return np.asarray(grey, dtype=np.float32)


def background_threshold(grey: np.ndarray) -> float:
    """Grey level separating the un-imaged surround from tissue, for *this* frame.

    Scaled to the frame's own median lit intensity, so the same anatomy imaged at a
    different gain yields the same tissue mask and therefore the same patches.
    """
    lit = grey[grey > NOISE_FLOOR]
    if lit.size < 100:
        return NOISE_FLOOR
    return max(NOISE_FLOOR, BACKGROUND_RATIO * float(np.median(lit)))


def _rank_normalise(patch: np.ndarray) -> np.ndarray:
    """Replace intensities by their ranks, scaled to [0, 1].

    Autocorrelation of ranks is a Spearman correlation, so it is unchanged by *any*
    monotonic tone curve -- gain, gamma, and the proprietary log-compression curves
    that differ between scanner vendors. Pearson autocorrelation on raw intensities
    only survives affine changes, which is why an earlier version of this file
    flipped 6 of 50 verdicts under a gamma of 0.7.
    """
    flat = patch.ravel()
    order = flat.argsort()
    ranks = np.empty(flat.size, dtype=np.float32)
    ranks[order] = np.arange(flat.size, dtype=np.float32)
    return (ranks / max(flat.size - 1, 1)).reshape(patch.shape)


def _patch_stats(patch: np.ndarray) -> tuple[float, float, float, float] | None:
    """(cv, lateral lag 1, lateral lag 4, |lateral - axial| lag 1), or None if unusable."""
    mean = float(patch.mean())
    if mean <= 0.0:
        return None
    # A patch that is almost entirely one value carries no texture to measure: either
    # it is synthetic, or the region is saturated. Ranking it would manufacture
    # structure out of tie-breaking order, so refuse instead.
    if len(np.unique(patch)) < 8:
        return None

    cv = float(patch.std()) / mean          # affine-invariant only; see docstring

    ranked = _rank_normalise(patch)
    centred = ranked - ranked.mean()
    energy = float((centred * centred).sum())
    if energy <= 0.0:
        return None
    lag1 = float((centred[:, :-1] * centred[:, 1:]).sum()) / energy
    lag4 = float((centred[:, :-4] * centred[:, 4:]).sum()) / energy
    # Same correlation down the columns. Absolute difference, so a frame stored rotated
    # by 90 degrees measures the same asymmetry rather than a negative one.
    axial = float((centred[:-1, :] * centred[1:, :]).sum()) / energy
    return cv, lag1, lag4, abs(lag1 - axial)


def measure(image) -> SpeckleFeatures:
    """Summarise the speckle statistics of every tissue patch on a fixed grid.

    Patches are required to be almost entirely inside the sector, so the black
    surround never contributes -- otherwise the "texture" being measured would partly
    be the shape of the fan, which is exactly the frame-level cue we are refusing to
    depend on.

    Deterministic: the same file always yields the same numbers. See PATCH_STRIDE.
    """
    grey = to_grey(image)
    floor = background_threshold(grey)
    tissue = grey > floor
    tissue_fraction = float(tissue.mean())
    if tissue_fraction < 0.05:
        raise NotMeasurable(f"tissue covers only {tissue_fraction:.1%} of the frame")

    height, width = grey.shape
    if height <= PATCH or width <= PATCH:
        raise NotMeasurable(f"frame {width}x{height} is smaller than one patch")

    cvs: list[float] = []
    lag1s: list[float] = []
    lag4s: list[float] = []
    anisos: list[float] = []
    for y in range(0, height - PATCH + 1, PATCH_STRIDE):
        for x in range(0, width - PATCH + 1, PATCH_STRIDE):
            patch = grey[y:y + PATCH, x:x + PATCH]
            if (patch > floor).mean() < 0.9:
                continue
            stats = _patch_stats(patch)
            if stats is None:
                continue
            cvs.append(stats[0])
            lag1s.append(stats[1])
            lag4s.append(stats[2])
            anisos.append(stats[3])

    if len(cvs) < MIN_PATCHES:
        raise NotMeasurable(
            f"only {len(cvs)} usable tissue patches on the grid (need {MIN_PATCHES}); "
            "the sector may be fragmented or the frame heavily cropped"
        )

    return SpeckleFeatures(
        cv=float(np.median(cvs)),
        autocorr_lag1=float(np.median(lag1s)),
        autocorr_lag4=float(np.median(lag4s)),
        anisotropy=float(np.median(anisos)),
        tissue_fraction=tissue_fraction,
        n_patches=len(cvs),
    )


# Theoretical CV of fully-developed Rayleigh speckle, before log compression.
# Reported alongside measurements so a reader can see how far processing moved it.
RAYLEIGH_CV = math.sqrt(4.0 / math.pi - 1.0)
