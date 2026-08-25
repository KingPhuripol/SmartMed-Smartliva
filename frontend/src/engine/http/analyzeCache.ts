import type { ImageIntake } from '../../domain'
import type { LiverUsAnalyzeOk } from './liverUsTypes'

/**
 * One /analyze call answers two pipeline stages.
 *
 * The pipeline asks the organ runner and then the segmentation runner as two
 * independent steps, but the service settles both in a single round trip.
 * Calling twice would not merely double the work — it could return two
 * different verdicts for one image, and the record would then contain an
 * outline produced under a decision the record does not hold.
 *
 * Exactly one response is ever resident. A second image evicts the first
 * rather than joining it, so no study can read another study's outline.
 */
interface Slot {
  imageId: string
  signal: AbortSignal | undefined
  promise: Promise<LiverUsAnalyzeOk>
}

let slot: Slot | null = null

export function analyzeOnce(
  intake: ImageIntake,
  signal: AbortSignal | undefined,
  start: () => Promise<LiverUsAnalyzeOk>,
): Promise<LiverUsAnalyzeOk> {
  // Both stages of one run receive the very same signal object, so identity is
  // what proves "same run" — an id alone would match a re-upload of the same
  // file and hand back a stale outline.
  if (slot && slot.imageId === intake.imageId && slot.signal === signal) {
    return slot.promise
  }
  const promise = start()
  // Held before the second consumer arrives, so a rejection is never unhandled.
  promise.catch(() => {})
  slot = { imageId: intake.imageId, signal, promise }
  return promise
}

/** Dropped once the second stage has read it; nothing outlives the run. */
export function releaseAnalyze(imageId: string): void {
  if (slot?.imageId === imageId) slot = null
}

export function clearAnalyzeCache(): void {
  slot = null
}
