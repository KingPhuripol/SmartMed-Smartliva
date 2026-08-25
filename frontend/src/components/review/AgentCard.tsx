import { useEffect, useState } from "react";
import type {
  AgentId,
  AgentOutput,
  AgentVerdict,
  Region,
  SupervisorAgentAssessment,
} from "../../domain";
import { AGENT_DISPLAY } from "../../config/agentDisplay";
import { describeAgentValue, formatAgentValue } from "../../lib/agentFormat";
import {
  AlertIcon,
  CheckIcon,
  ChevronIcon,
  CloseIcon,
  SparkIcon,
} from "../ui/Icons";
import { AgentValueEditor } from "./AgentValueEditor";
import type { AnnotationTool } from "../viewer/LayerControls";
import { PlusIcon, PencilIcon, TrashIcon } from "../ui/Icons";
import {
  OTHER_OPTION,
  suspectedOptionsFor,
  UNNAMED_MARK_LABELS,
} from "../../config/lesionClasses";

interface AgentCardProps {
  index: number;
  output: AgentOutput;
  verdict: AgentVerdict | undefined;
  assessment: SupervisorAgentAssessment | undefined;
  /** Which mark tool is armed, and the marks already tied to this correction. */
  markTool: AnnotationTool;
  marks: Region[];
  onRequestMark: (tool: AnnotationTool) => void;
  onUpdateMarkLabel: (regionId: string, label: string) => void;
  onRemoveMark: (regionId: string) => void;
  onUpdateMarkNote: (regionId: string, note: string) => void;
  /** Offered once this finding is settled, so the run keeps moving. */
  nextLabel: string | null;
  onNext: () => void;
  onMarkCorrect: () => void;
  onMarkIncorrect: (correctedValue: unknown, reason: string) => void;
  onHoverRegion: (regionId: string | null) => void;
}

const AGREEMENT_STYLE = {
  agree: { label: "สอดคล้อง", color: "var(--color-verified-ink)" },
  uncertain: { label: "ไม่แน่ใจ", color: "var(--color-modified-ink)" },
  disagree: { label: "ไม่เห็นด้วย", color: "var(--color-alert-ink)" },
} as const;

/**
 * One agent's answer and the physician's judgement of it.
 *
 * The physician reviews each agent separately — a single "looks right" over all
 * four would tell a retraining run nothing about which model failed. Marking an
 * agent incorrect requires a written reason; that free text is the most
 * valuable field in the record, because it is the only place a failure mode is
 * described in a clinician's own words.
 */
export function AgentCard({
  index,
  output,
  verdict,
  assessment,
  onMarkCorrect,
  onMarkIncorrect,
  onHoverRegion,
  markTool,
  marks,
  onRequestMark,
  onUpdateMarkLabel,
  onRemoveMark,
  onUpdateMarkNote,
  nextLabel,
  onNext,
}: AgentCardProps) {
  const display = AGENT_DISPLAY[output.agentId as AgentId];
  const settled = verdict && verdict.verdict !== "pending";
  const isIncorrect = verdict?.verdict === "incorrect";

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<unknown>(output.value);
  const [reason, setReason] = useState("");

  useEffect(() => {
    if (!editing) {
      setDraft(verdict?.correctedValue ?? output.value);
      setReason(verdict?.reason ?? "");
    }
  }, [editing, verdict, output.value]);

  const shownValue = verdict?.correctedValue ?? output.value;
  // A neutral frame. Which model this is already reads from the colour chip and
  // the name in the header; a coloured, glowing frame competed with the value
  // for attention without adding anything the header did not already say.

  const reasonMissing = isIncorrect && !(verdict?.reason ?? "").trim();

  return (
    <article
      className="panel animate-rise rounded-xl p-4"
      style={{ animationDelay: `${index * 70}ms` }}
      onMouseEnter={() => onHoverRegion(output.regions[0]?.regionId ?? null)}
      onMouseLeave={() => onHoverRegion(null)}
    >
      <header className="flex items-start gap-2.5">
        <span
          className="mt-1 h-3 w-3 shrink-0 rounded-[3px]"
          style={{ backgroundColor: display.color }}
        />
        <div className="min-w-0 flex-1">
          <h3 className="text-[14px] leading-tight font-semibold text-ink">
            {display.label}
          </h3>
          <p className="mt-0.5 text-[11.5px] text-ink-muted">
            {display.labelTh}
          </p>
        </div>

        {output.simulated && (
          <span className="border-modified/40 bg-modified/10 text-modified-ink flex shrink-0 items-center gap-1 rounded-full border px-2 py-1 text-[9.5px] font-bold tracking-[0.12em] uppercase">
            <AlertIcon className="h-3 w-3" />
            ค่าจำลอง
          </span>
        )}
      </header>

      {/* Value */}
      <div className="mt-3 flex items-end justify-between gap-3">
        <div className="min-w-0">
          <p
            className="tnum text-[19px] leading-tight font-bold tracking-tight"
            style={{ color: "var(--color-ink)" }}
          >
            {formatAgentValue(output.agentId, shownValue)}
          </p>
          <p className="mt-1 text-[11.5px] text-ink-muted">
            {describeAgentValue(output.agentId, shownValue)}
          </p>
        </div>
        <div className="shrink-0 text-right">
          <p className="text-[9.5px] font-medium tracking-[0.12em] text-ink-muted uppercase">
            confidence
          </p>
          <p className="tnum text-[15px] font-bold text-ink">
            {(output.confidence * 100).toFixed(0)}%
          </p>
        </div>
      </div>

      {/* Rationale + supervisor opinion */}
      <p
        className="mt-3 border-l-2 pl-2.5 text-[11.5px] leading-relaxed text-ink-muted"
        style={{
          borderColor: `color-mix(in oklab, ${display.color} 45%, transparent)`,
        }}
      >
        {output.rationale}
      </p>

      {assessment && (
        <div className="mt-2.5 flex items-start gap-2 rounded-lg border border-line bg-sunken px-2.5 py-2">
          <SparkIcon className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ink-muted" />
          <div className="min-w-0">
            <p
              className="text-[10px] font-semibold tracking-[0.12em] uppercase"
              style={{ color: AGREEMENT_STYLE[assessment.agreement].color }}
            >
              Supervisor · {AGREEMENT_STYLE[assessment.agreement].label}
            </p>
            <p className="mt-0.5 text-[11.5px] leading-relaxed text-ink-muted">
              {assessment.note}
            </p>
          </div>
        </div>
      )}

      {/* Physician verdict */}
      {editing ? (
        <div className="mt-3.5 border-t border-line pt-3.5">
          <p className="mb-2 text-[11px] font-medium tracking-[0.1em] text-ink-muted uppercase">
            ค่าที่ถูกต้อง
          </p>
          <AgentValueEditor
            agentId={output.agentId}
            value={draft}
            aiValue={output.value}
            onChange={setDraft}
            accent={display.color}
          />

          <div className="border-line mt-3 rounded-lg border p-2.5">
            <p className="text-ink-muted mb-2 text-[11px] font-medium tracking-[0.1em] uppercase">
              ชี้ตำแหน่งที่ผิดบนภาพ
              {marks.length > 0 && (
                <span className="tnum text-verified-ink ml-2 font-semibold">
                  มาร์กแล้ว {marks.length}
                </span>
              )}
            </p>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() =>
                  onRequestMark(markTool === "point" ? "none" : "point")
                }
                className={`flex flex-1 items-center justify-center gap-1.5 rounded-lg border px-3 py-1.5 text-[12.5px] font-medium transition ${
                  markTool === "point"
                    ? "border-primary bg-sunken text-ink"
                    : "border-line-strong text-ink-muted hover:text-ink"
                }`}
              >
                <PlusIcon className="h-3.5 w-3.5" />
                จิ้มจุด
              </button>
              <button
                type="button"
                onClick={() =>
                  onRequestMark(markTool === "box" ? "none" : "box")
                }
                className={`flex flex-1 items-center justify-center gap-1.5 rounded-lg border px-3 py-1.5 text-[12.5px] font-medium transition ${
                  markTool === "box"
                    ? "border-primary bg-sunken text-ink"
                    : "border-line-strong text-ink-muted hover:text-ink"
                }`}
              >
                <PencilIcon className="h-3.5 w-3.5" />
                วาดกรอบ
              </button>
            </div>
            {markTool !== "none" && (
              <p className="text-accent-ink mt-2 text-[11.5px]">
                กำลังรอให้ชี้บนภาพ —{" "}
                {markTool === "point"
                  ? "คลิกจุดที่ผิด"
                  : "ลากกรอบคลุมบริเวณที่ผิด"}
              </p>
            )}

            {marks.length > 0 && (
              <ul className="mt-2.5 space-y-1.5">
                {marks.map((mark) => (
                  <li key={mark.regionId} className="flex items-center gap-2">
                    <span className="tnum bg-ink text-card flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-full text-[10px] font-bold">
                      {mark.shape === "point" ? "·" : "□"}
                    </span>
                    <select
                      value={
                        UNNAMED_MARK_LABELS.has(mark.label) ? "" : mark.label
                      }
                      onChange={(e) =>
                        onUpdateMarkLabel(
                          mark.regionId,
                          e.target.value ||
                            (mark.shape === "point"
                              ? "จุดที่สงสัย"
                              : "บริเวณที่สงสัย"),
                        )
                      }
                      aria-label="สงสัยว่าเป็นอะไร"
                      className={`focus:border-primary min-w-0 flex-1 rounded-md border px-2 py-1 text-[12px] outline-none ${
                        UNNAMED_MARK_LABELS.has(mark.label)
                          ? "border-line-strong bg-card text-ink-muted"
                          : "border-primary bg-card text-ink font-medium"
                      }`}
                    >
                      <option value="">สงสัยว่าเป็น…</option>
                      {suspectedOptionsFor(output.agentId).map((option) => (
                        <option key={option} value={option}>
                          {option}
                        </option>
                      ))}
                    </select>
                    <button
                      type="button"
                      onClick={() => onRemoveMark(mark.regionId)}
                      aria-label="ลบเครื่องหมาย"
                      className="text-alert-ink/80 hover:text-alert-ink shrink-0 rounded p-1 transition"
                    >
                      <TrashIcon className="h-3.5 w-3.5" />
                    </button>
                  </li>
                ))}
              </ul>
            )}

            {marks.some((m) => m.label === OTHER_OPTION) && (
              <ul className="mt-1.5 space-y-1.5">
                {marks
                  .filter((m) => m.label === OTHER_OPTION)
                  .map((mark) => (
                    <li key={`${mark.regionId}-other`}>
                      <input
                        value={mark.note ?? ""}
                        onChange={(e) =>
                          onUpdateMarkNote(mark.regionId, e.target.value)
                        }
                        placeholder="ระบุว่าสงสัยอะไร"
                        aria-label="ระบุสิ่งที่สงสัย"
                        className={`focus:border-primary w-full rounded-md border px-2 py-1 text-[12px] outline-none ${
                          (mark.note ?? "").trim()
                            ? "border-primary bg-card text-ink"
                            : "border-alert bg-card text-ink placeholder:text-ink-muted"
                        }`}
                      />
                    </li>
                  ))}
              </ul>
            )}
          </div>

          <label className="mt-3 block">
            <span className="mb-1.5 block text-[11px] font-medium tracking-[0.1em] text-ink-muted uppercase">
              เหตุผลที่ AI ผิด <span className="text-alert-ink">*</span>
            </span>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={3}
              placeholder="เช่น บริเวณที่ agent ใช้ตัดสินเป็นเงาจากซี่โครง ไม่ใช่เนื้อตับ"
              className="w-full resize-none rounded-lg border border-line bg-sunken px-3 py-2 text-[12.5px] leading-relaxed text-ink outline-none placeholder:text-ink-muted focus:border-primary"
            />
          </label>

          <div className="mt-3 flex gap-2">
            <button
              type="button"
              disabled={!reason.trim()}
              onClick={() => {
                onMarkIncorrect(draft, reason.trim());
                setEditing(false);
                onRequestMark("none");
              }}
              className={`flex-1 rounded-lg px-3 py-2 text-[13px] font-semibold transition ${
                reason.trim()
                  ? "bg-modified text-on-accent hover:bg-modified active:scale-[0.98]"
                  : "cursor-not-allowed bg-sunken text-ink-muted"
              }`}
            >
              บันทึกการแก้ไข
            </button>
            <button
              type="button"
              onClick={() => setEditing(false)}
              className="rounded-lg border border-line px-3.5 py-2 text-[13px] font-medium text-ink-muted transition hover:text-ink"
            >
              ยกเลิก
            </button>
          </div>
          {!reason.trim() && (
            <p className="mt-2 text-[11px] text-ink-muted">
              ต้องระบุเหตุผลก่อนบันทึก — ข้อความนี้จะถูกใช้พัฒนาโมเดลรอบถัดไป
            </p>
          )}
        </div>
      ) : (
        <div className="mt-3.5 border-t border-line pt-3.5">
          {settled && (
            <div className="mb-2.5 flex items-start gap-2">
              <span
                className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full"
                style={{
                  backgroundColor: isIncorrect
                    ? "var(--color-modified)"
                    : "var(--color-verified)",
                }}
              >
                {isIncorrect ? (
                  <CloseIcon className="h-2.5 w-2.5 text-on-accent" />
                ) : (
                  <CheckIcon className="h-2.5 w-2.5 text-on-accent" />
                )}
              </span>
              <div className="min-w-0">
                <p className="text-[12px] font-semibold text-ink">
                  {isIncorrect
                    ? "แพทย์ระบุว่า AI ผิด"
                    : "แพทย์ยืนยันว่า AI ถูกต้อง"}
                </p>
                {isIncorrect && (
                  <>
                    <p className="tnum mt-0.5 text-[11.5px] text-ink-muted">
                      AI ตอบ {formatAgentValue(output.agentId, output.value)}
                    </p>
                    {verdict?.reason && (
                      <p className="mt-1 text-[11.5px] leading-relaxed text-ink-muted">
                        “{verdict.reason}”
                      </p>
                    )}
                  </>
                )}
              </div>
            </div>
          )}

          {reasonMissing && (
            <p className="text-alert-ink mb-2 text-[11.5px]">
              ยังไม่ได้ระบุเหตุผล — กรุณาแก้ไขก่อนออกรายงาน
            </p>
          )}

          <div className="flex gap-2">
            <button
              type="button"
              onClick={onMarkCorrect}
              className={`flex flex-1 items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-[13px] font-semibold transition active:scale-[0.98] ${
                verdict?.verdict === "correct"
                  ? "border-verified/50 bg-verified/12 text-verified-ink border"
                  : "bg-verified-ink text-on-primary hover:bg-verified"
              }`}
            >
              <CheckIcon className="h-4 w-4" />
              ถูกต้อง
            </button>
            <button
              type="button"
              onClick={() => setEditing(true)}
              className={`flex flex-1 items-center justify-center gap-1.5 rounded-lg border px-3 py-2 text-[13px] font-medium transition active:scale-[0.98] ${
                isIncorrect
                  ? "border-modified/50 bg-modified/12 text-modified-ink"
                  : "border-line-strong text-ink hover:border-line-strong hover:bg-sunken"
              }`}
            >
              <CloseIcon className="h-4 w-4" />
              ไม่ถูกต้อง
            </button>
          </div>

          {Boolean(settled) && nextLabel && (
            <button
              type="button"
              onClick={onNext}
              className="border-line-strong text-ink hover:bg-sunken mt-2 flex w-full items-center justify-center gap-1.5 rounded-lg border px-3 py-2 text-[13px] font-medium transition"
            >
              ถัดไป · {nextLabel}
              <ChevronIcon className="h-4 w-4 -rotate-90" />
            </button>
          )}
        </div>
      )}
    </article>
  );
}
