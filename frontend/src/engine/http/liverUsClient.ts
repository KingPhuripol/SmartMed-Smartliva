import type { LiverUsServiceConfig } from '../../config/service'
import type { LiverUsAnalyzeOk, LiverUsError, LiverUsHealth } from './liverUsTypes'

/**
 * Transport for the liver-ultrasound service. Knows how to speak HTTP and how
 * to fail; knows nothing about the pipeline or the domain.
 *
 * Every failure arrives as a ServiceFailure carrying a code, never a sentence —
 * the Thai and English text lives in config/messages.ts, as with every other
 * refusal in this codebase.
 */
export type ServiceFailureKind =
  | 'UNREACHABLE'
  | 'TIMEOUT'
  | 'REJECTED_IMAGE'
  | 'INFERENCE_FAILED'
  | 'CONTRACT_VIOLATION'

export class ServiceFailure extends Error {
  kind: ServiceFailureKind
  code: string | null
  status: number | null

  constructor(kind: ServiceFailureKind, code: string | null, status: number | null) {
    super(`liver-us service: ${kind}${code ? ` (${code})` : ''}`)
    this.name = 'ServiceFailure'
    this.kind = kind
    this.code = code
    this.status = status
  }
}

/** Image-level refusals: the picture is wrong, not the service. */
const IMAGE_REJECTIONS = new Set(['NO_FILE', 'BAD_IMAGE', 'UNSUPPORTED_TYPE', 'TOO_LARGE'])

function isAnalyzeOk(body: unknown): body is LiverUsAnalyzeOk {
  if (typeof body !== 'object' || body === null) return false
  const b = body as Record<string, unknown>
  if (b.ok !== true) return false
  const image = b.image as Record<string, unknown> | undefined
  const regions = b.regions as Record<string, unknown> | undefined
  const liver = regions?.liver as Record<string, unknown> | undefined
  return (
    typeof b.api_version === 'string' &&
    typeof b.model_version === 'string' &&
    typeof b.verdict === 'string' &&
    typeof b.is_liver_us === 'boolean' &&
    typeof image?.width === 'number' &&
    typeof image?.height === 'number' &&
    Array.isArray(b.warnings) &&
    Array.isArray(liver?.polygons)
  )
}

export function createLiverUsClient(cfg: LiverUsServiceConfig) {
  async function post(
    blob: Blob,
    fileName: string,
    signal: AbortSignal | undefined,
  ): Promise<LiverUsAnalyzeOk> {
    const form = new FormData()
    // The field name and the filename both matter: the service validates the
    // extension before it decodes anything.
    form.append('image', blob, fileName)
    if (cfg.siteId) form.append('site_id', cfg.siteId)

    // A caller abort and a timeout must stay distinguishable, so the timeout
    // gets its own controller and the caller's signal is chained onto it.
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(new Error('timeout')), cfg.analyzeTimeoutMs)
    const onCallerAbort = () => controller.abort(signal?.reason)
    signal?.addEventListener('abort', onCallerAbort, { once: true })

    let response: Response
    try {
      response = await fetch(`${cfg.baseUrl}/analyze`, {
        method: 'POST',
        body: form,
        signal: controller.signal,
      })
    } catch (err) {
      if (signal?.aborted) throw err
      throw new ServiceFailure(controller.signal.aborted ? 'TIMEOUT' : 'UNREACHABLE', null, null)
    } finally {
      clearTimeout(timer)
      signal?.removeEventListener('abort', onCallerAbort)
    }

    let body: unknown
    try {
      body = await response.json()
    } catch {
      throw new ServiceFailure('CONTRACT_VIOLATION', 'NOT_JSON', response.status)
    }

    if (isAnalyzeOk(body)) return body

    const failure = body as LiverUsError
    const code = failure?.error?.code ?? null
    if (typeof code === 'string' && IMAGE_REJECTIONS.has(code)) {
      throw new ServiceFailure('REJECTED_IMAGE', code, response.status)
    }
    if (code === 'INFERENCE_FAILED') {
      throw new ServiceFailure('INFERENCE_FAILED', code, response.status)
    }
    throw new ServiceFailure('CONTRACT_VIOLATION', code, response.status)
  }

  return {
    async analyze(blob: Blob, fileName: string, signal?: AbortSignal): Promise<LiverUsAnalyzeOk> {
      try {
        return await post(blob, fileName, signal)
      } catch (err) {
        // The service documents INFERENCE_FAILED as worth exactly one retry.
        if (err instanceof ServiceFailure && err.kind === 'INFERENCE_FAILED' && !signal?.aborted) {
          return post(blob, fileName, signal)
        }
        throw err
      }
    },

    async health(signal?: AbortSignal): Promise<LiverUsHealth | null> {
      try {
        const r = await fetch(`${cfg.baseUrl}/health`, { signal })
        return (await r.json()) as LiverUsHealth
      } catch {
        return null
      }
    },
  }
}

export type LiverUsClient = ReturnType<typeof createLiverUsClient>
