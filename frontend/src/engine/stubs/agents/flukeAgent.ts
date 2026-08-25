import type { AgentOutput, AgentRunner, Region } from '../../../domain'
import { delay } from '../../util'

/**
 * Agent 4 — Opisthorchis viverrini (liver fluke) findings.
 *
 * ⚠️ STUB.
 *
 * A NEGATIVE result still returns regions: they show which biliary structures
 * were examined. "Nothing found" and "nowhere looked" are different claims, and
 * the physician reviewing this agent needs to tell them apart.
 */
const EXAMINED: Region[] = [
  {
    regionId: 'fluke-region-01',
    shape: 'freehand',
    points: [
      [0.47, 0.72],
      [0.5, 0.62],
      [0.5, 0.53],
      [0.45, 0.45],
      [0.4, 0.4],
    ],
    label: 'Periportal tract examined',
    confidence: 0.98,
    source: 'fluke',
  },
  {
    regionId: 'fluke-region-02',
    shape: 'freehand',
    points: [
      [0.5, 0.55],
      [0.6, 0.55],
      [0.72, 0.5],
    ],
    label: 'Right intrahepatic duct examined',
    confidence: 0.97,
    source: 'fluke',
  },
]

export const stubFlukeAgent: AgentRunner<'fluke'> = {
  agentId: 'fluke',
  async run(_input, signal) {
    const started = performance.now()
    await delay(700, signal)

    const output: AgentOutput<'fluke'> = {
      agentId: 'fluke',
      value: 'Negative',
      confidence: 0.98,
      regions: EXAMINED,
      rationale:
        'Intrahepatic ducts are non-dilated with no periductal echogenic thickening or gallbladder sludge.',
      modelVersion: 'stub-fluke-0.1',
      inferenceMs: Math.round(performance.now() - started),
      simulated: true,
    }
    return output
  },
}
