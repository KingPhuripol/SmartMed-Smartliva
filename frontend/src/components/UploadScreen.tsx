import { useCallback, useRef, useState } from 'react'
import { QUALITY_CRITERIA } from '../config/quality'
import { SparkIcon, UploadIcon } from './ui/Icons'
import { CLINICAL_BENCHMARK_CASES, type ClinicalBenchmarkCase } from '../lib/clinicalCases'

interface UploadScreenProps {
  onSelectFile: (file: File) => void
  onUseSample: () => void
  onSelectBenchmarkCase?: (c: ClinicalBenchmarkCase) => void
  externalError?: string | null
}

const PIPELINE_SUMMARY = [
  {
    step: '1',
    title: 'ตรวจคุณภาพ (Quality Gate)',
    body: 'คัดกรองความสว่าง สัญญาณรบกวน และความละเอียดภาพอัลตราซาวด์',
  },
  {
    step: '2',
    title: 'ตรวจอวัยวะ (Organ Gate)',
    body: 'จำแนกโครงสร้างตับและสร้างขอบเขตตับ (Segmentation)',
  },
  {
    step: '3',
    title: '4 Specialists + Supervisor',
    body: 'ประเมินพังผืด · ไขมัน · ก้อนเนื้อ · พยาธิใบไม้ พร้อมตรวจทานความสอดคล้อง',
  },
]

export function UploadScreen({
  onSelectFile,
  onUseSample,
  onSelectBenchmarkCase,
  externalError,
}: UploadScreenProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)

  const accept = useCallback(
    (file: File | undefined) => {
      if (file) onSelectFile(file)
    },
    [onSelectFile],
  )

  return (
    <div className="relative flex flex-1 flex-col items-center justify-start overflow-y-auto px-4 py-6 sm:px-6 sm:py-8">
      <div className="animate-rise relative w-full max-w-[840px] flex flex-col items-center">
        {/* Header Branding */}
        <div className="mb-6 flex flex-col items-center text-center">
          <div className="mb-3 flex h-16 w-16 items-center justify-center rounded-2xl bg-emerald-50 border border-emerald-100 shadow-sm">
            <img
              src="/smartliva-mark.png"
              alt="SmartLiva"
              width={64}
              height={64}
              className="h-10 w-10 select-none drop-shadow"
            />
          </div>
          <h2 className="text-[26px] sm:text-[30px] font-bold tracking-tight text-ink">
            ระบบตรวจอัลตราซาวด์ตับอัจฉริยะ
          </h2>
          <p className="text-ink-muted mt-1.5 max-w-[34rem] text-[13.5px] sm:text-[14.5px] leading-relaxed">
            ระบบปัญญาประดิษฐ์ช่วยแพทย์ประเมินภาวะไขมันพอกตับ, ระดับพังผืดตับ (METAVIR), ตรวจหารอยโรค/ก้อนเนื้อ และความเสี่ยงพยาธิใบไม้ในตับ
          </p>
        </div>

        {externalError && (
          <div className="mb-4 w-full rounded-xl border border-red-200 bg-red-50 p-3.5 text-center text-sm font-medium text-red-700">
            ⚠️ {externalError}
          </div>
        )}

        {/* Upload Dropzone Box */}
        <div
          onDragOver={(e) => {
            e.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault()
            setDragging(false)
            accept(e.dataTransfer.files?.[0])
          }}
          className={`panel w-full rounded-2xl border-2 border-dashed p-6 sm:p-8 transition-all duration-200 shadow-sm ${
            dragging ? 'border-medical bg-emerald-50/60' : 'border-line bg-card hover:border-line-strong'
          }`}
        >
          <div className="flex flex-col items-center text-center">
            <div
              className={`mb-3.5 flex h-13 w-13 items-center justify-center rounded-2xl transition-colors duration-200 ${
                dragging ? 'bg-medical text-white' : 'bg-emerald-50 text-medical border border-emerald-100'
              }`}
            >
              <UploadIcon className="h-6 w-6" />
            </div>

            <p className="text-[16px] font-semibold text-ink">ลากภาพอัลตราซาวด์ B-mode มาวางที่นี่</p>
            <p className="tnum text-ink-muted mt-1 text-[12.5px]">
              ความละเอียดอย่างน้อย {QUALITY_CRITERIA.minWidth}×{QUALITY_CRITERIA.minHeight} px · PNG, JPEG, WebP, BMP
            </p>

            <div className="mt-5 flex w-full flex-col gap-3 sm:w-auto sm:flex-row">
              <button
                type="button"
                onClick={() => inputRef.current?.click()}
                className="bg-medical text-white shadow-md hover:bg-medical/90 h-10.5 rounded-xl px-6 text-[14px] font-semibold transition-all active:scale-[0.98] cursor-pointer"
              >
                เลือกไฟล์จากเครื่อง
              </button>
              <button
                type="button"
                onClick={onUseSample}
                className="border-line bg-sunken text-ink hover:bg-card hover:border-line-strong flex h-10.5 items-center justify-center gap-2 rounded-xl border px-5 text-[14px] font-medium transition-all active:scale-[0.98] cursor-pointer"
              >
                <SparkIcon className="h-4 w-4 text-amber-500" />
                ใช้ภาพจำลอง (Demo Scan)
              </button>
            </div>

            <input
              ref={inputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={(e) => {
                accept(e.target.files?.[0])
                e.target.value = ''
              }}
            />
          </div>

          {/* Clinical Benchmark Cases Gallery */}
          <div className="mt-7 border-t border-line pt-5">
            <div className="flex items-center justify-between mb-3 px-1">
              <p className="text-[11.5px] font-bold uppercase tracking-wider text-ink-muted flex items-center gap-1.5">
                <span>🔬</span>
                <span>เลือกทดสอบด้วย 8 เคสตรวจจริงจากคลินิก (Clinical Benchmarks)</span>
              </p>
              <span className="text-[11px] text-medical font-semibold hidden sm:inline">
                คลิกตรวจทันที ➔
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5">
              {CLINICAL_BENCHMARK_CASES.map((c) => (
                <button
                  key={c.id}
                  type="button"
                  onClick={() =>
                    onSelectBenchmarkCase ? onSelectBenchmarkCase(c) : onUseSample()
                  }
                  className="group flex flex-col justify-between rounded-xl border border-line bg-sunken p-3 text-left transition-all hover:border-medical hover:bg-card hover:shadow-md active:scale-[0.98] cursor-pointer"
                >
                  <div>
                    <span className="text-[13px] font-bold text-ink group-hover:text-medical block">
                      {c.shortTitle}
                    </span>
                    <span className="text-[11px] text-ink-muted block mt-0.5">
                      {c.subTitle}
                    </span>
                  </div>

                  <div className="mt-2.5 flex flex-wrap items-center gap-1 text-[10px] font-mono">
                    <span className="bg-emerald-100 text-emerald-800 font-semibold px-1.5 py-0.5 rounded">
                      {c.s_stage.stage}
                    </span>
                    <span className="bg-purple-100 text-purple-800 font-semibold px-1.5 py-0.5 rounded">
                      {c.fibrosis.stage}
                    </span>
                    {c.lesions.length > 0 ? (
                      <span className="bg-red-100 text-red-800 font-semibold px-1.5 py-0.5 rounded">
                        Lesion
                      </span>
                    ) : (
                      <span className="bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded">
                        No Lesion
                      </span>
                    )}
                  </div>
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* 3-Step Pipeline Summary */}
        <div className="mt-6 w-full grid grid-cols-1 gap-3 sm:grid-cols-3 pb-6">
          {PIPELINE_SUMMARY.map((item) => (
            <div
              key={item.step}
              className="panel rounded-xl p-3.5 bg-card border-line border flex items-start gap-3 shadow-2xs"
            >
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-emerald-50 text-medical text-xs font-bold font-mono border border-emerald-100">
                {item.step}
              </span>
              <div>
                <h4 className="text-xs font-semibold text-ink">{item.title}</h4>
                <p className="text-ink-muted text-[11.5px] mt-1 leading-snug">{item.body}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
