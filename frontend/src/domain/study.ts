/**
 * SmartLiva domain — intake, image quality and geometry.
 *
 * Everything in `src/domain/` is pure TypeScript: no React, no fetch, no DOM.
 * The UI, the mock engine and the real backend all speak these types, so any of
 * them can be replaced without touching the others.
 */

/** Bump when a stored record's shape changes; never reuse a version number. */
export const SCHEMA_VERSION = '2.0.0'

/* ----------------------------------------------------------- clinical data */

export interface PatientHistory {
  age?: number
  gender?: 'M' | 'F'
  hbv_positive?: boolean
  hcv_positive?: boolean
  alcohol_history?: boolean
  raw_fish_consumption?: boolean
  fluke_infection_history?: boolean
  family_cancer_history?: boolean
  endemic_area?: boolean
  diabetes?: boolean
  dyslipidemia?: boolean
  weight_kg?: number
  height_cm?: number
  bmi?: number
}

export interface LabData {
  ast?: number
  alt?: number
  platelets?: number
  bilirubin?: number
  alp?: number
  ggt?: number
  afp?: number
  ca19_9?: number
  fbs?: number
  hba1c?: number
}

export interface TEData {
  stiffness_kpa?: number
  cap_db_m?: number
}

export interface BiomarkersInfo {
  fib4_score?: number
  fib4_risk_tier?: string
  fib4_interpretation?: string
  apri_score?: number
  apri_risk_tier?: string
  calculated?: boolean
}

export interface ClinicalData {
  view?: string
  history?: PatientHistory
  lab?: LabData
  te?: TEData
  biomarkers?: BiomarkersInfo
}

/* ------------------------------------------------------------------ intake */

export interface ImageIntake {
  imageId: string
  fileName: string
  mimeType: string
  byteSize: number
  /** Pixel dimensions as decoded, before any resizing. */
  width: number
  height: number
  /**
   * Where the pixels live. In the browser build this is an object/data URL;
   * in production it is the object-store key. Never assume it is fetchable.
   */
  source: string
  receivedAt: string
  /** Patient clinical history, blood labs and biomarkers if provided */
  clinical?: ClinicalData | null
}

/* ----------------------------------------------------------- quality gate */

/**
 * Reject reasons are codes, not sentences — so they can be translated, counted
 * in analytics ("which reason rejects the most images?") and asserted in tests.
 */
export type QualityRejectCode =
  | 'RESOLUTION_TOO_LOW'
  | 'PIXEL_COUNT_TOO_LOW'
  | 'ASPECT_RATIO_OUT_OF_RANGE'
  | 'FILE_TOO_LARGE'
  | 'UNSUPPORTED_FORMAT'
  | 'IMAGE_UNREADABLE'

/** Non-blocking observations — the study proceeds but the report notes them. */
export type QualityWarningCode =
  | 'LIKELY_RECOMPRESSED'
  | 'NEAR_MINIMUM_RESOLUTION'
  | 'UNUSUAL_ASPECT_RATIO'

/**
 * The bar an image must clear before any model sees it.
 *
 * Held in one object on purpose: the threshold is a clinical decision, not a
 * constant scattered through the code, and it has to be quotable in the report.
 */
export interface QualityCriteria {
  minWidth: number
  minHeight: number
  minPixels: number
  maxByteSize: number
  acceptedMimeTypes: readonly string[]
  /** width / height bounds — screenshots and crops fall outside these. */
  minAspectRatio: number
  maxAspectRatio: number
}

export interface QualityMeasurement {
  width: number
  height: number
  pixels: number
  byteSize: number
  mimeType: string
  aspectRatio: number
}

export interface QualityCheck {
  passed: boolean
  /** Snapshot of the criteria in force at check time, for auditability. */
  criteria: QualityCriteria
  measured: QualityMeasurement
  rejections: QualityRejectCode[]
  warnings: QualityWarningCode[]
  checkedAt: string
}

/* ---------------------------------------------------------------- regions */

export type RegionShape = 'point' | 'box' | 'polygon' | 'freehand'

/** Who drew this region — drives colour, toggling and training weight. */
export type RegionSource = AgentId | 'segmentation' | 'physician'

/**
 * A labelled area on the image.
 *
 * `points` are ALWAYS normalised to 0..1 against the intake dimensions, so a
 * region stays correct across screen sizes, zoom, side-by-side panes and
 * machines that produce different aspect ratios.
 *
 * - `point`    → exactly 1 pair
 * - `box`      → exactly 2 pairs (top-left, bottom-right)
 * - `polygon`  → 3+ pairs, implicitly closed
 * - `freehand` → 2+ pairs, open path
 */
export interface Region {
  regionId: string
  shape: RegionShape
  points: Array<[number, number]>
  label: string
  /** Model confidence 0..1, or null for anything a physician drew. */
  confidence: number | null
  source: RegionSource
  note?: string
  /**
   * Set when the physician drew this while correcting a specific agent. It ties
   * "the model was wrong" to "and here is where", which is the pair a retraining
   * run needs — a reason without a location cannot be pointed at a pixel.
   */
  linkedAgentId?: AgentId
}

/* --------------------------------------------------------- organ & triage */

/**
 * What the service said about this image, kept alongside the derived result.
 *
 * The derived `OrganCheck` and `SegmentationResult` answer "what did the model
 * decide"; this answers "on what basis, and how far can it be trusted" — which
 * is the part a reader months from now cannot reconstruct.
 */
export interface ServiceGateReport {
  apiVersion: string
  modelVersion: string
  verdict: string
  confidence: number | null
  quality: { status: 'ACCEPT' | 'BORDERLINE' | 'REJECT'; score: number; reasons: string[] | null }
  top3: Array<[string, number]>
  /** Carried verbatim, including values this build does not recognise. */
  warnings: string[]
  frame: { width: number; height: number }
  areaPx: number
  areaPctFrame: number
  /** Rings the service found inside the liver that a single-ring Region cannot hold. */
  holesDropped: number
  timingMs: { gate: number; contour: number; total: number }
}

export interface OrganCheck {
  isLiverUltrasound: boolean
  /**
   * null when the image was cut before organ classification ran. A number here
   * is NOT a safety margin: the model's own evaluation shows it calling unseen
   * scanners "liver" at 0.95 mean confidence, so this may be read but must
   * never be used as a threshold.
   */
  confidence: number | null
  modelVersion: string
  /** True while no real model backs this step. */
  simulated: boolean
  checkedAt: string
  /**
   * Everything the model service reported, kept verbatim. The fields above say
   * what was decided; this says on what basis and how far it can be trusted.
   * null when a stub produced the answer.
   */
  service: ServiceGateReport | null
}

export interface SegmentationResult {
  /** Liver capsule outline(s) — usually one polygon. */
  regions: Region[]
  /**
   * null unless a real physical scale is known. Without DICOM there is no pixel
   * spacing, and the service reports pixels only — an area in cm² would be an
   * invention.
   */
  areaCm2: number | null
  /**
   * null when the producer publishes no confidence for the outline itself. The
   * organ gate's confidence is a different measurement and must not stand in
   * for this one.
   */
  confidence: number | null
  modelVersion: string
  simulated: boolean
}

export type TriageClassification = 'normal' | 'abnormal'

export interface TriageResult {
  classification: TriageClassification
  confidence: number
  /** Short justification surfaced to the physician and to the supervisor. */
  rationale: string
  modelVersion: string
  simulated: boolean
}

// Imported last to keep the agent contract in its own module.
import type { AgentId } from './agents'
