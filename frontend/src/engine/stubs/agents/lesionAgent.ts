import type { AgentOutput, AgentRunner, LesionFinding, Region } from '../../../domain'
import { CYST, NODULE } from '../../../lib/demoScan'
import { delay } from '../../util'

/**
 * Agent 3 — focal lesion detection and classification.
 *
 * ⚠️ STUB, positioned to match the synthetic sample study.
 *
 * The only agent whose regions are the finding itself rather than the evidence
 * for a judgement, so `LesionFinding.regionId` links each finding to its
 * outline. Keep that link when the real detector lands — the review UI resolves
 * findings to boxes through it.
 *
 * Detections below the display threshold are still returned; filtering is a
 * viewing decision made in the UI, not something the detector should bake in.
 */
function boxAround(cx: number, cy: number, r: number): Array<[number, number]> {
  // Radius is given in x-normalised units; convert for y using the 4:3 sample frame.
  const ry = r * 1.35
  return [
    [cx - r, cy - ry],
    [cx + r, cy + ry],
  ]
}

const REGIONS: Region[] = [
  {
    regionId: 'les-region-01',
    shape: 'box',
    points: boxAround(CYST.cx, CYST.cy, CYST.r),
    label: 'Cyst',
    confidence: 0.92,
    source: 'lesion',
  },
  {
    regionId: 'les-region-02',
    shape: 'box',
    points: boxAround(NODULE.cx, NODULE.cy, NODULE.r),
    label: 'Hemangioma',
    confidence: 0.41,
    source: 'lesion',
  },
]

const FINDINGS: LesionFinding[] = [
  {
    findingId: 'les-01',
    label: 'Cyst',
    confidence: 0.92,
    regionId: 'les-region-01',
  },
  {
    findingId: 'les-02',
    label: 'Hemangioma',
    confidence: 0.41,
    regionId: 'les-region-02',
  },
]

export const stubLesionAgent: AgentRunner<'lesion'> = {
  agentId: 'lesion',
  async run(_input, signal) {
    const started = performance.now()
    await delay(940, signal)

    const output: AgentOutput<'lesion'> = {
      agentId: 'lesion',
      value: { findings: FINDINGS },
      confidence: 0.92,
      regions: REGIONS,
      rationale:
        'One well-defined anechoic lesion with posterior acoustic enhancement (simple cyst); a second lower-confidence hyperechoic nodule in the left field.',
      modelVersion: 'stub-lesion-0.1',
      inferenceMs: Math.round(performance.now() - started),
      simulated: true,
    }
    return output
  },
}
