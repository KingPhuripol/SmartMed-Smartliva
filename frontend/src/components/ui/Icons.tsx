import type { ReactNode } from 'react'

interface IconProps {
  className?: string
}

const base = 'h-4 w-4'

function Svg({
  className,
  children,
  fill = 'none',
}: IconProps & { children: ReactNode; fill?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill={fill}
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className ?? base}
      aria-hidden="true"
    >
      {children}
    </svg>
  )
}

export const CheckIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="m4.5 12.5 5 5 10-11" />
  </Svg>
)

export const PencilIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 20h4l10.5-10.5a2.83 2.83 0 0 0-4-4L4 16v4Z" />
    <path d="m13.5 6.5 4 4" />
  </Svg>
)

export const UploadIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M12 16V4" />
    <path d="m7 9 5-5 5 5" />
    <path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" />
  </Svg>
)

export const LayersIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="m12 3 9 5-9 5-9-5 9-5Z" />
    <path d="m3 13 9 5 9-5" />
  </Svg>
)

export const SlidersIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 7h10M18 7h2M4 17h4M12 17h8" />
    <circle cx="16" cy="7" r="2" />
    <circle cx="10" cy="17" r="2" />
  </Svg>
)

export const ReportIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5Z" />
    <path d="M14 3v5h5" />
    <path d="M9 13h6M9 17h4" />
  </Svg>
)

export const DatabaseIcon = (p: IconProps) => (
  <Svg {...p}>
    <ellipse cx="12" cy="6" rx="7" ry="3" />
    <path d="M5 6v12c0 1.66 3.13 3 7 3s7-1.34 7-3V6" />
    <path d="M5 12c0 1.66 3.13 3 7 3s7-1.34 7-3" />
  </Svg>
)

export const CloseIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="m6 6 12 12M18 6 6 18" />
  </Svg>
)

export const ChevronIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="m6 9 6 6 6-6" />
  </Svg>
)

export const AlertIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M12 4 2.5 20h19L12 4Z" />
    <path d="M12 10v4M12 17.5v.01" />
  </Svg>
)

export const SparkIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M12 3.5 13.9 9l5.6 1.9-5.6 1.9L12 18.4 10.1 12.8 4.5 10.9 10.1 9 12 3.5Z" />
    <path d="M18.5 3.5v3M20 5h-3" />
  </Svg>
)

export const StethoscopeIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M5 3v6a4 4 0 0 0 8 0V3" />
    <path d="M5 3H3.5M13 3h1.5" />
    <path d="M9 13v2a5 5 0 0 0 10 0v-1" />
    <circle cx="19" cy="11" r="2" />
  </Svg>
)

export const PlusIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M12 5v14M5 12h14" />
  </Svg>
)

export const TrashIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 7h16M9 7V5h6v2M6 7l1 13h10l1-13" />
  </Svg>
)

export const RestartIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M20 12a8 8 0 1 1-2.6-5.9" />
    <path d="M20 4v4h-4" />
  </Svg>
)

export const DownloadIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M12 4v11" />
    <path d="m7 11 5 5 5-5" />
    <path d="M4 19h16" />
  </Svg>
)

export const PrintIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M7 9V4h10v5" />
    <path d="M6 18H5a2 2 0 0 1-2-2v-4a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2h-1" />
    <path d="M7 14h10v6H7v-6Z" />
  </Svg>
)

/** SmartLiva mark — a stylised liver lobe carrying a pulse trace. */
export function BrandMark({ className }: IconProps) {
  return (
    <svg viewBox="0 0 40 40" className={className ?? 'h-9 w-9'} aria-hidden="true">
      <defs>
        <linearGradient id="sl-brand" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#67E8F9" />
          <stop offset="55%" stopColor="#22D3EE" />
          <stop offset="100%" stopColor="#0E7490" />
        </linearGradient>
      </defs>
      <path
        d="M6.2 14.4c4.6-4.9 12.4-6.6 19.3-4.6 4.9 1.4 8 4.6 8.4 8.6.5 5.1-3.2 10-9 12.3-6.4 2.5-13.6 1.2-17.2-3.2-1-1.3-1.6-2.8-1.8-4.4"
        fill="none"
        stroke="url(#sl-brand)"
        strokeWidth="2.4"
        strokeLinecap="round"
      />
      <path
        d="M7.6 22.6c2.2.3 3.6-.2 4.4-1.6.9-1.5 1.9-1.5 2.7 0l1.6 3.1 2.3-6.2 2.1 4.7h8.4"
        fill="none"
        stroke="#E2E8F0"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}
