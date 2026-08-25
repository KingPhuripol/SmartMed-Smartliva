/**
 * SmartLiva domain layer.
 *
 * Import from `@/domain` (or `../domain`) — never reach into the individual
 * files from UI code, so the internal split can change without a wide refactor.
 *
 *   study.ts       intake, quality gate, regions, organ check, segmentation, triage
 *   agents.ts      the four specialist agents and their common envelope
 *   supervisor.ts  the LLM second opinion that sits above the agents
 *   pipeline.ts    stage sequence, halts, and the immutable StudyRecord
 *   review.ts      physician verdicts, audit trail, training feedback
 */

export * from './study'
export * from './agents'
export * from './supervisor'
export * from './pipeline'
export * from './review'
