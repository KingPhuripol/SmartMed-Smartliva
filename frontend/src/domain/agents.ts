/**
 * SmartLiva domain — the four specialist agents.
 *
 * Every agent produces the SAME envelope (`AgentOutput`), differing only in the
 * type of `value`. That is what lets the UI render any number of agents without
 * knowing what they do, and lets a real model replace a stub one at a time.
 */

import type { ImageIntake, Region, SegmentationResult, TriageResult } from './study'

export type AgentId = 'fibrosis' | 'steatosis' | 'lesion' | 'fluke'

/** Canonical order — used for rendering, reports and payloads. */
export const AGENT_IDS = ['fibrosis', 'steatosis', 'lesion', 'fluke'] as const

/* ----------------------------------------------------------- value shapes */

export type FibrosisStage = 'F0' | 'F1' | 'F2' | 'F3' | 'F4'
export type SteatosisStage = 'S0' | 'S1' | 'S2' | 'S3'
export type FlukeResult = 'Negative' | 'Positive'

export interface LesionFinding {
  findingId: string
  /** Class label from the detector, e.g. "Cyst", "Hemangioma". */
  label: string
  /** Longest axis in millimetres — null until pixel spacing is known. */
  confidence: number
  /** Region in the agent's `regions[]` that outlines this finding. */
  regionId: string
}

export interface LesionResult {
  findings: LesionFinding[]
}

/** Maps each agent to the type of answer it gives. */
export interface AgentValueMap {
  fibrosis: FibrosisStage
  steatosis: SteatosisStage
  lesion: LesionResult
  fluke: FlukeResult
}

export const FIBROSIS_STAGES: readonly FibrosisStage[] = ['F0', 'F1', 'F2', 'F3', 'F4']
export const STEATOSIS_STAGES: readonly SteatosisStage[] = ['S0', 'S1', 'S2', 'S3']
export const FLUKE_RESULTS: readonly FlukeResult[] = ['Negative', 'Positive']

/* --------------------------------------------------------------- envelope */

export interface AgentOutput<K extends AgentId = AgentId> {
  agentId: K
  value: AgentValueMap[K]
  confidence: number
  /** Areas the agent based its answer on — colour-coded and toggleable in the UI. */
  regions: Region[]
  /**
   * Why the agent landed here, in one or two sentences.
   * Shown to the physician AND fed to the supervisor — a bare number is not
   * reviewable, and the supervisor cannot cross-check reasoning it cannot see.
   */
  rationale: string
  modelVersion: string
  inferenceMs: number
  /** True while a stub stands in for a model that is not wired up yet. */
  simulated: boolean
}

/** Partial by design: agents can be added, or fail, without breaking the record. */
export type AgentOutputSet = { [K in AgentId]?: AgentOutput<K> }

/* ----------------------------------------------------------- runner contract */

export interface AgentInput {
  intake: ImageIntake
  segmentation: SegmentationResult
  triage: TriageResult
}

/**
 * One agent. Swap the implementation (stub → HTTP call → on-device model)
 * without any other file changing.
 */
export interface AgentRunner<K extends AgentId = AgentId> {
  readonly agentId: K
  run(input: AgentInput, signal?: AbortSignal): Promise<AgentOutput<K>>
}

/** Raised by a runner so the pipeline can record a per-agent failure. */
export class AgentError extends Error {
  readonly agentId: AgentId
  readonly detail: unknown

  constructor(agentId: AgentId, message: string, detail?: unknown) {
    super(message)
    this.name = 'AgentError'
    this.agentId = agentId
    this.detail = detail
  }
}
