/** Small shared helpers for the engine layer. */

let counter = 0

export function nextId(prefix: string): string {
  counter += 1
  return `${prefix}-${counter.toString(36).padStart(4, '0')}`
}

export function now(): string {
  return new Date().toISOString()
}

/** Simulated latency for stubbed stages, so the UI exercises real timings. */
export function delay(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException('Aborted', 'AbortError'))
      return
    }
    const timer = window.setTimeout(() => {
      signal?.removeEventListener('abort', onAbort)
      resolve()
    }, ms)
    const onAbort = () => {
      window.clearTimeout(timer)
      reject(new DOMException('Aborted', 'AbortError'))
    }
    signal?.addEventListener('abort', onAbort, { once: true })
  })
}
