/**
 * SmartLiva domain — the LLM supervisor that sits above the four agents.
 *
 * Its job is to judge each agent and to reason across them together. It is a
 * SECOND OPINION, never an authority: it must not silently overwrite an agent's
 * value. Both are shown to the physician, side by side.
 */

import type { AgentId, AgentOutput, AgentValueMap } from './agents'
import type { ImageIntake, SegmentationResult, TriageResult } from './study'

export type Agreement = 'agree' | 'uncertain' | 'disagree'

export type RiskLevel = 'low' | 'moderate' | 'high' | 'critical'

export const RISK_ORDER: readonly RiskLevel[] = ['low', 'moderate', 'high', 'critical']

export interface SupervisorAgentAssessment<K extends AgentId = AgentId> {
  agentId: K
  agreement: Agreement
  /** Why the supervisor agrees or doubts — must be specific, not "looks fine". */
  note: string
  /** Only present when `agreement === 'disagree'`; a suggestion, not a decision. */
  suggestedValue?: AgentValueMap[K]
}

export type ConflictSeverity = 'info' | 'warning' | 'critical'

/**
 * A clinically implausible combination across agents — e.g. F4 cirrhosis
 * alongside S0 and no lesions. This is the main thing the supervisor adds that
 * no single agent can see.
 */
export interface SupervisorConflict {
  conflictId: string
  agents: AgentId[]
  description: string
  severity: ConflictSeverity
}

export interface SupervisorReview {
  perAgent: SupervisorAgentAssessment[]
  conflicts: SupervisorConflict[]
  overallRisk: RiskLevel
  /** Narrative synthesis in clinical language. */
  impression: string
  recommendations: string[]
  modelVersion: string
  latencyMs: number
  simulated: boolean
  reviewedAt: string
}

export interface SupervisorInput {
  intake: ImageIntake
  segmentation: SegmentationResult
  triage: TriageResult
  agentOutputs: AgentOutput[]
}

/**
 * Swap between a rule-based stub, a hosted LLM, or an on-premise model without
 * touching the pipeline or the UI.
 *
 * Note for the real implementation: an ultrasound image is health data. Sending
 * it — or anything derived from it — to a third-party LLM has PDPA implications
 * that must be settled before this interface is backed by a remote service.
 */
export interface SupervisorRunner {
  run(input: SupervisorInput, signal?: AbortSignal): Promise<SupervisorReview>
}
