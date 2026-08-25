import { useState } from 'react'
import type { SupervisorReview } from '../../domain'
import { RISK_COLOR, RISK_INK, RISK_LABEL } from '../../lib/agentFormat'
import { AlertIcon, ChevronIcon, SparkIcon } from '../ui/Icons'

interface SupervisorPanelProps {
  supervisor: SupervisorReview
}

/** Fills for the conflict box. Text inside it uses SEVERITY_INK instead. */
const SEVERITY_COLOR = {
  info: 'var(--color-ai)',
  warning: 'var(--color-modified)',
  critical: 'var(--color-alert)',
} as const

const SEVERITY_INK = {
  info: 'var(--color-ai-ink)',
  warning: 'var(--color-modified-ink)',
  critical: 'var(--color-alert-ink)',
} as const

/**
 * The supervisor's cross-agent view: overall risk, contradictions between
 * agents, and what it suggests doing next.
 *
 * Presented as a second opinion sitting above the agent cards, never merged
 * into them — the physician has to be able to see that the supervisor and an
 * agent disagree, which is impossible once one overwrites the other.
 */
export function SupervisorPanel({ supervisor }: SupervisorPanelProps) {
  const [open, setOpen] = useState(true)
  const risk = supervisor.overallRisk
  const color = RISK_COLOR[risk]
  const ink = RISK_INK[risk]

  return (
    <div className="panel overflow-hidden rounded-xl">
      <div
        className="flex items-center gap-3 px-4 py-3"
        style={{ background: `color-mix(in oklab, ${color} 9%, transparent)` }}
      >
        <span
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border"
          style={{
            borderColor: `color-mix(in oklab, ${color} 45%, transparent)`,
            backgroundColor: `color-mix(in oklab, ${color} 14%, transparent)`,
            color: ink,
          }}
        >
          <SparkIcon className="h-4.5 w-4.5" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[10px] font-semibold tracking-[0.14em] text-ink-muted uppercase">
            Supervisor · {supervisor.modelVersion}
          </p>
          <p className="text-[15px] font-bold" style={{ color: ink }}>
            {RISK_LABEL[risk].th}
            <span className="ml-2 text-[11.5px] font-normal text-ink-muted">
              {RISK_LABEL[risk].en}
            </span>
          </p>
        </div>
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          aria-label={open ? 'ย่อ' : 'ขยาย'}
          className="shrink-0 rounded-lg p-1.5 text-ink-muted transition hover:bg-sunken hover:text-ink"
        >
          <ChevronIcon className={`h-4 w-4 transition-transform ${open ? 'rotate-180' : ''}`} />
        </button>
      </div>

      {open && (
        <div className="space-y-3 border-t border-line px-4 py-3.5">
          <p className="text-[12.5px] leading-relaxed text-ink">
            {supervisor.impression}
          </p>

          {supervisor.conflicts.length > 0 && (
            <div className="space-y-2">
              <p className="text-[10px] font-semibold tracking-[0.14em] text-ink-muted uppercase">
                ข้อสังเกตข้าม agent ({supervisor.conflicts.length})
              </p>
              {supervisor.conflicts.map((conflict) => (
                <div
                  key={conflict.conflictId}
                  className="flex items-start gap-2 rounded-lg border px-2.5 py-2"
                  style={{
                    borderColor: `color-mix(in oklab, ${SEVERITY_COLOR[conflict.severity]} 38%, transparent)`,
                    backgroundColor: `color-mix(in oklab, ${SEVERITY_COLOR[conflict.severity]} 8%, transparent)`,
                  }}
                >
                  <span
                    className="mt-0.5 shrink-0"
                    style={{ color: SEVERITY_INK[conflict.severity] }}
                  >
                    <AlertIcon className="h-3.5 w-3.5" />
                  </span>
                  <div className="min-w-0">
                    <p className="text-[10px] font-semibold tracking-[0.1em] uppercase"
                      style={{ color: SEVERITY_INK[conflict.severity] }}
                    >
                      {conflict.agents.join(' × ')}
                    </p>
                    <p className="mt-0.5 text-[11.5px] leading-relaxed text-ink">
                      {conflict.description}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}

          {supervisor.recommendations.length > 0 && (
            <div>
              <p className="mb-1.5 text-[10px] font-semibold tracking-[0.14em] text-ink-muted uppercase">
                ข้อเสนอแนะ
              </p>
              <ul className="space-y-1">
                {supervisor.recommendations.map((rec) => (
                  <li
                    key={rec}
                    className="flex gap-2 text-[11.5px] leading-relaxed text-ink-muted"
                  >
                    <span className="text-ink-muted">—</span>
                    <span>{rec}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
