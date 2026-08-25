import type { AgentOutput, AgentRunner, Region } from '../../../domain'
import { delay } from '../../util'

/**
 * Agent 2 — hepatic steatosis stage (S0–S3).
 *
 * ⚠️ STUB. See `fibrosisAgent.ts` for the contract notes that apply to all four.
 */
const SAMPLE_PATCHES: Region[] = [
  {
    regionId: 'stea-patch-01',
    shape: 'box',
    points: [
      [0.4, 0.36],
      [0.56, 0.5],
    ],
    label: 'Near-field parenchyma',
    confidence: 0.87,
    source: 'steatosis',
  },
]

export const stubSteatosisAgent: AgentRunner<'steatosis'> = {
  agentId: 'steatosis',
  async run(_input, signal) {
    const started = performance.now()
    await delay(760, signal)

    const output: AgentOutput<'steatosis'> = {
      agentId: 'steatosis',
      value: 'S2',
      confidence: 0.85,
      regions: SAMPLE_PATCHES,
      rationale:
        'Parenchyma is diffusely hyperechoic relative to renal cortex with marked posterior beam attenuation; diaphragm still discernible.',
      modelVersion: 'stub-steatosis-0.1',
      inferenceMs: Math.round(performance.now() - started),
      simulated: true,
    }
    return output
  },
}
