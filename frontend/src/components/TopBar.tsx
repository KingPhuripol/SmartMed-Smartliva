import type { StudyRecord } from '../domain'
import { RestartIcon } from './ui/Icons'

interface TopBarProps {
  study: StudyRecord | null
  reviewed: number
  total: number
  historyCount: number
  onReset: () => void
  onOpenHistory: () => void
}

function Chip({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline gap-1.5">
      <span className="text-ink-muted text-[10px] font-medium tracking-[0.12em] uppercase">
        {label}
      </span>
      <span className="tnum text-[12px] font-semibold text-ink">{value}</span>
    </div>
  )
}

export function TopBar({
  study,
  reviewed,
  total,
  historyCount,
  onReset,
  onOpenHistory,
}: TopBarProps) {
  const isUncalibrated = study?.organ?.service?.warnings?.includes('SCANNER_NOT_CALIBRATED')

  return (
    <header className="panel no-print relative z-30 flex h-14 shrink-0 items-center justify-between gap-4 rounded-none border-x-0 border-t-0 px-4 sm:px-6 bg-card/95 backdrop-blur-sm shadow-2xs">
      {/* Brand & Logo */}
      <div className="flex items-center gap-2.5 shrink-0">
        <img
          src="/smartliva-mark.png"
          alt="SmartLiva Logo"
          width={128}
          height={128}
          className="h-8 w-8 shrink-0 select-none drop-shadow-xs"
        />
        <div className="leading-tight">
          <div className="flex items-center gap-1.5">
            <h1 className="text-[15px] font-bold tracking-tight text-ink">
              Smart<span className="text-medical">Liva</span>
            </h1>
            <span className="bg-emerald-50 text-emerald-700 border border-emerald-200 text-[10px] font-bold px-1.5 py-0.2 rounded">
              v1.1
            </span>
            <span className="hidden sm:inline-flex items-center gap-1 bg-amber-500/10 text-amber-600 border border-amber-500/30 text-[10px] font-semibold px-2 py-0.5 rounded-full ml-1">
              <span>🔬</span>
              <span>Stage 2: Pilot Shadow Study</span>
            </span>
          </div>
          <p className="text-ink-muted text-[10px] tracking-[0.08em]">
            Clinical Intelligence & Doctor-in-the-Loop Console
          </p>
        </div>
      </div>

      {/* Study Metadata (when reviewing a study) */}
      {study ? (
        <div className="flex min-w-0 flex-1 items-center justify-end sm:justify-between gap-3 sm:gap-4 overflow-hidden ml-4">
          <div className="hidden sm:flex items-center gap-4">
            <Chip label="Study ID" value={study.studyId} />
            <div className="bg-line h-4 w-px" />
            <Chip label="ไฟล์ภาพ" value={study.intake.fileName} />
            <div className="bg-line h-4 w-px" />
            <Chip label="ขนาด" value={`${study.intake.width}×${study.intake.height} px`} />
          </div>

          {isUncalibrated && (
            <div className="hidden items-center gap-1.5 rounded-full border border-amber-500/40 bg-amber-500/10 px-2.5 py-0.5 text-[11px] font-medium text-amber-600 md:flex">
              <span>⚠️</span>
              <span>ยังไม่ calibrate</span>
            </div>
          )}

          {/* Right Action Controls */}
          <div className="flex shrink-0 items-center gap-2">
            {total > 0 && (
              <div className="border-line bg-sunken flex items-center gap-1.5 rounded-full border px-2.5 py-1">
                <span className="text-ink-muted hidden text-[10px] font-medium tracking-[0.1em] uppercase md:inline">
                  ตรวจแล้ว
                </span>
                <span className="tnum text-[12px] font-bold text-medical">
                  {reviewed}
                  <span className="text-ink-muted font-normal">/{total}</span>
                </span>
              </div>
            )}

            {/* History Button */}
            <button
              type="button"
              onClick={onOpenHistory}
              className="border-line bg-card hover:bg-sunken text-ink text-xs font-semibold px-3 py-1.2 rounded-full border flex items-center gap-1.5 transition cursor-pointer"
            >
              <span>📋</span>
              <span className="hidden sm:inline">ประวัติ</span>
              <span className="bg-medical text-white font-mono text-[10px] font-bold rounded-full px-1.5 py-0.2">
                {historyCount}
              </span>
            </button>

            {/* New Case Button */}
            <button
              type="button"
              onClick={onReset}
              className="bg-primary text-white hover:bg-primary-hover flex items-center gap-1.5 rounded-full px-3 py-1.2 text-[12px] font-semibold transition cursor-pointer shadow-xs active:scale-[0.98]"
            >
              <RestartIcon className="h-3.5 w-3.5" />
              <span>เคสใหม่</span>
            </button>
          </div>
        </div>
      ) : (
        <div className="flex items-center gap-2.5">
          {/* History Button on Upload Screen */}
          <button
            type="button"
            onClick={onOpenHistory}
            className="border-line bg-card hover:bg-sunken text-ink text-xs font-semibold px-3 py-1.2 rounded-full border flex items-center gap-1.5 transition shadow-2xs cursor-pointer"
          >
            <span>📋</span>
            <span>ประวัติการตรวจ</span>
            <span className="bg-medical text-white font-mono text-[10px] font-bold rounded-full px-1.5 py-0.2">
              {historyCount}
            </span>
          </button>

          <div className="flex items-center gap-1.5 bg-emerald-50 text-emerald-700 border border-emerald-200 px-2.5 py-1 rounded-full text-xs font-medium">
            <span className="bg-emerald-500 animate-pulse h-2 w-2 rounded-full" />
            <span>ระบบพร้อมใช้งาน</span>
          </div>
        </div>
      )}
    </header>
  )
}
