import type { AgentRunner } from '../../../domain'
import { stubFibrosisAgent } from './fibrosisAgent'
import { stubSteatosisAgent } from './steatosisAgent'
import { stubLesionAgent } from './lesionAgent'
import { stubFlukeAgent } from './flukeAgent'

/**
 * The agent registry.
 *
 * The pipeline iterates this list — it has no knowledge of which agents exist.
 * Swapping one stub for a real HTTP-backed runner, or adding a fifth agent, is
 * a one-line change here and nothing else.
 */
export const AGENT_RUNNERS: AgentRunner[] = [
  stubFibrosisAgent as AgentRunner,
  stubSteatosisAgent as AgentRunner,
  stubLesionAgent as AgentRunner,
  stubFlukeAgent as AgentRunner,
]

export { stubFibrosisAgent, stubSteatosisAgent, stubLesionAgent, stubFlukeAgent }
