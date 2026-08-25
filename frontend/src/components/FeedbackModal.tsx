import { useMemo, useState } from 'react'
import type { PhysicianReview, StudyRecord } from '../domain'
import { buildTrainingFeedback } from '../domain'
import { LIVER_US_SERVICE } from '../config/service'
import { CloseIcon, DatabaseIcon, DownloadIcon } from './ui/Icons'

interface FeedbackModalProps {
  study: StudyRecord
  review: PhysicianReview
  onClose: () => void
  onConfirm: () => void
}

/**
 * Preview and submit physician verified feedback directly to SQLite Data Flywheel.
 */
export function FeedbackModal({ study, review, onClose, onConfirm }: FeedbackModalProps) {
  const [submitting, setSubmitting] = useState(false)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  const payload = useMemo(
    () => buildTrainingFeedback(study, review, new Date().toISOString()),
    [study, review],
  )
  const json = useMemo(() => JSON.stringify(payload, null, 2), [payload])

  const corrected = payload.agents.filter((a) => a.verdict === 'incorrect').length
  const confirmed = payload.agents.length - corrected

  const handleSendToFlywheel = async () => {
    setSubmitting(true)
    setErrorMsg(null)
    try {
      const res = await fetch(`${LIVER_US_SERVICE.baseUrl}/api/feedback`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: json,
      })

      if (!res.ok) {
        throw new Error(`Server returned status ${res.status}`)
      }

      onConfirm()
    } catch (err) {
      setErrorMsg(`เกิดข้อผิดพลาดในการบันทึกข้อมูล: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setSubmitting(false)
    }
  }

  const download = () => {
    const blob = new Blob([json], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${study.studyId}-feedback.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm">
      <div className="panel flex max-h-[86vh] w-full max-w-2xl flex-col rounded-2xl">
        <header className="border-line flex shrink-0 items-center gap-3 border-b px-5 py-4">
          <span className="border-ai/30 bg-ai/10 text-ai flex h-9 w-9 items-center justify-center rounded-lg border">
            <DatabaseIcon className="h-4.5 w-4.5" />
          </span>
          <div className="min-w-0">
            <h2 className="text-[15px] font-semibold text-ink">ส่งข้อมูลเข้า Data Flywheel & คิวเทรนโมเดล</h2>
            <p className="text-[11.5px] text-ink-muted">
              บันทึกผล AI · คำตัดสินแพทย์ · Annotations · เหตุผล ลง SQLite Flywheel Database
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="ปิด"
            className="ml-auto shrink-0 rounded-lg border border-line p-2 text-ink-muted transition hover:border-line-strong hover:text-ink"
          >
            <CloseIcon className="h-4 w-4" />
          </button>
        </header>

        <div className="grid shrink-0 grid-cols-4 gap-2.5 px-5 py-4">
          {[
            { label: 'ยืนยัน', value: confirmed, tone: 'text-verified-ink' },
            { label: 'แก้ไข', value: corrected, tone: 'text-modified-ink' },
            {
              label: 'เครื่องหมาย',
              value: payload.physicianAnnotations.length,
              tone: 'text-ink',
            },
            { label: 'ขนาด', value: `${(json.length / 1024).toFixed(1)} KB`, tone: 'text-ai' },
          ].map((stat) => (
            <div
              key={stat.label}
              className="rounded-lg border border-line bg-sunken px-3 py-2.5"
            >
              <p className="text-[10px] font-medium tracking-[0.12em] text-ink-muted uppercase">
                {stat.label}
              </p>
              <p className={`tnum mt-1 text-[16px] font-bold ${stat.tone}`}>{stat.value}</p>
            </div>
          ))}
        </div>

        {errorMsg && (
          <div className="mx-5 mb-3 rounded-lg border border-danger/40 bg-danger/10 px-4 py-2.5 text-[12.5px] text-danger">
            {errorMsg}
          </div>
        )}

        <div className="min-h-0 flex-1 overflow-auto px-5">
          <pre className="tnum rounded-lg border border-line bg-sunken p-4 text-[11.5px] leading-relaxed whitespace-pre-wrap text-ink-muted">
            {json}
          </pre>
        </div>

        <footer className="border-line shrink-0 border-t px-5 py-4">
          <p className="mb-3 text-[11.5px] leading-relaxed text-ink-muted">
            ข้อมูลจะถูกจัดเก็บเข้าสู่ SQLite Flywheel Database ของ SmartLiva ทันที เพื่อใช้เป็นสัญญาณปรับปรุงโมเดลในรอบถัดไป
          </p>
          <div className="flex flex-col gap-2 sm:flex-row">
            <button
              type="button"
              onClick={handleSendToFlywheel}
              disabled={submitting}
              className="bg-primary text-on-primary hover:bg-primary-hover flex-1 rounded-lg px-4 py-2.5 text-[13.5px] font-semibold shadow-btn transition active:scale-[0.98] disabled:opacity-50"
            >
              {submitting ? 'กำลังบันทึกข้อมูล...' : 'ส่งเข้าคิวเทรน (Data Flywheel)'}
            </button>
            <button
              type="button"
              onClick={download}
              disabled={submitting}
              className="flex items-center justify-center gap-2 rounded-lg border border-line-strong px-4 py-2.5 text-[13px] font-medium text-ink transition hover:border-line-strong hover:bg-sunken"
            >
              <DownloadIcon className="h-4 w-4" />
              ดาวน์โหลด JSON
            </button>
          </div>
        </footer>
      </div>
    </div>
  )
}
