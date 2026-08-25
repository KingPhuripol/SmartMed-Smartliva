import type { PipelineProgress, StageId, StageStatus } from '../../domain'
import { STAGE_ORDER } from '../../domain'
import { STAGE_LABELS } from '../../config/stages'
import { CheckIcon, CloseIcon } from '../ui/Icons'

interface PipelineScreenProps {
  imageUrl: string
  imageName: string
  progress: PipelineProgress | null
  statuses: Partial<Record<StageId, StageStatus>>
}

/** The numbered marker, in the same language the upload screen introduces. */
const MARKER_STYLE: Record<StageStatus, string> = {
  pending: 'border-line-strong text-ink-muted bg-card',
  running: 'border-accent-ink bg-accent-tint text-accent-ink',
  passed: 'border-verified-ink bg-verified-ink text-white',
  skipped: 'border-line-strong bg-sunken text-ink-muted',
  rejected: 'border-alert-ink bg-alert-ink text-white',
  failed: 'border-alert-ink bg-alert-ink text-white',
}

/**
 * Live view of the pipeline while it runs.
 *
 * Every gate is listed, including the ones that get skipped, so it is always
 * visible which checks an image actually went through — that matters when the
 * study is reviewed later.
 *
 * It shares the review screen's skeleton on purpose: dark image column on the
 * left, light panel on the right. The image therefore stays exactly where it is
 * when the pipeline finishes and the panel swaps stages for findings — nothing
 * jumps, and the full width is used instead of a narrow block in the middle.
 */
export function PipelineScreen({
  imageUrl,
  imageName,
  progress,
  statuses,
}: PipelineScreenProps) {
  const percent = Math.round((progress?.overall ?? 0) * 100)
  const runningStage = STAGE_ORDER.find((id) => statuses[id] === 'running')

  return (
    <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
      <section
        data-surface="dark"
        className="bg-page text-ink relative flex min-h-[46vh] flex-1 flex-col lg:min-h-0"
      >
        <div className="flex shrink-0 items-center gap-3 px-5 pt-4">
          <h2 className="text-[13px] font-semibold tracking-[0.14em] uppercase">
            กำลังวิเคราะห์
          </h2>
          <span className="tnum text-ink-muted hidden truncate text-[11.5px] sm:inline">
            {imageName}
          </span>
          <span className="text-accent-ink animate-breathe ml-auto shrink-0 text-[11px] font-semibold tracking-[0.18em] uppercase">
            {runningStage ? STAGE_LABELS[runningStage].title : 'เริ่มต้น'}
          </span>
        </div>

        <div className="relative flex min-h-0 flex-1 items-center justify-center px-5 py-4">
          <div className="border-line relative max-h-full overflow-hidden rounded-lg border">
            <img
              src={imageUrl}
              alt={imageName}
              draggable={false}
              className="block max-h-[68vh] w-auto max-w-full object-contain lg:max-h-[72vh]"
            />
            <div className="animate-scan absolute inset-x-0 h-24 -translate-y-1/2">
              <div className="from-accent/0 via-accent/20 to-accent/0 h-full w-full bg-gradient-to-b" />
              <div className="bg-accent absolute inset-x-0 bottom-0 h-px" />
            </div>
          </div>
        </div>
      </section>

      <aside className="border-line flex min-h-0 flex-col border-t lg:w-[40%] lg:shrink-0 lg:border-t-0 lg:border-l">
        <div className="border-line shrink-0 border-b px-5 pt-4 pb-3.5">
          <div className="flex items-baseline justify-between gap-3">
            <h2 className="text-ink text-[13px] font-semibold tracking-[0.14em] uppercase">
              ขั้นตอนการวิเคราะห์
            </h2>
            <span className="tnum text-ink text-[13px] font-bold">{percent}%</span>
          </div>
          <div className="bg-sunken mt-2.5 h-1 w-full overflow-hidden rounded-full">
            <div
              className="bg-accent h-full rounded-full transition-[width] duration-300 ease-out"
              style={{ width: `${percent}%` }}
            />
          </div>
        </div>

        {/* The explanation appears only for the stage actually running: eight
            paragraphs is most of the height and none of it is read mid-run. */}
        <ol className="min-h-0 flex-1 space-y-1 overflow-y-auto px-5 py-4">
          {STAGE_ORDER.map((stageId, index) => {
            const status = statuses[stageId] ?? 'pending'
            const label = STAGE_LABELS[stageId]
            const active = status === 'running'
            const last = index === STAGE_ORDER.length - 1
            return (
              <li key={stageId} className="relative flex gap-3 py-1">
                {!last && (
                  <span
                    aria-hidden="true"
                    className="bg-line absolute top-[28px] bottom-[-4px] left-[13px] w-px"
                  />
                )}
                <span
                  className={`tnum relative z-10 flex h-[26px] w-[26px] shrink-0 items-center justify-center rounded-full border text-[12.5px] font-semibold transition-colors duration-300 ${MARKER_STYLE[status]}`}
                >
                  {status === 'passed' ? (
                    <CheckIcon className="h-3 w-3" />
                  ) : status === 'rejected' || status === 'failed' ? (
                    <CloseIcon className="h-3 w-3" />
                  ) : (
                    index + 1
                  )}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-baseline gap-2">
                    <span
                      className={`text-[14.5px] ${
                        active
                          ? 'text-ink font-semibold'
                          : status === 'passed'
                            ? 'text-ink font-medium'
                            : 'text-ink-muted'
                      }`}
                    >
                      {label.title}
                    </span>
                    {status === 'skipped' && (
                      <span className="text-ink-muted text-[12.5px]">ข้าม</span>
                    )}
                  </span>
                  {active && (
                    <span className="text-ink-muted mt-0.5 block text-[12.5px] leading-relaxed">
                      {label.detail}
                    </span>
                  )}
                </span>
              </li>
            )
          })}
        </ol>
      </aside>
    </div>
  )
}
