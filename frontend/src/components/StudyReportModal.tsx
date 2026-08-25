import type { AgentId, AgentOutput, PhysicianReview, StudyRecord } from '../domain'
import { AGENT_IDS } from '../domain'
import { AGENT_DISPLAY } from '../config/agentDisplay'
import { STAGE_LABELS } from '../config/stages'
import { describeAgentValue, formatAgentValue, RISK_LABEL } from '../lib/agentFormat'
import { CloseIcon, PrintIcon } from './ui/Icons'

interface StudyReportModalProps {
  study: StudyRecord
  review: PhysicianReview
  onClose: () => void
}

/** Paper palette. Deliberately not the screen tokens: print needs more contrast. */
const PAPER = {
  ink: '#1A252F',
  navy: '#123B5D',
  rule: '#B6C2CE',
  ruleLight: '#DCE6EE',
  muted: '#5C6E7F',
  confirmed: '#15704F',
  corrected: '#B3152F',
  warn: '#8A5606',
  tint: '#F2F6F9',
} as const

/** Risk escalates green → amber → red, with critical held apart from high. */
const RISK_PAPER: Record<string, { color: string; tint: string }> = {
  low: { color: '#15704F', tint: '#E7F4EE' },
  moderate: { color: '#8A5606', tint: '#FCF3E3' },
  high: { color: '#B3152F', tint: '#FBEAED' },
  critical: { color: '#7F1020', tint: '#F6DDE2' },
}

function Section({
  no,
  title,
  children,
}: {
  no: number
  title: string
  children: React.ReactNode
}) {
  return (
    <section className="mt-5 break-inside-avoid">
      <h3
        className="flex items-baseline gap-2 border-b pb-1 text-[11px] font-bold tracking-[0.12em] uppercase"
        style={{ color: PAPER.navy, borderColor: PAPER.rule }}
      >
        <span className="tnum">{no}.</span>
        {title}
      </h3>
      <div className="mt-2.5">{children}</div>
    </section>
  )
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex gap-2 border-b py-1" style={{ borderColor: PAPER.ruleLight }}>
      <span className="w-[92px] shrink-0 text-[10px] font-semibold tracking-[0.06em] uppercase" style={{ color: PAPER.muted }}>
        {label}
      </span>
      <span className="min-w-0 flex-1 text-[12px] break-all">{value}</span>
    </div>
  )
}

/**
 * The report, rendered as a white sheet on screen and printed as-is.
 *
 * Laid out the way a radiology report is: identifiers, then how the study was
 * produced, then findings, then the impression, then what limits the impression,
 * then a signature. Numbered sections and ruled fields are what make a clinical
 * document readable out of order — a reader looking for one fact should not have
 * to read the prose to find it.
 *
 * It states both what the model said and what the physician concluded, plus
 * which parts no real model stands behind, because a reader months from now
 * cannot reconstruct any of that from the values alone.
 */
export function StudyReportModal({ study, review, onClose }: StudyReportModalProps) {
  const assessed = AGENT_IDS.filter((id) => study.agents[id]) as AgentId[]
  const issued = new Date()
  const simulated = assessed.filter((id) => study.agents[id]?.simulated)
  const corrections = assessed.filter((id) => review.verdicts[id]?.verdict === 'incorrect')
  const gate = study.organ?.service ?? null
  const notCalibrated = gate?.warnings.includes('SCANNER_NOT_CALIBRATED') ?? false

  return (
    <div className="print-root fixed inset-0 z-50 flex flex-col items-center overflow-y-auto bg-black/75 p-4 backdrop-blur-sm sm:p-8">
      <div className="no-print mb-3 flex w-full max-w-[820px] shrink-0 items-center gap-2">
        <h2 className="text-[13px] font-semibold tracking-[0.14em] text-slate-300 uppercase">
          รายงานผลการตรวจ
        </h2>
        <div className="ml-auto flex gap-2">
          <button
            type="button"
            onClick={() => window.print()}
            className="bg-medical hover:bg-ai-ink flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-[13px] font-semibold text-white transition active:scale-[0.98]"
          >
            <PrintIcon className="h-4 w-4" />
            พิมพ์ / บันทึก PDF
          </button>
          <button
            type="button"
            onClick={onClose}
            aria-label="ปิด"
            className="border-line-strong hover:bg-sunken rounded-lg border px-3 py-2 text-slate-300 transition"
          >
            <CloseIcon className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div
        className="print-sheet w-full max-w-[820px] rounded-lg bg-white px-8 py-8 shadow-2xl sm:px-11 sm:py-10"
        style={{ color: PAPER.ink }}
      >
        {/* ------------------------------------------------------ letterhead */}
        <header
          className="flex items-start justify-between gap-4 border-b-2 pb-3"
          style={{ borderColor: PAPER.navy }}
        >
          <div className="flex items-center gap-3">
            <img src="/smartliva-mark.png" alt="" width={128} height={128} className="h-12 w-12 shrink-0" />
            <div>
              <p className="text-[21px] leading-none font-bold tracking-tight">
                Smart<span style={{ color: PAPER.navy }}>Liva</span>
              </p>
              <p className="mt-1.5 text-[10.5px] tracking-[0.12em] uppercase" style={{ color: PAPER.muted }}>
                รายงานผลวิเคราะห์อัลตราซาวด์ตับด้วยระบบช่วยวิเคราะห์
              </p>
            </div>
          </div>
          <div className="shrink-0 text-right">
            <p className="text-[9.5px] font-bold tracking-[0.12em] uppercase" style={{ color: PAPER.muted }}>
              เลขที่รายงาน
            </p>
            <p className="tnum text-[14px] font-bold" style={{ color: PAPER.navy }}>
              {study.studyId}
            </p>
            <p className="tnum mt-0.5 text-[10px]" style={{ color: PAPER.muted }}>
              ออกรายงาน {issued.toLocaleString('th-TH')}
            </p>
          </div>
        </header>

        {/* ------------------------------------------------- 1 · identifiers */}
        <Section no={1} title="ข้อมูลการตรวจ">
          <div className="grid gap-x-8 sm:grid-cols-2">
            <Field label="ไฟล์ภาพ" value={study.intake.fileName} />
            <Field label="ความละเอียด" value={<span className="tnum">{study.intake.width}×{study.intake.height} px</span>} />
            <Field label="รับภาพเมื่อ" value={<span className="tnum">{new Date(study.intake.receivedAt).toLocaleString('th-TH')}</span>} />
            <Field label="คัดกรอง" value={study.triage?.classification === 'abnormal' ? 'ผิดปกติ' : 'ปกติ'} />
          </div>
        </Section>

        {/* ---------------------------------------------------- 2 · technique */}
        <Section no={2} title="วิธีการตรวจและที่มาของผล">
          <div className="grid gap-5 sm:grid-cols-[176px_1fr]">
            <figure>
              <img
                src={study.intake.source}
                alt={study.intake.fileName}
                className="w-full rounded border bg-black object-contain"
                style={{ borderColor: PAPER.rule }}
              />
              <figcaption className="mt-1.5 text-[9.5px]" style={{ color: PAPER.muted }}>
                ภาพที่ใช้วิเคราะห์
              </figcaption>
            </figure>
            <div>
              <div className="grid gap-x-8 sm:grid-cols-2">
                <Field
                  label="ขอบเขตตับ"
                  value={gate ? <span className="tnum">{gate.areaPctFrame.toFixed(1)}% ของเฟรม</span> : 'ไม่ได้วัด'}
                />
                <Field label="คุณภาพภาพ" value={gate ? gate.quality.status : '—'} />
                <Field label="โมเดลหาขอบตับ" value={gate ? <span className="tnum">LiverUS {gate.modelVersion}</span> : '—'} />
                <Field label="สัญญา API" value={gate ? <span className="tnum">{gate.apiVersion}</span> : '—'} />
              </div>
              <p className="mt-2 text-[10.5px] leading-relaxed" style={{ color: PAPER.muted }}>
                ด่านที่ภาพผ่าน:{' '}
                {study.stages
                  .filter((s) => s.status === 'passed' || s.status === 'skipped')
                  .map((s) => `${STAGE_LABELS[s.stageId].title}${s.status === 'skipped' ? ' (ข้าม)' : ''}`)
                  .join(' → ')}
              </p>
            </div>
          </div>
        </Section>

        {/* ----------------------------------------------------- 3 · findings */}
        <Section no={3} title="ผลการวิเคราะห์รายหัวข้อ">
          <table className="w-full border-collapse text-left">
            <thead>
              <tr style={{ backgroundColor: PAPER.tint }}>
                {['หัวข้อ', 'ผลจากระบบ', 'มั่นใจ', 'ผลที่แพทย์รับรอง', 'สถานะ'].map((h) => (
                  <th
                    key={h}
                    className="border px-2.5 py-1.5 text-[9.5px] font-bold tracking-[0.06em] uppercase"
                    style={{ borderColor: PAPER.rule, color: PAPER.navy }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {assessed.map((agentId) => {
                const output = study.agents[agentId] as AgentOutput
                const verdict = review.verdicts[agentId]
                const final = verdict?.correctedValue ?? output.value
                const corrected = verdict?.verdict === 'incorrect'
                const stateColor = corrected ? PAPER.corrected : PAPER.confirmed
                return (
                  <tr key={agentId}>
                    <td className="border px-2.5 py-2 text-[11.5px] font-medium" style={{ borderColor: PAPER.rule }}>
                      <span className="inline-flex items-center gap-1.5">
                        <span
                          className="h-2 w-2 shrink-0 rounded-[2px]"
                          style={{ backgroundColor: AGENT_DISPLAY[agentId].color }}
                        />
                        {AGENT_DISPLAY[agentId].labelTh}
                      </span>
                      {output.simulated && (
                        <span className="ml-1 text-[9.5px] font-semibold" style={{ color: PAPER.warn }}>
                          (ค่าจำลอง)
                        </span>
                      )}
                    </td>
                    <td className="tnum border px-2.5 py-2 text-[11.5px]" style={{ borderColor: PAPER.rule, color: PAPER.muted }}>
                      {formatAgentValue(agentId, output.value)}
                    </td>
                    <td className="tnum border px-2.5 py-2 text-[11.5px]" style={{ borderColor: PAPER.rule, color: PAPER.muted }}>
                      {(output.confidence * 100).toFixed(0)}%
                    </td>
                    <td className="tnum border px-2.5 py-2 text-[12px] font-bold" style={{ borderColor: PAPER.rule, color: stateColor }}>
                      {formatAgentValue(agentId, final)}
                    </td>
                    <td className="border px-2.5 py-2 text-[11px] font-semibold" style={{ borderColor: PAPER.rule, color: stateColor }}>
                      {corrected ? 'แพทย์แก้ไข' : 'แพทย์ยืนยัน'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>

          {corrections.length > 0 && (
            <div className="mt-2.5">
              <p className="text-[9.5px] font-bold tracking-[0.1em] uppercase" style={{ color: PAPER.muted }}>
                เหตุผลที่แพทย์แก้ไข
              </p>
              <ul className="mt-1 space-y-1">
                {corrections.map((id) => (
                  <li key={id} className="text-[11.5px] leading-relaxed">
                    <span className="font-bold" style={{ color: PAPER.corrected }}>
                      {AGENT_DISPLAY[id].labelTh}:
                    </span>{' '}
                    {review.verdicts[id]?.reason}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {review.annotations.length > 0 && (
            <div className="mt-2.5">
              <p className="text-[9.5px] font-bold tracking-[0.1em] uppercase" style={{ color: PAPER.muted }}>
                ตำแหน่งที่แพทย์ทำเครื่องหมาย ({review.annotations.length})
              </p>
              <ul className="mt-1 space-y-0.5">
                {review.annotations.map((region) => (
                  <li key={region.regionId} className="text-[11.5px] leading-relaxed">
                    <span style={{ color: PAPER.muted }}>
                      {region.shape === 'point' ? 'จุด' : 'บริเวณ'}
                      {region.linkedAgentId ? ` · ${AGENT_DISPLAY[region.linkedAgentId].labelTh}` : ''}
                      {' — '}
                    </span>
                    <span className="font-medium">{region.label}</span>
                    {region.note ? ` — ${region.note}` : ''}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Section>

        {/* --------------------------------------------------- 4 · impression */}
        <Section no={4} title="ความเห็นสรุป">
          {study.supervisor && (
            <p
              className="mb-2 inline-block rounded px-2 py-0.5 text-[12.5px] font-bold"
              style={{
                color: RISK_PAPER[study.supervisor.overallRisk]?.color ?? PAPER.ink,
                backgroundColor: RISK_PAPER[study.supervisor.overallRisk]?.tint,
              }}
            >
              {RISK_LABEL[study.supervisor.overallRisk].th}
            </p>
          )}
          <ul className="space-y-1.5">
            {assessed.map((agentId) => {
              const output = study.agents[agentId] as AgentOutput
              const verdict = review.verdicts[agentId]
              const final = verdict?.correctedValue ?? output.value
              const corrected = verdict?.verdict === 'incorrect'
              return (
                <li key={agentId} className="flex items-baseline gap-2 text-[12.5px]">
                  <span
                    className="mt-[5px] h-2 w-2 shrink-0 rounded-[2px]"
                    style={{ backgroundColor: AGENT_DISPLAY[agentId].color }}
                  />
                  <span className="min-w-0">
                    <span style={{ color: PAPER.muted }}>{AGENT_DISPLAY[agentId].labelTh}</span>{' '}
                    <span className="font-bold" style={{ color: corrected ? PAPER.corrected : PAPER.confirmed }}>
                      {formatAgentValue(agentId, final)}
                    </span>
                    {' — '}
                    {describeAgentValue(agentId, final)}
                    {corrected && (
                      <span className="ml-1 text-[10.5px] font-semibold" style={{ color: PAPER.corrected }}>
                        (แพทย์แก้ไข)
                      </span>
                    )}
                  </span>
                </li>
              )
            })}
          </ul>

          {study.supervisor && study.supervisor.recommendations.length > 0 && (
            <ul className="mt-2 space-y-0.5">
              {study.supervisor.recommendations.map((rec) => (
                <li key={rec} className="text-[11.5px] leading-relaxed" style={{ color: PAPER.muted }}>
                  — {rec}
                </li>
              ))}
            </ul>
          )}

          {review.finalNote && (
            <p className="mt-2 text-[12px] leading-relaxed">
              <span className="font-semibold">หมายเหตุแพทย์:</span> {review.finalNote}
            </p>
          )}
        </Section>

        {/* -------------------------------------------------- 5 · limitations */}
        <Section no={5} title="ข้อจำกัดของผลนี้">
          <ul className="space-y-1 text-[11.5px] leading-relaxed">
            {simulated.length > 0 && (
              <li style={{ color: PAPER.warn }}>
                <span className="font-bold">ค่าจำลอง —</span>{' '}
                {simulated.map((id) => AGENT_DISPLAY[id].labelTh).join(', ')}{' '}
                ยังไม่มีโมเดลจริงรองรับ ค่าที่แสดงเป็นค่าทดสอบระบบ ไม่ใช่ผลวิเคราะห์
              </li>
            )}
            {notCalibrated && (
              <li style={{ color: PAPER.warn }}>
                <span className="font-bold">เครื่องสแกนยังไม่ปรับจูน —</span>{' '}
                ภาพนี้มาจากเครื่องที่ยังไม่ผ่านการปรับจูนกับโมเดล
                ผลคัดกรองอวัยวะจึงใช้ตัดสินอัตโนมัติไม่ได้ ต้องให้แพทย์ยืนยันทุกครั้ง
              </li>
            )}
            <li style={{ color: PAPER.muted }}>
              ระบบรับภาพ PNG/JPEG/WebP/BMP ซึ่งไม่มีข้อมูลระยะต่อพิกเซล
              จึงไม่รายงานขนาดรอยโรคเป็นหน่วยความยาวจริง
            </li>
            <li style={{ color: PAPER.muted }}>
              SmartLiva เป็นซอฟต์แวร์ช่วยวิเคราะห์ ไม่ใช่เครื่องมือวินิจฉัย
              ทุกค่าในรายงานนี้ผ่านการยืนยันหรือแก้ไขโดยแพทย์ผู้ลงนาม
            </li>
          </ul>
        </Section>

        {/* ---------------------------------------------------- 6 · signature */}
        <Section no={6} title="การรับรองผล">
          <div className="grid gap-8 sm:grid-cols-2">
            <div>
              <div className="h-12 border-b" style={{ borderColor: PAPER.rule }} />
              <p className="mt-1.5 text-[10.5px]" style={{ color: PAPER.muted }}>
                ลายเซ็นแพทย์ผู้รายงาน
              </p>
            </div>
            <div>
              <div className="h-12 border-b" style={{ borderColor: PAPER.rule }} />
              <p className="mt-1.5 text-[10.5px]" style={{ color: PAPER.muted }}>
                ชื่อ–สกุล / เลขใบประกอบวิชาชีพ / วันที่
              </p>
            </div>
          </div>
        </Section>

        <footer
          className="tnum mt-6 flex flex-wrap items-center justify-between gap-2 border-t pt-2.5 text-[9.5px]"
          style={{ borderColor: PAPER.rule, color: PAPER.muted }}
        >
          <span>
            {study.studyId} · schema {study.schemaVersion}
            {gate ? ` · LiverUS ${gate.modelVersion}` : ''}
          </span>
          <span>ออกโดยระบบ SmartLiva · {issued.toLocaleDateString('th-TH')}</span>
        </footer>
      </div>

      <div className="no-print h-6 shrink-0" />
    </div>
  )
}
