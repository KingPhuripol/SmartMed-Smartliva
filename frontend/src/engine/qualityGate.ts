import type {
  ImageIntake,
  QualityCheck,
  QualityCriteria,
  QualityMeasurement,
  QualityRejectCode,
  QualityWarningCode,
} from '../domain'
import { NEAR_MINIMUM_MARGIN, QUALITY_CRITERIA } from '../config/quality'

/**
 * Stage 1 — the image quality gate.
 *
 * This runs BEFORE any model sees the image, on purpose: analysing a
 * low-resolution or cropped frame produces a confident-looking answer built on
 * detail that is not there, which is exactly the bias the gate exists to stop.
 *
 * Unlike the model stages this is fully implemented — it is pure measurement.
 */

export interface DecodedImage {
  width: number
  height: number
  /** Stable Data URL for the decoded file (persists across runs without revoking) */
  objectUrl: string
}

/** Decodes a file far enough to measure it. Rejects if the bytes are not an image. */
export function decodeImage(file: File): Promise<DecodedImage> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const dataUrl = reader.result as string
      const img = new Image()
      img.onload = () => {
        resolve({ width: img.naturalWidth, height: img.naturalHeight, objectUrl: dataUrl })
      }
      img.onerror = () => {
        reject(new Error('IMAGE_UNREADABLE'))
      }
      img.src = dataUrl
    }
    reader.onerror = () => {
      reject(new Error('IMAGE_UNREADABLE'))
    }
    reader.readAsDataURL(file)
  })
}

export function measure(file: File, decoded: DecodedImage): QualityMeasurement {
  return {
    width: decoded.width,
    height: decoded.height,
    pixels: decoded.width * decoded.height,
    byteSize: file.size,
    mimeType: file.type || 'image/jpeg',
    aspectRatio: decoded.height === 0 ? 0 : decoded.width / decoded.height,
  }
}

/**
 * Applies the criteria. Collects EVERY failure rather than short-circuiting.
 */
export function runQualityGate(
  measured: QualityMeasurement,
  criteria: QualityCriteria = QUALITY_CRITERIA,
  checkedAt: string = new Date().toISOString(),
): QualityCheck {
  const rejections: QualityRejectCode[] = []
  const warnings: QualityWarningCode[] = []

  if (
    criteria.acceptedMimeTypes.length > 0 &&
    measured.mimeType &&
    !criteria.acceptedMimeTypes.includes(measured.mimeType) &&
    !measured.mimeType.startsWith('image/')
  ) {
    rejections.push('UNSUPPORTED_FORMAT')
  }
  if (measured.byteSize > criteria.maxByteSize) {
    rejections.push('FILE_TOO_LARGE')
  }
  if (measured.width < criteria.minWidth || measured.height < criteria.minHeight) {
    rejections.push('RESOLUTION_TOO_LOW')
  }
  if (measured.pixels < criteria.minPixels) {
    rejections.push('PIXEL_COUNT_TOO_LOW')
  }
  if (
    measured.aspectRatio < criteria.minAspectRatio ||
    measured.aspectRatio > criteria.maxAspectRatio
  ) {
    rejections.push('ASPECT_RATIO_OUT_OF_RANGE')
  }

  if (
    rejections.length === 0 &&
    measured.width < criteria.minWidth * NEAR_MINIMUM_MARGIN &&
    measured.height < criteria.minHeight * NEAR_MINIMUM_MARGIN
  ) {
    warnings.push('NEAR_MINIMUM_RESOLUTION')
  }

  return {
    passed: rejections.length === 0,
    criteria,
    measured,
    rejections,
    warnings,
    checkedAt,
  }
}

export function createIntake(file: File, decoded: DecodedImage): ImageIntake {
  return {
    imageId: `img-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    fileName: file.name,
    mimeType: file.type || 'image/jpeg',
    byteSize: file.size,
    width: decoded.width,
    height: decoded.height,
    source: decoded.objectUrl,
    receivedAt: new Date().toISOString(),
  }
}

export function createSyntheticIntake(
  dataUrl: string,
  fileName: string,
  width: number,
  height: number,
  byteSize: number,
): ImageIntake {
  return {
    imageId: `img-synth-${Date.now()}`,
    fileName,
    mimeType: 'image/png',
    byteSize,
    width,
    height,
    source: dataUrl,
    receivedAt: new Date().toISOString(),
  }
}
