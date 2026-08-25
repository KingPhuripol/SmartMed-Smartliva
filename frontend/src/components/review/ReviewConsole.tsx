import type {
  AgentId,
  AgentOutput,
  PhysicianReview,
  Region,
  StudyRecord,
} from "../../domain";
import { AGENT_IDS, isVerdictSettled, pendingAgents } from "../../domain";
import type { AgentVerdict } from "../../domain";
import { AGENT_DISPLAY, PHYSICIAN_COLOR } from "../../config/agentDisplay";
import { formatAgentValue } from "../../lib/agentFormat";
import {
  suspectedOptionsFor,
  UNNAMED_MARK_LABELS,
} from "../../config/lesionClasses";
import { AgentCard } from "./AgentCard";
import type { AnnotationTool } from "../viewer/LayerControls";
import { ChevronIcon, DatabaseIcon, ReportIcon, TrashIcon } from "../ui/Icons";

interface ReviewConsoleProps {
  study: StudyRecord;
  review: PhysicianReview;
  onMarkCorrect: (agentId: AgentId) => void;
  onMarkIncorrect: (
    agentId: AgentId,
    correctedValue: unknown,
    reason: string,
  ) => void;
  onHoverRegion: (regionId: string | null) => void;
  onUpdateAnnotationNote: (regionId: string, note: string) => void;
  onUpdateAnnotationLabel: (regionId: string, label: string) => void;
  onRemoveAnnotation: (regionId: string) => void;
  onGenerateReport: () => void;
  onSubmitFeedback: () => void;
  submitted: boolean;
  /** The finding the physician has drilled into; null shows the overview. */
  focusedAgentId: AgentId | null;
  onFocusAgent: (agentId: AgentId | null) => void;
  markTool: AnnotationTool;
  /** Turn the mark tool on for the agent being corrected, or off with 'none'. */
  onRequestMark: (agentId: AgentId, tool: AnnotationTool) => void;
}

/**
 * Right pane — the physician's recheck of everything the pipeline produced.
 *
 * Two states. The overview answers "what did the AI find in this image at all".
 * Drilling into one finding narrows both panes at once: the card opens here, and
 * the image drops every other overlay so the physician is looking at exactly the
 * thing they are judging.
 *
 * The cross-agent supervisor is deliberately absent from both. It is a rule
 * engine, not the second opinion its name implies, and the engine still records
 * its read on the StudyRecord — it simply does not speak to the physician until
 * something real is behind it.
 */
export function ReviewConsole({
  study,
  review,
  onMarkCorrect,
  onMarkIncorrect,
  onHoverRegion,
  onUpdateAnnotationNote,
  onUpdateAnnotationLabel,
  onRemoveAnnotation,
  onGenerateReport,
  onSubmitFeedback,
  submitted,
  focusedAgentId,
  onFocusAgent,
  markTool,
  onRequestMark,
}: ReviewConsoleProps) {
  const assessed = AGENT_IDS.filter(
    (id) => study.agents[id] !== undefined,
  ) as AgentId[];
  const pending = pendingAgents(review, assessed);
  const done = assessed.length - pending.length;
  const progress = assessed.length === 0 ? 0 : (done / assessed.length) * 100;
  const ready = pending.length === 0 && assessed.length > 0;

  return (
    <aside className="border-line flex min-h-0 flex-col border-t lg:w-[40%] lg:shrink-0 lg:border-t-0 lg:border-l">
      <div className="no-print border-line shrink-0 border-b px-5 pt-4 pb-3.5">
        <h2 className="text-[13px] font-semibold tracking-[0.14em] text-ink uppercase">
          Physician Recheck
        </h2>
        <p className="mt-0.5 text-[11.5px] text-ink-muted">
          ตรวจผลของ agent ทีละตัว — ถ้าผิดต้องระบุเหตุผลเพื่อนำไปพัฒนาโมเดล
        </p>
        <div className="mt-3 flex items-center gap-2.5">
          <div className="h-1 flex-1 overflow-hidden rounded-full bg-sunken">
            <div
              className="bg-verified h-full rounded-full transition-[width] duration-500 ease-out"
              style={{ width: `${progress}%` }}
            />
          </div>
          <span className="tnum text-[11.5px] text-ink-muted">
            {done}/{assessed.length}
          </span>
        </div>
      </div>

      <div className="scroll-fade flex-1 space-y-3 px-5 py-4 lg:min-h-0 lg:overflow-y-auto">
        {focusedAgentId && study.agents[focusedAgentId] ? (
          <>
            <button
              type="button"
              onClick={() => onFocusAgent(null)}
              className="text-ink-muted hover:text-ink -ml-1 flex items-center gap-1 rounded-md px-1 py-1 text-[12.5px] font-medium transition"
            >
              <ChevronIcon className="h-4 w-4 rotate-90" />
              ภาพรวมทั้งภาพ
            </button>
            <AgentCard
              index={assessed.indexOf(focusedAgentId)}
              output={study.agents[focusedAgentId] as AgentOutput}
              verdict={review.verdicts[focusedAgentId]}
              assessment={undefined}
              onMarkCorrect={() => onMarkCorrect(focusedAgentId)}
              onMarkIncorrect={(value, reason) =>
                onMarkIncorrect(focusedAgentId, value, reason)
              }
              onHoverRegion={onHoverRegion}
              markTool={markTool}
              marks={review.annotations.filter(
                (a) => a.linkedAgentId === focusedAgentId,
              )}
              onRequestMark={(tool) => onRequestMark(focusedAgentId, tool)}
              onUpdateMarkLabel={onUpdateAnnotationLabel}
              onRemoveMark={onRemoveAnnotation}
              onUpdateMarkNote={onUpdateAnnotationNote}
              nextLabel={(() => {
                const next = assessed[assessed.indexOf(focusedAgentId) + 1];
                return next ? AGENT_DISPLAY[next].label : null;
              })()}
              onNext={() => {
                const next = assessed[assessed.indexOf(focusedAgentId) + 1];
                onFocusAgent(next ?? null);
              }}
            />
          </>
        ) : (
          <>
            <div className="panel overflow-hidden rounded-xl">
              <p className="border-line text-ink-muted border-b px-4 py-2.5 text-[10px] font-medium tracking-[0.14em] uppercase">
                สิ่งที่ AI วิเคราะห์ได้ ({assessed.length})
              </p>
              <ul>
                {assessed.map((agentId) => (
                  <FindingRow
                    key={agentId}
                    agentId={agentId}
                    output={study.agents[agentId] as AgentOutput}
                    verdict={review.verdicts[agentId]}
                    onOpen={() => onFocusAgent(agentId)}
                    onHoverRegion={onHoverRegion}
                  />
                ))}
              </ul>
            </div>

            <AnnotationList
              annotations={review.annotations}
              onUpdateNote={onUpdateAnnotationNote}
              onUpdateLabel={onUpdateAnnotationLabel}
              onRemove={onRemoveAnnotation}
              onHoverRegion={onHoverRegion}
            />

            <p className="text-ink-muted px-1 pt-1 pb-2 text-[11px] leading-relaxed">
              ผลของ AI ถูกบันทึกไว้แยกจากคำตัดสินของแพทย์เสมอ ทำให้ย้อนดูได้ว่า
              AI ตอบอะไร และแพทย์แก้เป็นอะไร
            </p>
          </>
        )}
      </div>

      <div className="bar-top no-print shrink-0 px-5 py-3.5">
        {!ready && (
          <p className="mb-2.5 text-[11.5px] text-ink-muted">
            เหลืออีก {pending.length} agent ที่ยังไม่ได้ตรวจ
          </p>
        )}
        <div className="flex flex-col gap-2 sm:flex-row">
          <button
            type="button"
            disabled={!ready}
            onClick={onGenerateReport}
            className={`flex flex-1 items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-[13.5px] font-semibold transition active:scale-[0.98] ${
              ready
                ? "bg-primary text-on-primary hover:bg-primary-hover shadow-btn"
                : "cursor-not-allowed bg-sunken text-ink-muted"
            }`}
          >
            <ReportIcon className="h-4 w-4" />
            ออกรายงาน
          </button>
          <button
            type="button"
            disabled={!ready}
            onClick={onSubmitFeedback}
            className={`flex items-center justify-center gap-2 rounded-lg border px-4 py-2.5 text-[13px] font-medium transition active:scale-[0.98] ${
              ready
                ? submitted
                  ? "border-verified/50 bg-verified/12 text-verified-ink"
                  : "border-line-strong text-ink hover:border-line-strong hover:bg-sunken"
                : "cursor-not-allowed border-line-strong text-ink-muted"
            }`}
          >
            <DatabaseIcon className="h-4 w-4" />
            {submitted ? "ส่งแล้ว" : "ส่งไปเทรนโมเดล"}
          </button>
        </div>
      </div>
    </aside>
  );
}

/**
 * One line of the overview: what this agent decided, and whether the physician
 * has settled it yet. Clicking opens the full card and narrows the image to this
 * finding alone.
 */
function FindingRow({
  agentId,
  output,
  verdict,
  onOpen,
  onHoverRegion,
}: {
  agentId: AgentId;
  output: AgentOutput;
  verdict: AgentVerdict | undefined;
  onOpen: () => void;
  onHoverRegion: (regionId: string | null) => void;
}) {
  const display = AGENT_DISPLAY[agentId];
  const settled = isVerdictSettled(verdict);
  const status = !settled
    ? { label: "ยังไม่ตรวจ", className: "text-ink-muted" }
    : verdict?.verdict === "correct"
      ? { label: "ยืนยันแล้ว", className: "text-verified-ink" }
      : { label: "แก้ไขแล้ว", className: "text-modified-ink" };

  return (
    <li className="border-line border-b last:border-b-0">
      <button
        type="button"
        onClick={onOpen}
        onPointerEnter={() =>
          onHoverRegion(output.regions[0]?.regionId ?? null)
        }
        onPointerLeave={() => onHoverRegion(null)}
        className="hover:bg-sunken flex w-full items-center gap-3 px-4 py-3 text-left transition"
      >
        <span
          className="h-2.5 w-2.5 shrink-0 rounded-[3px]"
          style={{ backgroundColor: display.color }}
        />
        <span className="min-w-0 flex-1">
          <span className="flex items-baseline gap-2">
            <span className="text-[13px] font-semibold text-ink">
              {display.label}
            </span>
            <span className="text-ink-muted truncate text-[11.5px]">
              {display.labelTh}
            </span>
          </span>
          <span className={`mt-0.5 block text-[11.5px] ${status.className}`}>
            {status.label}
            {output.simulated && " · ค่าจำลอง"}
          </span>
        </span>
        <span className="tnum shrink-0 text-right">
          <span className="block text-[14px] font-bold text-ink">
            {formatAgentValue(agentId, output.value)}
          </span>
          <span className="text-ink-muted block text-[11px]">
            {(output.confidence * 100).toFixed(0)}%
          </span>
        </span>
        <ChevronIcon className="text-ink-muted h-4 w-4 shrink-0 -rotate-90" />
      </button>
    </li>
  );
}

/** The wording a mark carries before it has been named. */
function defaultLabel(region: Region): string {
  return region.shape === "point" ? "จุดที่สงสัย" : "บริเวณที่สงสัย";
}

function AnnotationList({
  annotations,
  onUpdateNote,
  onUpdateLabel,
  onRemove,
  onHoverRegion,
}: {
  annotations: Region[];
  onUpdateNote: (regionId: string, note: string) => void;
  onUpdateLabel: (regionId: string, label: string) => void;
  onRemove: (regionId: string) => void;
  onHoverRegion: (regionId: string | null) => void;
}) {
  if (annotations.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-line px-4 py-3.5">
        <p className="text-[12px] font-medium text-ink-muted">
          จุดที่แพทย์สงสัย
        </p>
        <p className="mt-1 text-[11.5px] leading-relaxed text-ink-muted">
          ใช้เครื่องมือ “จุด” หรือ “กรอบ” บนภาพเพื่อทำเครื่องหมายบริเวณที่ AI
          มองข้าม — ข้อมูลนี้จะถูกส่งไปเทรนโมเดลด้วย
        </p>
      </div>
    );
  }

  return (
    <div className="panel rounded-xl p-4">
      <p className="mb-2.5 flex items-center gap-2 text-[12px] font-semibold text-ink">
        <span
          className="h-2.5 w-2.5 rounded-[3px]"
          style={{ backgroundColor: PHYSICIAN_COLOR }}
        />
        จุดที่แพทย์สงสัย ({annotations.length})
      </p>
      <ul className="space-y-2">
        {annotations.map((region) => (
          <li
            key={region.regionId}
            onMouseEnter={() => onHoverRegion(region.regionId)}
            onMouseLeave={() => onHoverRegion(null)}
            className="rounded-lg border border-line bg-sunken p-2.5"
          >
            <div className="mb-2 flex items-center gap-2">
              {/* Naming the suspicion is the point of the mark: an unnamed box
                  tells a retraining run only that the physician looked here. */}
              <select
                value={
                  UNNAMED_MARK_LABELS.has(region.label) ? "" : region.label
                }
                onChange={(e) =>
                  onUpdateLabel(
                    region.regionId,
                    e.target.value || defaultLabel(region),
                  )
                }
                aria-label="สงสัยว่าเป็นอะไร"
                className={`min-w-0 flex-1 rounded-md border px-2 py-1.5 text-[12px] outline-none transition focus:border-primary ${
                  UNNAMED_MARK_LABELS.has(region.label)
                    ? "border-line-strong bg-card text-ink-muted"
                    : "border-primary bg-card text-ink font-medium"
                }`}
              >
                <option value="">สงสัยว่าเป็น…</option>
                {suspectedOptionsFor(region.linkedAgentId).map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => onRemove(region.regionId)}
                aria-label="ลบเครื่องหมาย"
                className="text-alert-ink/80 hover:text-alert-ink shrink-0 rounded p-1 transition"
              >
                <TrashIcon className="h-3.5 w-3.5" />
              </button>
            </div>
            <input
              value={region.note ?? ""}
              onChange={(e) => onUpdateNote(region.regionId, e.target.value)}
              placeholder="ระบุสิ่งที่สงสัย เช่น สงสัยรอยโรคที่ AI ไม่ได้จับ"
              className="w-full rounded-md border border-line bg-sunken px-2.5 py-1.5 text-[12px] text-ink outline-none placeholder:text-ink-muted focus:border-primary"
            />
          </li>
        ))}
      </ul>
    </div>
  );
}
