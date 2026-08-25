import type { QualityCriteria } from '../domain'

/**
 * The image-quality bar, in one place.
 *
 * This is a CLINICAL decision, not a technical constant — the whole point of
 * the gate is to keep low-quality input from biasing the models. Changing a
 * number here changes what the system is willing to diagnose, so it is quoted
 * verbatim in every report and stored on every study record.
 *
 * ⚠️ Values below are placeholders pending the team's agreed threshold.
 */
export const QUALITY_CRITERIA: QualityCriteria = {
  minWidth: 512,
  minHeight: 384,
  minPixels: 512 * 384,
  maxByteSize: 25 * 1024 * 1024,
  acceptedMimeTypes: ['image/png', 'image/jpeg', 'image/webp', 'image/bmp'],
  // Ultrasound frames are broadly landscape; a 1:3 screenshot is not a study.
  minAspectRatio: 0.6,
  maxAspectRatio: 2.2,
}

/** Within this margin of the minimum, the image passes but is flagged. */
export const NEAR_MINIMUM_MARGIN = 1.15
