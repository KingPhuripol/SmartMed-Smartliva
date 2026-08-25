import { useEffect, useState } from 'react'

export interface EHRRecord {
  id: number
  hn: string
  docNo: string
  timestamp: string
  s_stage: string
  fibrosis_stage: string
  lesions_summary: string
  liver_fluke: string
  doctor_note: string
  caseTitle: string
  imageUrl?: string
}

interface HistoryModalProps {
  open: boolean
  onClose: () => void
  onSelectRecord?: (record: EHRRecord) => void
}

export function HistoryModal({ open, onClose, onSelectRecord }: HistoryModalProps) {
  const [records, setRecords] = useState<EHRRecord[]>([])

  const loadRecords = () => {
    try {
      const stored = localStorage.getItem('smartliva_ehr_records')
      if (stored) {
        setRecords(JSON.parse(stored))
      } else {
        setRecords([])
      }
    } catch {
      setRecords([])
    }
  }

  useEffect(() => {
    if (open) {
      loadRecords()
    }
  }, [open])

  const handleClear = () => {
    if (window.confirm('คุณต้องการลบประวัติการตรวจทั้งหมดในระบบใช่หรือไม่?')) {
      localStorage.removeItem('smartliva_ehr_records')
      setRecords([])
    }
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm animate-fade">
      <div className="bg-card border-line max-h-[85vh] w-full max-w-2xl overflow-hidden rounded-2xl border shadow-2xl flex flex-col">
        {/* Header */}
        <div className="border-line flex items-center justify-between border-b px-6 py-4 bg-sunken">
          <div className="flex items-center gap-2.5">
            <span className="text-xl">📋</span>
            <div>
              <h3 className="text-base font-semibold text-ink">ประวัติการตรวจและเวชระเบียน (Hospital EHR History)</h3>
              <p className="text-ink-muted text-xs">บันทึกผลการตรวจอัลตราซาวด์ตับทั้งหมดในระบบ ({records.length} รายการ)</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-ink-muted hover:text-ink hover:bg-line/40 h-8 w-8 rounded-full flex items-center justify-center transition"
          >
            ✕
          </button>
        </div>

        {/* Content List */}
        <div className="flex-1 overflow-y-auto p-6 space-y-3">
          {records.length === 0 ? (
            <div className="py-12 text-center text-ink-muted">
              <span className="text-4xl block mb-2 opacity-60">📁</span>
              <p className="text-sm font-medium">ยังไม่มีประวัติการตรวจบันทึกไว้ในระบบ</p>
              <p className="text-xs text-ink-muted/80 mt-1">เมื่อแพทย์ยืนยันผลตรวจและกดบันทึก ข้อมูลจะปรากฏที่นี่ทันที</p>
            </div>
          ) : (
            records.map((rec) => (
              <div
                key={rec.id}
                className="border-line bg-card hover:border-medical hover:shadow-md transition-all rounded-xl border p-4 flex items-center justify-between gap-4"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="bg-medical/10 text-medical font-mono font-semibold px-2 py-0.5 rounded text-xs">
                      {rec.hn}
                    </span>
                    <span className="text-ink-muted text-xs font-mono">{rec.timestamp}</span>
                  </div>
                  <h4 className="text-sm font-semibold text-ink mt-1 truncate">{rec.caseTitle}</h4>
                  <p className="text-xs text-ink-muted mt-0.5">
                    Steatosis: <span className="font-semibold text-ink">{rec.s_stage}</span> · Fibrosis:{' '}
                    <span className="font-semibold text-ink">{rec.fibrosis_stage}</span> · Fluke:{' '}
                    <span className="font-semibold text-ink">{rec.liver_fluke}</span>
                  </p>
                  {rec.doctor_note && (
                    <p className="text-xs text-ink-muted/90 mt-1 bg-sunken px-2.5 py-1 rounded truncate">
                      🩺 {rec.doctor_note}
                    </p>
                  )}
                </div>

                {onSelectRecord && (
                  <button
                    type="button"
                    onClick={() => {
                      onSelectRecord(rec)
                      onClose()
                    }}
                    className="bg-medical text-white hover:bg-medical/90 text-xs font-semibold px-3 py-2 rounded-lg shrink-0 transition"
                  >
                    ดูรายงาน
                  </button>
                )}
              </div>
            ))
          )}
        </div>

        {/* Footer */}
        <div className="border-line border-t px-6 py-3 bg-sunken flex items-center justify-between">
          <button
            type="button"
            onClick={handleClear}
            disabled={records.length === 0}
            className="text-alert-ink hover:underline text-xs font-medium disabled:opacity-40"
          >
            ลบประวัติทั้งหมด
          </button>
          <button
            type="button"
            onClick={onClose}
            className="border-line bg-card hover:bg-sunken text-ink text-xs font-semibold px-4 py-2 rounded-lg border transition"
          >
            ปิดหน้าต่าง
          </button>
        </div>
      </div>
    </div>
  )
}
