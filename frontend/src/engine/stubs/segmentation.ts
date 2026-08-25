import type { Region, SegmentationRunner } from '../../domain'
import { LIVER_POLYGON } from '../../lib/geometry'
import { delay } from '../util'

/**
 * Stage 2b — liver segmentation (U-Net).
 *
 * ⚠️ STUB returning the sample study's outline. The U-Net itself is trained;
 * wiring is what's missing. When the endpoint lands, the only requirement is
 * that the mask arrives as a normalised POLYGON, not a bitmap — the overlay,
 * the report and the training payload all assume `Region.points`.
 *
 * If the model emits a raster mask, run marching-squares + simplification on
 * the backend and send the contour. Do not push bitmaps to the browser.
 */
export const stubSegmentation: SegmentationRunner = {
  async run(_intake, signal) {
    await delay(1080, signal)

    const capsule: Region = {
      regionId: 'seg-liver-01',
      shape: 'polygon',
      points: LIVER_POLYGON.map(([x, y]) => [x, y] as [number, number]),
      label: 'Liver',
      confidence: 0.94,
      source: 'segmentation',
    }

    return {
      regions: [capsule],
      areaCm2: 176.3,
      confidence: 0.94,
      modelVersion: 'stub-unet-0.1',
      simulated: true,
    }
  },
}
