/**
 * SmartLiva domain — physician review and the training signal it produces.
 *
 * Held separately from `StudyRecord` on purpose. The AI's output is written
 * once and never edited; the physician's judgement accumulates alongside it.
 * That separation is what makes "AI said X, physician said Y" recoverable — the
 * audit trail a medical tool needs, and the label a retraining run needs.
 */

import type { AgentId, AgentValueMap } from './agents'
import { AGENT_IDS } from './agents'
import type { Region, TriageClassification } from './study'
import { SCHEMA_VERSION } from './study'
import type { StudyRecord } from './pipeline'

export type Verdict = 'pending' | 'correct' | 'incorrect'

export interface AgentVerdict<K extends AgentId = AgentId> {
  agentId: K
  verdict: Verdict
  /** The physician's value. Required whenever `verdict === 'incorrect'`. */
  correctedValue?: AgentValueMap[K]
  /**
   * Why the agent was wrong — required for 'incorrect'.
   * This free text is the most valuable field in the whole record: it is the
   * only place the model's failure mode is described in a clinician's words.
   */
  reason?: string
  reviewedAt: string | null
}

export type AgentVerdictSet = { [K in AgentId]?: AgentVerdict<K> }

/* --------------------------------------------------------- audit trail */

export type ReviewEventKind =
  | 'verdict_set'
  | 'value_corrected'
  | 'annotation_added'
  | 'annotation_removed'
  | 'triage_overridden'
  | 'agents_forced'
  | 'note_updated'
  | 'review_completed'

/**
 * Append-only. Never edit or delete an event — correcting a mistake means
 * adding another event, so the sequence of decisions stays intact.
 */
export interface ReviewEvent {
  eventId: string
  at: string
  /** Identifier of the reviewing clinician once authentication exists. */
  actor: string
  kind: ReviewEventKind
  agentId?: AgentId
  summary: string
}

export interface PhysicianReview {
  schemaVersion: string
  studyId: string
  verdicts: AgentVerdictSet
  /** Points, boxes and freehand marks the physician drew on the image. */
  annotations: Region[]
  /** Set when the physician disagrees with the normal/abnormal gate. */
  triageOverride: TriageClassification | null
  finalNote: string
  events: ReviewEvent[]
  startedAt: string
  completedAt: string | null
}

/* ------------------------------------------------------------- helpers */

export function createReview(studyId: string, startedAt: string): PhysicianReview {
  return {
    schemaVersion: SCHEMA_VERSION,
    studyId,
    verdicts: {},
    annotations: [],
    triageOverride: null,
    finalNote: '',
    events: [],
    startedAt,
    completedAt: null,
  }
}

/** A verdict counts as settled only if an 'incorrect' one carries a reason. */
export function isVerdictSettled(verdict: AgentVerdict | undefined): boolean {
  if (!verdict || verdict.verdict === 'pending') return false
  if (verdict.verdict === 'incorrect') {
    return typeof verdict.reason === 'string' && verdict.reason.trim().length > 0
  }
  return true
}

/** Agents that still need the physician's attention. */
export function pendingAgents(review: PhysicianReview, assessed: AgentId[]): AgentId[] {
  return assessed.filter((id) => !isVerdictSettled(review.verdicts[id]))
}

export function isReviewComplete(review: PhysicianReview, assessed: AgentId[]): boolean {
  return pendingAgents(review, assessed).length === 0
}

/* ------------------------------------------------- training feedback */

export interface AgentFeedback {
  agentId: AgentId
  aiValue: unknown
  aiConfidence: number
  aiRationale: string
  modelVersion: string
  simulated: boolean
  verdict: Verdict
  physicianValue: unknown
  /** Free-text failure description — the highest-value field for retraining. */
  reason: string | null
}

/**
 * What gets posted to the retraining store. Deliberately self-describing: a
 * training run months from now must be able to interpret it without this
 * codebase.
 */
export interface TrainingFeedbackRecord {
  schemaVersion: string
  studyId: string
  submittedAt: string
  image: {
    fileName: string
    width: number
    height: number
    /** Storage key in production; never inline pixel data. */
    reference: string
  }
  qualityPassed: boolean
  organConfidence: number | null
  segmentationRegions: Region[]
  triage: {
    aiClassification: TriageClassification | null
    physicianOverride: TriageClassification | null
  }
  agents: AgentFeedback[]
  supervisor: {
    overallRisk: string | null
    conflictCount: number
    simulated: boolean
  }
  /** Marks the physician drew — a supervision signal no agent produced. */
  physicianAnnotations: Region[]
  finalNote: string
  correctionCount: number
  events: ReviewEvent[]
}

export function buildTrainingFeedback(
  study: StudyRecord,
  review: PhysicianReview,
  submittedAt: string,
): TrainingFeedbackRecord {
  const agents: AgentFeedback[] = AGENT_IDS.flatMap((agentId) => {
    const output = study.agents[agentId]
    if (!output) return []
    const verdict = review.verdicts[agentId]
    return [
      {
        agentId,
        aiValue: output.value,
        aiConfidence: output.confidence,
        aiRationale: output.rationale,
        modelVersion: output.modelVersion,
        simulated: output.simulated,
        verdict: verdict?.verdict ?? 'pending',
        physicianValue: verdict?.correctedValue ?? output.value,
        reason: verdict?.reason ?? null,
      },
    ]
  })

  return {
    schemaVersion: SCHEMA_VERSION,
    studyId: study.studyId,
    submittedAt,
    image: {
      fileName: study.intake.fileName,
      width: study.intake.width,
      height: study.intake.height,
      reference: study.intake.source.startsWith('data:')
        ? `inline:${study.intake.fileName}`
        : study.intake.source,
    },
    qualityPassed: study.quality?.passed ?? false,
    organConfidence: study.organ?.confidence ?? null,
    segmentationRegions: study.segmentation?.regions ?? [],
    triage: {
      aiClassification: study.triage?.classification ?? null,
      physicianOverride: review.triageOverride,
    },
    agents,
    supervisor: {
      overallRisk: study.supervisor?.overallRisk ?? null,
      conflictCount: study.supervisor?.conflicts.length ?? 0,
      simulated: study.supervisor?.simulated ?? true,
    },
    physicianAnnotations: review.annotations,
    finalNote: review.finalNote,
    correctionCount: agents.filter((a) => a.verdict === 'incorrect').length,
    events: review.events,
  }
}
