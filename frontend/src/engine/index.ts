import { createPipeline } from './pipeline'
import { createLiverUsRunners } from './http/liverUsAdapter'
import {
  createHttpFibrosisRunner,
  createHttpFlukeRunner,
  createHttpLesionRunner,
  createHttpSteatosisRunner,
} from './http/realAgents'
import { stubTriage } from './stubs/triage'
import { ruleBasedSupervisor } from './supervisor'

/**
 * The wiring point for the entire SmartLiva analysis engine.
 *
 * Organ Check & Segmentation: Real LiverUS Gatekeeper + UNet Multi-Organ
 * Triage: Gated triage evaluation
 * Specialist Agents (Fibrosis, Steatosis, Lesion, Fluke): Real Deep Learning Models (simulated: false)
 * Supervisor: Rule-based cross-agent conflict engine + clinical second opinion
 */
const liverUs = createLiverUsRunners()

export const REAL_AGENT_RUNNERS = [
  createHttpFibrosisRunner(),
  createHttpSteatosisRunner(),
  createHttpLesionRunner(),
  createHttpFlukeRunner(),
]

export const analysisPipeline = createPipeline({
  organCheck: liverUs.organCheck,
  segmentation: liverUs.segmentation,
  triage: stubTriage,
  agents: REAL_AGENT_RUNNERS,
  supervisor: ruleBasedSupervisor,
})

export { createPipeline } from './pipeline'
export type { PipelineDeps } from './pipeline'
export {
  createIntake,
  createSyntheticIntake,
  decodeImage,
  measure,
  runQualityGate,
} from './qualityGate'
export { ruleBasedSupervisor } from './supervisor'
export { REAL_AGENT_RUNNERS as AGENT_RUNNERS }
