import { useEffect } from 'react'
import { CheckIcon, CloseIcon } from './Icons'

interface ToastProps {
  message: string
  onDismiss: () => void
}

export function Toast({ message, onDismiss }: ToastProps) {
  useEffect(() => {
    const timer = window.setTimeout(onDismiss, 4200)
    return () => window.clearTimeout(timer)
  }, [message, onDismiss])

  return (
    <div
      role="status"
      className="panel animate-rise no-print fixed top-[76px] left-1/2 z-[60] flex -translate-x-1/2 items-center gap-2.5 rounded-full py-2.5 pr-2.5 pl-4"
    >
      <span className="border-verified/40 bg-verified/15 text-verified-ink flex h-5 w-5 items-center justify-center rounded-full border">
        <CheckIcon className="h-3 w-3" />
      </span>
      <span className="text-[13px] text-ink">{message}</span>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss"
        className="rounded-full p-1 text-ink-muted transition hover:bg-sunken hover:text-ink"
      >
        <CloseIcon className="h-3.5 w-3.5" />
      </button>
    </div>
  )
}
