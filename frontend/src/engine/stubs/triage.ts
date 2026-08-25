import type { TriageRunner } from '../../domain'
import { delay } from '../util'

/**
 * Stage 3 — normal vs abnormal triage.
 *
 * ⚠️ STUB, and the one with no model behind it at all yet — training data for
 * "normal liver" has not been assembled.
 *
 * It currently answers `abnormal` every time. That is the deliberately safe
 * default: a false "normal" skips all four specialist agents, which is the most
 * dangerous failure this pipeline can have. Erring towards `abnormal` costs
 * compute; erring towards `normal` costs a missed finding.
 *
 * The physician can also force the agents to run regardless — see
 * `PipelineOptions.forceAgents`.
 */
export const stubTriage: TriageRunner = {
  async run(_intake, _segmentation, signal) {
    await delay(640, signal)

    return {
      classification: 'abnormal',
      confidence: 0.5,
      rationale:
        'ยังไม่มีโมเดลจำแนกตับปกติ ระบบจึงส่งต่อให้ agent ทุกตัวประเมินเสมอเพื่อความปลอดภัย',
      modelVersion: 'stub-triage-0.0',
      simulated: true,
    }
  },
}
