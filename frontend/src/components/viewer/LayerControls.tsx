import type { AgentId, RegionSource } from '../../domain'
import type { RegionKeyEntry } from '../../lib/regionKey'
import { AGENT_DISPLAY, PHYSICIAN_COLOR, SEGMENTATION_COLOR } from '../../config/agentDisplay'
import { RegionKey } from './RegionKey'

export type AnnotationTool = 'none' | 'point' | 'box'

interface LayerControlsProps {
  assessedAgents: AgentId[]
  visibleSources: Set<RegionSource>
  onToggleSource: (source: RegionSource) => void
  maskOpacity: number
  onMaskOpacityChange: (value: number) => void
  /** Only shown as a layer once the physician has actually marked something. */
  annotationCount: number
  /** One finding is in focus, so the layer switches do not apply. */
  isolated?: boolean
  keyEntries: RegionKeyEntry[]
  highlightRegionId: string | null
  onHighlight: (regionId: string | null) => void
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-3">
      <span className="text-ink-muted w-[54px] shrink-0 pt-[5px] text-[10px] font-medium tracking-[0.14em] uppercase">
        {label}
      </span>
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  )
}

function LayerChip({
  active,
  color,
  label,
  onClick,
}: {
  active: boolean
  color: string
  label: string
  onClick: () => void
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={active}
      onClick={onClick}
      className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11.5px] font-medium whitespace-nowrap transition ${
        active
          ? 'border-line-strong bg-sunken text-ink'
          : 'border-line text-ink-muted hover:text-ink'
      }`}
    >
      <span
        className="h-2.5 w-2.5 shrink-0 rounded-[3px] transition-opacity"
        style={{ backgroundColor: color, opacity: active ? 1 : 0.28 }}
      />
      {label}
    </button>
  )
}

/**
 * The floating panel under the image: the key naming every numbered finding,
 * which agents' regions are drawn, and how strong the liver mask is.
 *
 * It deliberately has no marking tools. A mark made here would carry no agent,
 * and a mark with no agent cannot be attributed to a model in the training
 * record — so every mark is made inside the correction of the agent it disputes.
 */
export function LayerControls({
  assessedAgents,
  visibleSources,
  onToggleSource,
  maskOpacity,
  onMaskOpacityChange,
  annotationCount,
  isolated = false,
  keyEntries,
  highlightRegionId,
  onHighlight,
}: LayerControlsProps) {
  const hasKey = keyEntries.some((entry) => visibleSources.has(entry.region.source))

  return (
    <div className="panel-float space-y-3 rounded-xl px-4 py-3.5">
      {hasKey && (
        <Row label="Findings">
          <RegionKey
            entries={keyEntries}
            visibleSources={visibleSources}
            highlightRegionId={highlightRegionId}
            onHighlight={onHighlight}
          />
        </Row>
      )}

      <Row label="Layers">
        <div
          className={`flex flex-wrap items-center gap-2 ${isolated ? 'pointer-events-none opacity-45' : ''}`}
          aria-disabled={isolated || undefined}
        >
          <LayerChip
            active={visibleSources.has('segmentation')}
            color={SEGMENTATION_COLOR}
            label="Liver"
            onClick={() => onToggleSource('segmentation')}
          />
          {assessedAgents.map((agentId) => (
            <LayerChip
              key={agentId}
              active={visibleSources.has(agentId)}
              color={AGENT_DISPLAY[agentId].color}
              label={AGENT_DISPLAY[agentId].label}
              onClick={() => onToggleSource(agentId)}
            />
          ))}
          {annotationCount > 0 && (
            <LayerChip
              active={visibleSources.has('physician')}
              color={PHYSICIAN_COLOR}
              label={`แพทย์ (${annotationCount})`}
              onClick={() => onToggleSource('physician')}
            />
          )}
        </div>
      </Row>

      <Row label="Mask">
        <div className="flex items-center gap-3">
          <input
            id="mask-opacity"
            aria-label="ความเข้มของ mask"
            type="range"
            min={0}
            max={100}
            value={Math.round(maskOpacity * 100)}
            onChange={(e) => onMaskOpacityChange(Number(e.target.value) / 100)}
            className="slider min-w-0 flex-1"
          />
          <span className="tnum text-ink w-10 shrink-0 text-right text-[12px]">
            {Math.round(maskOpacity * 100)}%
          </span>
        </div>
      </Row>
    </div>
  )
}
