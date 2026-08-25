/**
 * Configuration for the SmartLiva AI Backend Service.
 */
export interface LiverUsServiceConfig {
  baseUrl: string
  /** Whole-request budget in milliseconds */
  analyzeTimeoutMs: number
  /** Scanner identifier */
  siteId: string | null
}

const resolveDefaultBaseUrl = (): string => {
  if (import.meta.env.VITE_LIVER_US_URL) {
    return import.meta.env.VITE_LIVER_US_URL
  }
  if (typeof window !== 'undefined' && window.location && window.location.port !== '5173') {
    return window.location.origin
  }
  return 'http://127.0.0.1:8000'
}

export const LIVER_US_SERVICE: LiverUsServiceConfig = {
  baseUrl: resolveDefaultBaseUrl(),
  analyzeTimeoutMs: 25000,
  siteId: import.meta.env.VITE_LIVER_US_SITE_ID ?? null,
}
