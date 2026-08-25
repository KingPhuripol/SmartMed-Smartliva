import type { OrganCheckRunner } from '../../domain'
import { delay, now } from '../util'

/**
 * Stage 2a — "is this a liver ultrasound?"
 *
 * ⚠️ STUB. A trained classifier for this exists on the ML side but is not yet
 * exposed over HTTP. Replace the body with a call to that endpoint; the
 * signature and the `OrganCheck` shape do not change.
 *
 * Until then `simulated: true` travels with the result all the way to the UI,
 * which labels the stage accordingly — no stubbed number is ever presented as a
 * real model output.
 */
export const stubOrganCheck: OrganCheckRunner = {
  async run(intake, signal) {
    await delay(520, signal)

    // Crude stand-in so an obviously wrong upload still gets rejected in demos:
    // real ultrasound frames are wider than they are tall and predominantly grey.
    const aspect = intake.height === 0 ? 0 : intake.width / intake.height
    const plausible = aspect >= 0.8 && aspect <= 2.0

    return {
      isLiverUltrasound: plausible,
      confidence: plausible ? 0.96 : 0.22,
      // A stub has no service behind it; the field stays empty rather than
      // fabricating a gate report the record would then treat as evidence.
      service: null,
      modelVersion: 'stub-organ-0.1',
      simulated: true,
      checkedAt: now(),
    }
  },
}
