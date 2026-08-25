import type { StudyRecord } from '../../domain'
import {
  HALT_MESSAGES,
  QUALITY_REJECT_MESSAGES,
  QUALITY_WARNING_MESSAGES,
} from '../../config/messages'
import { AlertIcon, RestartIcon, UploadIcon } from '../ui/Icons'

interface RejectScreenProps {
  study: StudyRecord
  onRetry: () => void
}

/**
 * Shown when the pipeline stops at a gate.
 *
 * States what failed, what the requirement was and what was actually measured —
 * "image rejected" without those numbers just gets the same file uploaded again.
 */
export function RejectScreen({ study, onRetry }: RejectScreenProps) {
  const halt = study.halt
  const quality = study.quality
  if (!halt) return null

  const message = HALT_MESSAGES[halt.reason]

  return (
    <div className="relative flex flex-1 items-center justify-center overflow-y-auto px-6 py-10">
      <div
        className="pointer-events-none absolute inset-0 opacity-60"
        style={{
          background:
            'radial-gradient(620px 340px at 50% 10%, color-mix(in oklab, var(--color-alert) 12%, transparent), transparent 70%)',
        }}
      />

      <div className="animate-rise relative w-full max-w-xl">
        <div className="panel rounded-2xl p-7 sm:p-9">
          <div className="flex items-start gap-4">
            <span className="border-alert/45 bg-alert/12 text-alert-ink flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border">
              <AlertIcon className="h-6 w-6" />
            </span>
            <div className="min-w-0">
              <h2 className="text-[19px] font-semibold text-ink">{message.th}</h2>
              <p className="mt-1 text-[12.5px] text-ink-muted">{message.en}</p>
            </div>
          </div>

          {halt.reason === 'QUALITY_REJECTED' && quality && (
            <div className="mt-6 space-y-4">
              <ul className="space-y-2">
                {quality.rejections.map((code) => (
                  <li
                    key={code}
                    className="border-alert/30 bg-alert/8 rounded-lg border px-3 py-2.5"
                  >
                    <p className="text-[12.5px] leading-relaxed text-ink">
                      {QUALITY_REJECT_MESSAGES[code].th}
                    </p>
                    <p className="tnum mt-0.5 text-[10.5px] text-ink-muted">{code}</p>
                  </li>
                ))}
              </ul>

              <div className="rounded-lg border border-line bg-sunken p-3.5">
                <p className="mb-2 text-[10px] font-semibold tracking-[0.14em] text-ink-muted uppercase">
                  เกณฑ์ที่ใช้ · ค่าที่วัดได้
                </p>
                <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-[12px]">
                  <Row
                    label="ความละเอียด"
                    required={`≥ ${quality.criteria.minWidth}×${quality.criteria.minHeight}`}
                    actual={`${quality.measured.width}×${quality.measured.height}`}
                    ok={
                      quality.measured.width >= quality.criteria.minWidth &&
                      quality.measured.height >= quality.criteria.minHeight
                    }
                  />
                  <Row
                    label="สัดส่วนภาพ"
                    required={`${quality.criteria.minAspectRatio}–${quality.criteria.maxAspectRatio}`}
                    actual={quality.measured.aspectRatio.toFixed(2)}
                    ok={
                      quality.measured.aspectRatio >= quality.criteria.minAspectRatio &&
                      quality.measured.aspectRatio <= quality.criteria.maxAspectRatio
                    }
                  />
                  <Row
                    label="ขนาดไฟล์"
                    required={`≤ ${(quality.criteria.maxByteSize / 1024 / 1024).toFixed(0)} MB`}
                    actual={`${(quality.measured.byteSize / 1024 / 1024).toFixed(2)} MB`}
                    ok={quality.measured.byteSize <= quality.criteria.maxByteSize}
                  />
                  <Row
                    label="รูปแบบไฟล์"
                    required={quality.criteria.acceptedMimeTypes
                      .map((t) => t.replace('image/', ''))
                      .join(' · ')}
                    actual={quality.measured.mimeType.replace('image/', '') || 'unknown'}
                    ok={quality.criteria.acceptedMimeTypes.includes(quality.measured.mimeType)}
                  />
                </dl>
              </div>

              {quality.warnings.length > 0 && (
                <ul className="space-y-1.5">
                  {quality.warnings.map((code) => (
                    <li key={code} className="text-modified-ink text-[11.5px]">
                      {QUALITY_WARNING_MESSAGES[code].th}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {halt.reason === 'NOT_LIVER_ULTRASOUND' && (
            <div className="mt-6 rounded-lg border border-line bg-sunken p-3.5">
              <p className="text-[12.5px] leading-relaxed text-ink">
                ระบบไม่พบลักษณะของอัลตราซาวด์ตับในภาพนี้
                {study.organ?.confidence !== null && study.organ !== null && (
                  <span className="tnum text-ink-muted">
                    {' '}
                    (ความมั่นใจ {(study.organ.confidence * 100).toFixed(0)}%)
                  </span>
                )}
              </p>
              <p className="mt-1.5 text-[11.5px] text-ink-muted">
                กรุณาอัปโหลดภาพ B-mode ของตับที่เห็นเนื้อตับชัดเจน
              </p>
            </div>
          )}

          <div className="mt-7 flex flex-col gap-2 sm:flex-row">
            <button
              type="button"
              onClick={onRetry}
              className="bg-primary text-on-primary hover:bg-primary-hover flex flex-1 items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-[13.5px] font-semibold transition active:scale-[0.98]"
            >
              <UploadIcon className="h-4 w-4" />
              อัปโหลดภาพใหม่
            </button>
            <button
              type="button"
              onClick={onRetry}
              className="flex items-center justify-center gap-2 rounded-lg border border-line-strong px-4 py-2.5 text-[13px] font-medium text-ink transition hover:border-line-strong hover:bg-sunken"
            >
              <RestartIcon className="h-4 w-4" />
              เริ่มใหม่
            </button>
          </div>
        </div>

        <p className="tnum mt-4 text-center text-[11px] text-ink-muted">
          {study.studyId} · หยุดที่ด่าน {halt.stageId}
        </p>
      </div>
    </div>
  )
}

function Row({
  label,
  required,
  actual,
  ok,
}: {
  label: string
  required: string
  actual: string
  ok: boolean
}) {
  return (
    <>
      <dt className="text-ink-muted">{label}</dt>
      <dd className="tnum text-right">
        <span className="text-ink-muted">{required}</span>
        <span className="mx-1.5 text-ink-muted">→</span>
        <span className={ok ? 'text-verified-ink' : 'text-alert-ink font-semibold'}>
          {actual}
        </span>
      </dd>
    </>
  )
}
