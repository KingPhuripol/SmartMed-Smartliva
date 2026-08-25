export type { ServiceGateReport } from '../../domain'

/**
 * The service's frozen JSON contract (api_version 1.1), transcribed as types.
 *
 * Fields are nullable rather than optional: the contract guarantees every key
 * is present, some carrying null. Modelling them as optional would let a
 * missing key pass silently as an absent one.
 */

/** The gate's decision. Only 'liver' causes an outline to be produced. */
export type LiverUsVerdict =
  | 'liver'
  | 'kidney'
  | 'gallbladder'
  | 'spleen'
  | 'pancreas'
  | 'thyroid'
  | 'breast'
  | 'carotid'
  | 'fetus'
  | 'other'
  | 'NOT_US'
  | 'LOW_QUALITY'
  | 'UNCERTAIN'

export type LiverUsQualityStatus = 'ACCEPT' | 'BORDERLINE' | 'REJECT'

/**
 * Warnings are an open set — the service may add values. Membership is tested
 * one value at a time so an unknown future warning is carried through rather
 * than crashing or being mistaken for one of these.
 */
export const WARN_NOT_CALIBRATED = 'SCANNER_NOT_CALIBRATED'
export const WARN_LOW_CONFIDENCE = 'LOW_CONFIDENCE'
export const WARN_FORCED_CONTOUR = 'FORCED_CONTOUR'

export interface LiverUsPolygon {
  /** Closed ring in ORIGINAL IMAGE PIXELS, origin top-left. No repeated last point. */
  outer: Array<[number, number]>
  holes: Array<Array<[number, number]>>
  n_points: number
  area_px: number
  area_pct_frame: number
  perimeter_px: number
}

export interface LiverUsAnalyzeOk {
  ok: true
  api_version: string
  model_version: string
  image: { name: string; width: number; height: number }
  verdict: LiverUsVerdict
  is_liver_us: boolean
  /** null when the image was cut at the quality gate, before organ classification. */
  confidence: number | null
  quality: {
    status: LiverUsQualityStatus
    score: number
    reasons: string[] | null
  }
  top3: Array<[string, number]>
  regions: {
    liver: {
      found: boolean
      polygons: LiverUsPolygon[]
      area_px_total: number
      area_pct_frame_total: number
    }
  }
  overlay_png_base64: string | null
  warnings: string[]
  timing_ms: { gate: number; contour: number; total: number }
}

export type LiverUsErrorCode =
  | 'NO_FILE'
  | 'BAD_IMAGE'
  | 'UNSUPPORTED_TYPE'
  | 'TOO_LARGE'
  | 'INFERENCE_FAILED'
  | 'NOT_FOUND'
  | 'METHOD_NOT_ALLOWED'
  | 'BAD_REQUEST'

export interface LiverUsError {
  ok: false
  error: { code: LiverUsErrorCode | string; message: string }
}

export interface LiverUsHealth {
  ok: boolean
  model_loaded: boolean
  device: string
  model_version: string
  api_version: string
  uptime_s: number
}
