import type { Region, RegionSource } from '../domain'
import { AGENT_DISPLAY, PHYSICIAN_COLOR, SEGMENTATION_COLOR } from '../config/agentDisplay'

/** Colour a region is drawn in — decided solely by who produced it. */
export function colorForSource(source: RegionSource): string {
  if (source === 'segmentation') return SEGMENTATION_COLOR
  if (source === 'physician') return PHYSICIAN_COLOR
  return AGENT_DISPLAY[source]?.color ?? SEGMENTATION_COLOR
}

export interface RegionKeyEntry {
  region: Region
  /** `1..n` for model findings, ordered shallow to deep; `A..Z` for physician marks. */
  marker: string
  color: string
  /** Normalised 0..1 corner the marker chip is pinned to. */
  anchor: [number, number]
  /** Normalised 0..1 depth of the region's centre. */
  depth: number
}

/** Only shapes that name a specific finding get a marker; outlines and traces do not. */
const KEYABLE_SHAPES = new Set(['box', 'point'])

function bounds(region: Region) {
  const xs = region.points.map((p) => p[0])
  const ys = region.points.map((p) => p[1])
  return {
    x1: Math.min(...xs),
    y1: Math.min(...ys),
    x2: Math.max(...xs),
    y2: Math.max(...ys),
  }
}

/**
 * Numbers every finding on the image so the picture can carry marks instead of
 * sentences, and the words can live in one legible list beneath it.
 *
 * Two deliberate choices:
 *
 * - **Model findings are numbered by depth**, shallow first. Depth is clinical
 *   information in liver B-mode — near-field versus deep-field behaviour is what
 *   steatosis grading reads — so the ordering carries meaning rather than
 *   reflecting whichever agent happened to finish first.
 * - **Physician marks are lettered, not numbered.** What the AI produced and what
 *   the physician added stay distinguishable at a glance, and adding a mark never
 *   renumbers the agents' findings underneath it.
 */
export function buildRegionKey(regions: Region[]): RegionKeyEntry[] {
  const keyable = regions.filter(
    (r) => KEYABLE_SHAPES.has(r.shape) && r.regionId !== 'preview',
  )

  const entries: RegionKeyEntry[] = keyable
    .filter((r) => r.source !== 'physician')
    .map((region) => ({ region, b: bounds(region) }))
    .sort((a, b) => a.b.y1 + a.b.y2 - (b.b.y1 + b.b.y2))
    .map(({ region, b }, i) => ({
      region,
      marker: String(i + 1),
      color: colorForSource(region.source),
      anchor: [b.x1, b.y1] as [number, number],
      depth: (b.y1 + b.y2) / 2,
    }))

  keyable
    .filter((r) => r.source === 'physician')
    .forEach((region, i) => {
      const b = bounds(region)
      entries.push({
        region,
        marker: i < 26 ? String.fromCharCode(65 + i) : `#${i + 1}`,
        color: PHYSICIAN_COLOR,
        anchor: [b.x1, b.y1],
        depth: (b.y1 + b.y2) / 2,
      })
    })

  return entries
}
