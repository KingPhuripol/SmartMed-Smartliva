import type { RegionSource } from '../../domain'
import type { RegionKeyEntry } from '../../lib/regionKey'

interface RegionKeyProps {
  entries: RegionKeyEntry[]
  /** Entries whose source is switched off are hidden, matching the image. */
  visibleSources: Set<RegionSource>
  highlightRegionId: string | null
  onHighlight: (regionId: string | null) => void
}

/**
 * The words that used to sit on the parenchyma.
 *
 * Ordered shallow to deep, matching the numbers on the image. No depth figure is
 * printed: without DICOM there is no true pixel spacing, so the sequence carries
 * the ordering without implying a measurement the system cannot make.
 */
export function RegionKey({
  entries,
  visibleSources,
  highlightRegionId,
  onHighlight,
}: RegionKeyProps) {
  const shown = entries.filter((entry) => visibleSources.has(entry.region.source))
  if (shown.length === 0) return null

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
      {shown.map((entry) => {
        const active = highlightRegionId === entry.region.regionId
        return (
          <button
            key={entry.region.regionId}
            type="button"
            onPointerEnter={() => onHighlight(entry.region.regionId)}
            onPointerLeave={() => onHighlight(null)}
            onFocus={() => onHighlight(entry.region.regionId)}
            onBlur={() => onHighlight(null)}
            className={`-mx-1 flex items-center gap-1.5 rounded-md px-1 py-0.5 text-[12px] whitespace-nowrap transition ${
              active ? 'bg-sunken text-ink' : 'text-ink-muted hover:text-ink'
            }`}
          >
            <span
              className="tnum flex h-[15px] min-w-[15px] items-center justify-center rounded-full px-[3px] text-[9.5px] leading-none font-bold text-on-accent"
              style={{ backgroundColor: entry.color, opacity: active ? 1 : 0.85 }}
            >
              {entry.marker}
            </span>
            {entry.region.label}
            {entry.region.confidence !== null && (
              <span className="tnum text-[10.5px] text-ink-muted">
                {(entry.region.confidence * 100).toFixed(0)}%
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}
