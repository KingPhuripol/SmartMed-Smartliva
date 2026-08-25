import type {
  AgentId,
  FibrosisStage,
  FlukeResult,
  LesionFinding,
  LesionResult,
  SteatosisStage,
} from '../../domain'
import { FIBROSIS_STAGES, FLUKE_RESULTS, STEATOSIS_STAGES } from '../../domain'
import { LESION_CLASSES } from '../../config/lesionClasses'
import { FIBROSIS_NOTES, STEATOSIS_NOTES } from '../../lib/agentFormat'
import { PlusIcon, TrashIcon } from '../ui/Icons'

interface AgentValueEditorProps {
  agentId: AgentId
  value: unknown
  aiValue: unknown
  onChange: (value: unknown) => void
  accent: string
}

function StageGrid({
  options,
  notes,
  current,
  aiValue,
  onChange,
  accent,
  columns,
}: {
  options: readonly string[]
  notes: Record<string, string>
  current: string
  aiValue: string
  onChange: (value: string) => void
  accent: string
  columns: string
}) {
  return (
    <div className={`grid gap-1.5 ${columns}`} role="radiogroup">
      {options.map((option) => {
        const active = option === current
        return (
          <button
            key={option}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(option)}
            className={`relative rounded-lg border px-1 py-2.5 text-center transition-all ${
              active
                ? 'bg-sunken'
                : 'border-line hover:border-line-strong hover:bg-sunken'
            }`}
            style={active ? { borderColor: accent, boxShadow: `0 0 20px -10px ${accent}` } : undefined}
          >
            <span
              className="tnum block text-[14px] font-bold"
              style={{ color: active ? accent : 'var(--color-ink-muted)' }}
            >
              {option}
            </span>
            <span className="mt-0.5 block text-[10px] leading-tight text-ink-muted">
              {notes[option]}
            </span>
            {aiValue === option && (
              <span className="bg-card absolute -top-1.5 left-1/2 -translate-x-1/2 rounded-full border border-line-strong px-1.5 text-[8.5px] font-bold tracking-[0.1em] text-ink-muted uppercase">
                AI
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}

let manualFindingSeq = 0

/** Controls the physician uses to state the correct value for one agent. */
export function AgentValueEditor({
  agentId,
  value,
  aiValue,
  onChange,
  accent,
}: AgentValueEditorProps) {
  if (agentId === 'fibrosis') {
    return (
      <StageGrid
        options={FIBROSIS_STAGES}
        notes={FIBROSIS_NOTES}
        current={value as FibrosisStage}
        aiValue={aiValue as FibrosisStage}
        onChange={(v) => onChange(v as FibrosisStage)}
        accent={accent}
        columns="grid-cols-5"
      />
    )
  }

  if (agentId === 'steatosis') {
    return (
      <StageGrid
        options={STEATOSIS_STAGES}
        notes={STEATOSIS_NOTES}
        current={value as SteatosisStage}
        aiValue={aiValue as SteatosisStage}
        onChange={(v) => onChange(v as SteatosisStage)}
        accent={accent}
        columns="grid-cols-4"
      />
    )
  }

  if (agentId === 'fluke') {
    return (
      <div className="grid grid-cols-2 gap-2" role="radiogroup">
        {FLUKE_RESULTS.map((option) => {
          const active = option === (value as FlukeResult)
          return (
            <button
              key={option}
              type="button"
              role="radio"
              aria-checked={active}
              onClick={() => onChange(option)}
              className={`relative rounded-lg border px-3 py-2.5 text-left transition-all ${
                active ? 'bg-sunken' : 'border-line hover:border-line-strong'
              }`}
              style={
                active ? { borderColor: accent, boxShadow: `0 0 20px -10px ${accent}` } : undefined
              }
            >
              <span
                className="block text-[13.5px] font-semibold"
                style={{ color: active ? accent : 'var(--color-ink-muted)' }}
              >
                {option === 'Negative' ? 'ไม่พบ (Negative)' : 'พบ (Positive)'}
              </span>
              {aiValue === option && (
                <span className="bg-card absolute -top-1.5 right-2 rounded-full border border-line-strong px-1.5 text-[8.5px] font-bold tracking-[0.1em] text-ink-muted uppercase">
                  AI
                </span>
              )}
            </button>
          )
        })}
      </div>
    )
  }

  const result = (value as LesionResult) ?? { findings: [] }
  const update = (findings: LesionFinding[]) => onChange({ findings })

  return (
    <div className="space-y-2">
      {result.findings.length === 0 && (
        <p className="rounded-lg border border-dashed border-line px-3 py-2.5 text-center text-[12px] text-ink-muted">
          ไม่มีรอยโรค — จะรายงานว่าเนื้อตับไม่พบรอยโรคเฉพาะที่
        </p>
      )}

      {result.findings.map((finding) => (
        <div
          key={finding.findingId}
          className="flex items-center gap-2 rounded-lg border border-line bg-sunken p-2"
        >
          <select
            value={finding.label}
            onChange={(e) =>
              update(
                result.findings.map((f) =>
                  f.findingId === finding.findingId ? { ...f, label: e.target.value } : f,
                ),
              )
            }
            aria-label="ชนิดรอยโรค"
            className="min-w-0 flex-1 rounded-md border border-line bg-card px-2 py-1.5 text-[12.5px] text-ink outline-none"
          >
            {LESION_CLASSES.map((cls) => (
              <option key={cls} value={cls}>
                {cls}
              </option>
            ))}
          </select>

          <button
            type="button"
            onClick={() =>
              update(result.findings.filter((f) => f.findingId !== finding.findingId))
            }
            aria-label={`ลบ ${finding.label}`}
            className="text-alert-ink/80 hover:bg-alert/12 hover:text-alert-ink shrink-0 rounded-md p-1.5 transition"
          >
            <TrashIcon className="h-4 w-4" />
          </button>
        </div>
      ))}

      <button
        type="button"
        onClick={() => {
          manualFindingSeq += 1
          update([
            ...result.findings,
            {
              findingId: `phys-les-${manualFindingSeq}`,
              label: 'Cyst',
              confidence: 1,
              regionId: '',
            },
          ])
        }}
        className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-dashed border-line px-3 py-2 text-[12.5px] font-medium text-ink-muted transition hover:border-primary hover:text-ink"
      >
        <PlusIcon className="h-4 w-4" />
        เพิ่มรอยโรค
      </button>
    </div>
  )
}
