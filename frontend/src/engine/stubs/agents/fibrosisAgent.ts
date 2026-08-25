import type { AgentOutput, AgentRunner, Region } from '../../../domain'
import { delay } from '../../util'

/**
 * Agent 1 — METAVIR fibrosis stage.
 *
 * ⚠️ STUB. `simulated: true` propagates to the UI, which marks the card so the
 * value is never mistaken for a real prediction.
 *
 * The regions are the patches the agent claims to have judged from. A real
 * implementation must return the same thing: a stage with no visible basis is
 * not reviewable, and the physician review step exists precisely to check
 * whether the model looked at the right place.
 */
const SAMPLE_PATCHES: Region[] = [
  {
    regionId: 'fib-patch-01',
    shape: 'box',
    points: [
      [0.35, 0.3],
      [0.45, 0.4],
    ],
    label: 'Capsule texture',
    confidence: 0.68,
    source: 'fibrosis',
  },
]

export const stubFibrosisAgent: AgentRunner<'fibrosis'> = {
  agentId: 'fibrosis',
  async run(_input, signal) {
    const started = performance.now()
    await delay(880, signal)

    const output: AgentOutput<'fibrosis'> = {
      agentId: 'fibrosis',
      value: 'F1',
      confidence: 0.7,
      regions: SAMPLE_PATCHES,
      rationale:
        'Capsule remains smooth with mildly coarsened periportal echotexture; no nodular surface or septal banding.',
      modelVersion: 'stub-fibrosis-0.1',
      inferenceMs: Math.round(performance.now() - started),
      simulated: true,
    }
    return output
  },
}
