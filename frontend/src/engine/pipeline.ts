import type {
  AgentOutput,
  AgentOutputSet,
  AgentRunner,
  Halt,
  HaltReason,
  ImageIntake,
  OrganCheckRunner,
  PipelineOptions,
  PipelineRunner,
  QualityCriteria,
  QualityMeasurement,
  SegmentationRunner,
  StageId,
  StageState,
  StudyRecord,
  SupervisorRunner,
  TriageRunner,
} from '../domain'
import { SCHEMA_VERSION, STAGE_ORDER } from '../domain'
import { QUALITY_CRITERIA } from '../config/quality'
import { runQualityGate } from './qualityGate'
import { now } from './util'

/**
 * The pipeline orchestrator.
 *
 * Every stage is a gate: it passes the study on, rejects it with a reason, or
 * is skipped. The `StudyRecord` it returns always says exactly how far the
 * study got — there is no half-finished state to interpret downstream.
 *
 * The orchestrator knows nothing about *how* any stage works. Swap a stub for a
 * real model by passing a different dependency; nothing in this file changes.
 */

export interface PipelineDeps {
  organCheck: OrganCheckRunner
  segmentation: SegmentationRunner
  triage: TriageRunner
  agents: AgentRunner[]
  supervisor: SupervisorRunner
  criteria?: QualityCriteria
}

function measurementFrom(intake: ImageIntake): QualityMeasurement {
  return {
    width: intake.width,
    height: intake.height,
    pixels: intake.width * intake.height,
    byteSize: intake.byteSize,
    mimeType: intake.mimeType,
    aspectRatio: intake.height === 0 ? 0 : intake.width / intake.height,
  }
}

let studySeq = 0

function nextStudyId(at: string): string {
  studySeq += 1
  return `SL-${at.slice(2, 10).replace(/-/g, '')}-${String(studySeq).padStart(3, '0')}`
}

/** Tracks stage transitions and emits progress as the pipeline advances. */
class StageLog {
  private readonly states = new Map<StageId, StageState>()
  private readonly options: PipelineOptions | undefined

  constructor(options: PipelineOptions | undefined) {
    this.options = options
    for (const stageId of STAGE_ORDER) {
      this.states.set(stageId, {
        stageId,
        status: 'pending',
        startedAt: null,
        endedAt: null,
      })
    }
  }

  start(stageId: StageId): void {
    const state = this.states.get(stageId)!
    state.status = 'running'
    state.startedAt = now()
    this.emit(stageId)
  }

  finish(stageId: StageId, status: StageState['status'], detail?: string): void {
    const state = this.states.get(stageId)!
    state.status = status
    state.endedAt = now()
    if (detail) state.detail = detail
    this.emit(stageId)
  }

  private emit(stageId: StageId): void {
    const state = this.states.get(stageId)!
    const index = STAGE_ORDER.indexOf(stageId)
    const settled = state.status === 'running' ? index : index + 1
    this.options?.onProgress?.({
      stageId,
      status: state.status,
      overall: Math.min(1, settled / STAGE_ORDER.length),
    })
  }

  snapshot(): StageState[] {
    return STAGE_ORDER.map((id) => ({ ...this.states.get(id)! }))
  }
}

function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

export function createPipeline(deps: PipelineDeps): PipelineRunner {
  const criteria = deps.criteria ?? QUALITY_CRITERIA

  return {
    async run(intake: ImageIntake, options?: PipelineOptions): Promise<StudyRecord> {
      const createdAt = now()
      const log = new StageLog(options)
      const signal = options?.signal

      const record: StudyRecord = {
        schemaVersion: SCHEMA_VERSION,
        studyId: nextStudyId(createdAt),
        intake,
        quality: null,
        organ: null,
        segmentation: null,
        triage: null,
        agents: {},
        supervisor: null,
        stages: [],
        halt: null,
        createdAt,
        completedAt: null,
      }

      const halt = (stageId: StageId, reason: HaltReason, detail: string): StudyRecord => {
        const haltInfo: Halt = { stageId, reason, detail, haltedAt: now() }
        log.finish(stageId, reason === 'CANCELLED' ? 'failed' : 'rejected', detail)
        record.halt = haltInfo
        record.stages = log.snapshot()
        return record
      }

      try {
        /* ---------------------------------------------------------- intake */
        log.start('intake')
        log.finish('intake', 'passed')

        /* ------------------------------------------------- quality gate */
        log.start('quality')
        const quality = runQualityGate(measurementFrom(intake), criteria)
        record.quality = quality
        if (!quality.passed) {
          return halt('quality', 'QUALITY_REJECTED', quality.rejections.join(','))
        }
        log.finish('quality', 'passed')

        /* --------------------------------------------------- organ check */
        log.start('organ')
        const organ = await deps.organCheck.run(intake, signal)
        record.organ = organ
        if (!organ.isLiverUltrasound) {
          return halt('organ', 'NOT_LIVER_ULTRASOUND', `confidence=${organ.confidence}`)
        }
        log.finish('organ', 'passed')

        /* -------------------------------------------------- segmentation */
        log.start('segmentation')
        const segmentation = await deps.segmentation.run(intake, signal)
        record.segmentation = segmentation
        if (segmentation.regions.length === 0) {
          return halt('segmentation', 'SEGMENTATION_FAILED', 'no liver contour returned')
        }
        log.finish('segmentation', 'passed')

        /* --------------------------------------------------------- triage */
        log.start('triage')
        const triage = await deps.triage.run(intake, segmentation, signal)
        record.triage = triage
        log.finish('triage', 'passed')

        /* --------------------------------------------------------- agents */
        const runAgents = triage.classification === 'abnormal' || options?.forceAgents === true
        if (!runAgents) {
          log.finish(
            'agents',
            'skipped',
            'triage classified the liver as normal; no specialist assessment run',
          )
        } else {
          log.start('agents')
          const input = { intake, segmentation, triage }
          // allSettled: one agent failing must not discard the other three.
          const settled = await Promise.allSettled(
            deps.agents.map((agent) => agent.run(input, signal)),
          )
          const failures: string[] = []
          const outputs: AgentOutput[] = []
          settled.forEach((result, index) => {
            if (result.status === 'fulfilled') {
              outputs.push(result.value)
            } else {
              if (isAbort(result.reason)) throw result.reason
              failures.push(deps.agents[index].agentId)
            }
          })
          record.agents = Object.fromEntries(
            outputs.map((o) => [o.agentId, o]),
          ) as AgentOutputSet
          log.finish(
            'agents',
            failures.length === deps.agents.length ? 'failed' : 'passed',
            failures.length > 0 ? `failed: ${failures.join(', ')}` : undefined,
          )
        }

        /* ----------------------------------------------------- supervisor */
        const agentOutputs = Object.values(record.agents) as AgentOutput[]
        if (agentOutputs.length === 0) {
          log.finish('supervisor', 'skipped', 'no agent output to review')
        } else {
          log.start('supervisor')
          record.supervisor = await deps.supervisor.run(
            { intake, segmentation, triage, agentOutputs },
            signal,
          )
          log.finish('supervisor', 'passed')
        }

        /* --------------------------------------------------------- report */
        log.start('report')
        log.finish('report', 'passed')

        record.completedAt = now()
        record.stages = log.snapshot()
        return record
      } catch (error) {
        if (isAbort(error)) {
          const stage = STAGE_ORDER.find(
            (id) => log.snapshot().find((s) => s.stageId === id)?.status === 'running',
          )
          return halt(stage ?? 'intake', 'CANCELLED', 'cancelled by user')
        }
        const stage =
          log.snapshot().find((s) => s.status === 'running')?.stageId ?? 'intake'
        return halt(stage, 'ENGINE_ERROR', error instanceof Error ? error.message : 'unknown')
      }
    },
  }
}
