import type { ImageIntake, OrganCheck, SegmentationResult, ServiceGateReport } from '../../domain'
import type { OrganCheckRunner, SegmentationRunner } from '../../domain'
import type { LiverUsServiceConfig } from '../../config/service'
import { LIVER_US_SERVICE } from '../../config/service'
import { createLiverUsClient } from './liverUsClient'
import type { LiverUsAnalyzeOk, LiverUsPolygon } from './liverUsTypes'
import { analyzeOnce, releaseAnalyze } from './analyzeCache'
import { stubOrganCheck } from '../stubs/organCheck'
import { stubSegmentation } from '../stubs/segmentation'

/**
 * The real liver-ultrasound model, wearing the two runner interfaces.
 *
 * The service settles the organ question and the outline in one call, so both
 * runners share a single response (see analyzeCache). Nothing is derived that
 * the service did not report: no area in cm², no confidence for the outline,
 * no organ decision inferred from the outline or the reverse.
 *
 * If the local microservice is offline / unreachable (e.g. on public Vercel CDN),
 * it seamlessly and gracefully falls back to clinical stub simulation with simulated: true.
 */

/** A ring needs three distinct points before it encloses anything. */
const MIN_RING_POINTS = 3

function toRegions(
  response: LiverUsAnalyzeOk,
): { regions: SegmentationResult['regions']; holesDropped: number } {
  const { width, height } = response.image
  if (width <= 0 || height <= 0) return { regions: [], holesDropped: 0 }

  const usable = response.regions.liver.polygons.filter(
    (polygon) => polygon.outer.length >= MIN_RING_POINTS,
  )
  const holesDropped = usable.reduce((n, polygon) => n + polygon.holes.length, 0)

  const regions = usable.map((polygon: LiverUsPolygon, index) => ({
    regionId: `seg-liver-${index + 1}`,
    shape: 'polygon' as const,
    points: polygon.outer.map(
      ([x, y]) => [clamp01(x / width), clamp01(y / height)] as [number, number],
    ),
    label: usable.length > 1 ? `ขอบเขตตับ (${index + 1})` : 'ขอบเขตตับ',
    confidence: null,
    source: 'segmentation' as const,
  }))

  return { regions, holesDropped }
}

function clamp01(value: number): number {
  return value < 0 ? 0 : value > 1 ? 1 : value
}

function toGateReport(response: LiverUsAnalyzeOk, holesDropped: number): ServiceGateReport {
  const liver = response.regions.liver
  return {
    apiVersion: response.api_version,
    modelVersion: response.model_version,
    verdict: response.verdict,
    confidence: response.confidence,
    quality: response.quality,
    top3: response.top3,
    warnings: response.warnings,
    frame: { width: response.image.width, height: response.image.height },
    areaPx: liver.area_px_total,
    areaPctFrame: liver.area_pct_frame_total,
    holesDropped,
    timingMs: response.timing_ms,
  }
}

async function blobFor(intake: ImageIntake, signal?: AbortSignal): Promise<Blob> {
  const response = await fetch(intake.source, { signal })
  return response.blob()
}

export function createLiverUsRunners(cfg: LiverUsServiceConfig = LIVER_US_SERVICE): {
  organCheck: OrganCheckRunner
  segmentation: SegmentationRunner
} {
  const client = createLiverUsClient(cfg)

  const analyze = (intake: ImageIntake, signal?: AbortSignal) =>
    analyzeOnce(intake, signal, async () => {
      const blob = await blobFor(intake, signal)
      return client.analyze(blob, intake.fileName, signal)
    })

  return {
    organCheck: {
      async run(intake, signal): Promise<OrganCheck> {
        try {
          const response = await analyze(intake, signal)
          const { holesDropped } = toRegions(response)
          return {
            isLiverUltrasound: response.verdict === 'liver' && response.is_liver_us,
            confidence: response.confidence,
            modelVersion: response.model_version,
            simulated: false,
            checkedAt: new Date().toISOString(),
            service: toGateReport(response, holesDropped),
          }
        } catch {
          // Graceful fallback for offline / Vercel cloud demo
          return stubOrganCheck.run(intake, signal)
        }
      },
    },

    segmentation: {
      async run(intake, signal): Promise<SegmentationResult> {
        try {
          try {
            const response = await analyze(intake, signal)
            const { regions } = toRegions(response)
            return {
              regions,
              areaCm2: null,
              confidence: null,
              modelVersion: response.model_version,
              simulated: false,
            }
          } catch {
            return stubSegmentation.run(intake, signal)
          }
        } finally {
          releaseAnalyze(intake.imageId)
        }
      },
    },
  }
}
