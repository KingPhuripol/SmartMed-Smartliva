import type { Region, RegionSource } from '../../domain'
import type { RegionKeyEntry } from '../../lib/regionKey'
import { colorForSource } from '../../lib/regionKey'

interface RegionLayerProps {
  regions: Region[]
  /** Regions whose source is switched off are not drawn. */
  visibleSources: Set<RegionSource>
  highlightRegionId?: string | null
  /** Mask fill opacity for closed polygons, 0..1. */
  fillOpacity?: number
  /** Numbered findings from `buildRegionKey`; drawn as marker chips. */
  keyEntries?: RegionKeyEntry[]
  showMarkers?: boolean
}

function pointsToSvg(points: Array<[number, number]>): string {
  return points.map(([x, y]) => `${(x * 100).toFixed(3)},${(y * 100).toFixed(3)}`).join(' ')
}

/**
 * Draws every region in one SVG, colour-coded by which agent produced it.
 *
 * Uses a 0–100 viewBox with `preserveAspectRatio="none"` so normalised
 * coordinates map straight onto the image box, plus `non-scaling-stroke` so
 * outlines keep a constant weight regardless of how the image is scaled.
 *
 * Findings are marked with a number, never a sentence. Seven opaque captions
 * laid over the parenchyma hid the speckle the physician is here to read, so the
 * words moved to the key beneath the image and only the marker stays on tissue.
 */
export function RegionLayer({
  regions,
  visibleSources,
  highlightRegionId,
  fillOpacity = 0.28,
  keyEntries = [],
  showMarkers = true,
}: RegionLayerProps) {
  const shown = regions.filter((r) => visibleSources.has(r.source))

  return (
    <>
      <svg
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        className="pointer-events-none absolute inset-0 h-full w-full"
      >
        {shown.map((region) => {
          const color = colorForSource(region.source)
          const active = highlightRegionId === region.regionId
          const strokeWidth = active ? 3 : 1.75

          if (region.shape === 'point') {
            const [x, y] = region.points[0] ?? [0, 0]
            return (
              <g key={region.regionId}>
                <circle
                  cx={x * 100}
                  cy={y * 100}
                  r={1.2}
                  fill={color}
                  fillOpacity={0.9}
                  stroke="#0F172A"
                  strokeWidth={1}
                  vectorEffect="non-scaling-stroke"
                />
                <circle
                  cx={x * 100}
                  cy={y * 100}
                  r={3.2}
                  fill="none"
                  stroke={color}
                  strokeWidth={strokeWidth}
                  vectorEffect="non-scaling-stroke"
                />
              </g>
            )
          }

          if (region.shape === 'box') {
            const [[x1, y1], [x2, y2]] = [
              region.points[0] ?? [0, 0],
              region.points[1] ?? [0, 0],
            ]
            const x = Math.min(x1, x2) * 100
            const y = Math.min(y1, y2) * 100
            const w = Math.abs(x2 - x1) * 100
            const h = Math.abs(y2 - y1) * 100
            const armX = Math.min(w * 0.3, 3)
            const armY = Math.min(h * 0.3, 4)
            return (
              <g key={region.regionId}>
                <rect
                  x={x}
                  y={y}
                  width={w}
                  height={h}
                  fill={color}
                  fillOpacity={active ? 0.16 : 0.05}
                  stroke={color}
                  strokeOpacity={active ? 1 : 0.8}
                  strokeWidth={strokeWidth}
                  strokeDasharray="6 4"
                  vectorEffect="non-scaling-stroke"
                />
                <path
                  d={[
                    `M ${x} ${y + armY} L ${x} ${y} L ${x + armX} ${y}`,
                    `M ${x + w - armX} ${y} L ${x + w} ${y} L ${x + w} ${y + armY}`,
                    `M ${x + w} ${y + h - armY} L ${x + w} ${y + h} L ${x + w - armX} ${y + h}`,
                    `M ${x + armX} ${y + h} L ${x} ${y + h} L ${x} ${y + h - armY}`,
                  ].join(' ')}
                  fill="none"
                  stroke={color}
                  strokeWidth={active ? 4 : 2.75}
                  strokeLinecap="round"
                  vectorEffect="non-scaling-stroke"
                />
              </g>
            )
          }

          if (region.shape === 'polygon') {
            return (
              <g key={region.regionId}>
                <polygon
                  points={pointsToSvg(region.points)}
                  fill={color}
                  fillOpacity={fillOpacity}
                />
                <polygon
                  points={pointsToSvg(region.points)}
                  fill="none"
                  stroke={color}
                  strokeWidth={active ? 3 : 2}
                  strokeLinejoin="round"
                  vectorEffect="non-scaling-stroke"
                />
              </g>
            )
          }

          return (
            <polyline
              key={region.regionId}
              points={pointsToSvg(region.points)}
              fill="none"
              stroke={color}
              strokeWidth={active ? 4 : 2.5}
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeOpacity={0.9}
              vectorEffect="non-scaling-stroke"
            />
          )
        })}
      </svg>

      {showMarkers &&
        keyEntries
          .filter((entry) => visibleSources.has(entry.region.source))
          .map((entry) => {
            const active = highlightRegionId === entry.region.regionId
            const [x, y] = entry.anchor
            return (
              <div
                key={`marker-${entry.region.regionId}`}
                className="pointer-events-none absolute"
                style={{ left: `${x * 100}%`, top: `${y * 100}%` }}
              >
                <span
                  className={`tnum flex h-[19px] min-w-[19px] -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full px-1 text-[10.5px] leading-none font-bold text-on-accent transition-transform duration-150 ${
                    active ? 'scale-125' : ''
                  }`}
                  style={{
                    backgroundColor: entry.color,
                    // Dark ring first so the chip survives bright speckle, then a
                    // faint glow in the agent's own colour to tie it to the key.
                    boxShadow: `0 0 0 1.5px rgb(2 6 23 / 0.9), 0 0 ${
                      active ? '14px' : '8px'
                    } ${entry.color}66`,
                  }}
                >
                  {entry.marker}
                </span>
              </div>
            )
          })}
    </>
  )
}
