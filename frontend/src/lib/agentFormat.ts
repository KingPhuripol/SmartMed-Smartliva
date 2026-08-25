import type {
  AgentId,
  AgentValueMap,
  FibrosisStage,
  FlukeResult,
  LesionResult,
  RiskLevel,
  SteatosisStage,
} from '../domain'

/** Short qualifiers shown beneath each stage value. */
export const FIBROSIS_NOTES: Record<FibrosisStage, string> = {
  F0: 'ไม่พบพังผืด',
  F1: 'พังผืดบริเวณ portal ไม่มี septa',
  F2: 'พังผืดพร้อม septa เล็กน้อย',
  F3: 'septa จำนวนมาก ยังไม่เป็นตับแข็ง',
  F4: 'ตับแข็ง',
}

export const STEATOSIS_NOTES: Record<SteatosisStage, string> = {
  S0: 'ไขมันน้อยกว่า 5%',
  S1: 'ไขมัน 5–33%',
  S2: 'ไขมัน 34–66%',
  S3: 'ไขมันมากกว่า 66%',
}

export const RISK_LABEL: Record<RiskLevel, { th: string; en: string }> = {
  low: { th: 'ความเสี่ยงต่ำ', en: 'Low risk' },
  moderate: { th: 'ความเสี่ยงปานกลาง', en: 'Moderate risk' },
  high: { th: 'ความเสี่ยงสูง', en: 'High risk' },
  critical: { th: 'ความเสี่ยงสูงมาก', en: 'Critical' },
}

export const RISK_COLOR: Record<RiskLevel, string> = {
  low: 'var(--color-verified)',
  moderate: 'var(--color-modified)',
  high: 'var(--color-high)',
  critical: 'var(--color-alert)',
}

/**
 * The same four levels, in the variant that is readable as text on the current
 * surface. RISK_COLOR values are fills: amber on white is 2.15:1, so using one
 * as a text colour fails AA outright.
 */
export const RISK_INK: Record<RiskLevel, string> = {
  low: 'var(--color-verified-ink)',
  moderate: 'var(--color-modified-ink)',
  high: 'var(--color-high-ink)',
  critical: 'var(--color-alert-ink)',
}

/** One-line summary of an agent's answer, used on cards and in reports. */
export function formatAgentValue(agentId: AgentId, value: unknown): string {
  switch (agentId) {
    case 'fibrosis':
      return value as FibrosisStage
    case 'steatosis':
      return value as SteatosisStage
    case 'fluke':
      return value as FlukeResult
    case 'lesion': {
      const result = value as LesionResult
      if (!result || result.findings.length === 0) return 'ไม่พบรอยโรค'
      const counts = new Map<string, number>()
      for (const f of result.findings) counts.set(f.label, (counts.get(f.label) ?? 0) + 1)
      return [...counts.entries()].map(([label, n]) => `${label} × ${n}`).join(', ')
    }
    default:
      return String(value)
  }
}

export function describeAgentValue(agentId: AgentId, value: unknown): string {
  switch (agentId) {
    case 'fibrosis':
      return FIBROSIS_NOTES[value as FibrosisStage] ?? ''
    case 'steatosis':
      return STEATOSIS_NOTES[value as SteatosisStage] ?? ''
    case 'fluke':
      return value === 'Positive'
        ? 'เข้าได้กับการติดเชื้อ Opisthorchis viverrini'
        : 'ไม่พบร่องรอยการติดเชื้อ'
    case 'lesion': {
      const result = value as LesionResult
      const n = result?.findings.length ?? 0
      return n === 0 ? 'เนื้อตับไม่มีรอยโรคเฉพาะที่' : `ระบุตำแหน่งไว้ ${n} จุดบนภาพ`
    }
    default:
      return ''
  }
}

/** Deep equality good enough for comparing agent values. */
export function sameAgentValue<K extends AgentId>(
  a: AgentValueMap[K] | undefined,
  b: AgentValueMap[K] | undefined,
): boolean {
  return JSON.stringify(a) === JSON.stringify(b)
}
