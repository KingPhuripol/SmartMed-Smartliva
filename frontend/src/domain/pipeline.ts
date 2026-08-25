/**
 * SmartLiva domain — the staged pipeline and the study record it produces.
 *
 * The pipeline is a sequence of GATES. Each stage either passes the study on,
 * rejects it with a code, or is skipped. There is no "half-succeeded" state and
 * no bare `null` to interpret: the record always says where it stopped and why.
 */

import type { AgentOutputSet } from './agents'
import type { SupervisorReview } from './supervisor'
import type {
  ImageIntake,
  OrganCheck,
  QualityCheck,
  SegmentationResult,
  TriageClassification,
  TriageResult,
} from './study'

export type StageId =
  | 'intake'
  | 'quality'
  | 'organ'
  | 'segmentation'
  | 'triage'
  | 'agents'
  | 'supervisor'
  | 'report'

export const STAGE_ORDER = [
  'intake',
  'quality',
  'organ',
  'segmentation',
  'triage',
  'agents',
  'supervisor',
  'report',
] as const

export type StageStatus =
  | 'pending'
  | 'running'
  | 'passed'
  | 'rejected'
  | 'skipped'
  | 'failed'

export interface StageState {
  stageId: StageId
  status: StageStatus
  startedAt: string | null
  endedAt: string | null
  /** Present when status is 'skipped' or 'failed'; rejections carry a code instead. */
  detail?: string
}

/** Why a study stopped before reaching the report. */
export type HaltReason =
  | 'QUALITY_REJECTED'
  | 'NOT_LIVER_ULTRASOUND'
  | 'SEGMENTATION_FAILED'
  | 'ENGINE_ERROR'
  | 'CANCELLED'

export interface Halt {
  stageId: StageId
  reason: HaltReason
  /** Physician-facing explanation, resolved from a code by the UI layer. */
  detail: string
  haltedAt: string
}

/**
 * Everything the system produced for one image. Immutable once the pipeline
 * finishes — physician input lives in a separate `PhysicianReview` record so
 * that "what the AI said" is always recoverable.
 */
export interface StudyRecord {
  schemaVersion: string
  studyId: string
  intake: ImageIntake

  quality: QualityCheck | null
  organ: OrganCheck | null
  segmentation: SegmentationResult | null
  triage: TriageResult | null
  agents: AgentOutputSet
  supervisor: SupervisorReview | null

  stages: StageState[]
  /** Null means the pipeline ran to completion. */
  halt: Halt | null

  createdAt: string
  completedAt: string | null
}

/* ------------------------------------------------------ stage runner contracts */

/**
 * The three single-model gates. Each mirrors `AgentRunner` / `SupervisorRunner`:
 * one method, typed input, typed output, cancellable.
 *
 * Every stage in the pipeline is replaceable through one of these five
 * interfaces — that is the whole extension surface of the engine.
 */
export interface OrganCheckRunner {
  run(intake: ImageIntake, signal?: AbortSignal): Promise<OrganCheck>
}

export interface SegmentationRunner {
  run(intake: ImageIntake, signal?: AbortSignal): Promise<SegmentationResult>
}

export interface TriageRunner {
  run(
    intake: ImageIntake,
    segmentation: SegmentationResult,
    signal?: AbortSignal,
  ): Promise<TriageResult>
}

/* ------------------------------------------------------------ runner contract */

export interface PipelineProgress {
  stageId: StageId
  status: StageStatus
  /** 0..1 across the whole pipeline, for the progress bar. */
  overall: number
}

export interface PipelineOptions {
  /**
   * Run the four agents even when triage says the liver is normal.
   *
   * A false negative at triage is the most dangerous failure in this flow, so
   * the physician can always force the full assessment.
   */
  forceAgents?: boolean
  signal?: AbortSignal
  onProgress?: (progress: PipelineProgress) => void
}

export interface PipelineRunner {
  run(intake: ImageIntake, options?: PipelineOptions): Promise<StudyRecord>
}

/* ------------------------------------------------------------------ helpers */

export function stageState(record: StudyRecord, stageId: StageId): StageState | undefined {
  return record.stages.find((s) => s.stageId === stageId)
}

/** True when the study reached the report stage without halting. */
export function isReportable(record: StudyRecord): boolean {
  return record.halt === null && record.completedAt !== null
}

/** The classification the report should use, honouring a physician override. */
export function effectiveClassification(
  record: StudyRecord,
  override?: TriageClassification,
): TriageClassification | null {
  return override ?? record.triage?.classification ?? null
}
