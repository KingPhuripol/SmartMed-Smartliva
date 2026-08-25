import type {
  AgentId,
  AgentOutput,
  AgentValueMap,
  Agreement,
  FibrosisStage,
  FlukeResult,
  LesionResult,
  RiskLevel,
  SteatosisStage,
  SupervisorAgentAssessment,
  SupervisorConflict,
  SupervisorInput,
  SupervisorReview,
  SupervisorRunner,
} from '../domain'
import { RISK_ORDER } from '../domain'
import { CRITICAL_LESION_LABELS } from '../config/lesionClasses'
import { delay, now } from './util'

/**
 * Stage 5 — the supervisor sitting above the four agents.
 *
 * This is a RULE-BASED implementation, not an LLM. It is not a placeholder in
 * the way the agent stubs are: the cross-agent checks below are real clinical
 * reasoning and stay useful even after an LLM is wired in — as the deterministic
 * floor an LLM's output can be checked against.
 *
 * To swap in an LLM, implement `SupervisorRunner` elsewhere and pass it to the
 * pipeline. Note before doing so: an ultrasound study is health data, and
 * sending it or its derivatives to a hosted model has PDPA consequences that
 * need settling first.
 *
 * Its verdicts are a SECOND OPINION. Nothing here overwrites an agent's value.
 */

function findValue<K extends AgentId>(
  outputs: AgentOutput[],
  agentId: K,
): AgentValueMap[K] | null {
  const match = outputs.find((o) => o.agentId === agentId)
  return match ? (match.value as AgentValueMap[K]) : null
}

const FIBROSIS_RISK: Record<FibrosisStage, RiskLevel> = {
  F0: 'low',
  F1: 'low',
  F2: 'moderate',
  F3: 'high',
  F4: 'critical',
}

const STEATOSIS_RISK: Record<SteatosisStage, RiskLevel> = {
  S0: 'low',
  S1: 'low',
  S2: 'moderate',
  S3: 'high',
}

function worst(a: RiskLevel, b: RiskLevel): RiskLevel {
  return RISK_ORDER.indexOf(a) >= RISK_ORDER.indexOf(b) ? a : b
}

/** Confidence bands used when no more specific rule applies. */
function agreementFromConfidence(confidence: number): Agreement {
  if (confidence >= 0.85) return 'agree'
  if (confidence >= 0.65) return 'uncertain'
  return 'disagree'
}

function assessAgent(output: AgentOutput): SupervisorAgentAssessment {
  if (output.simulated) {
    return {
      agentId: output.agentId,
      agreement: 'uncertain',
      note: 'ยังไม่มีโมเดลจริงรองรับ agent นี้ — ค่าที่แสดงเป็นค่าจำลอง ไม่ควรใช้ตัดสินใจทางคลินิก',
    }
  }

  if (output.regions.length === 0) {
    return {
      agentId: output.agentId,
      agreement: 'disagree',
      note: 'Agent ไม่ได้ระบุบริเวณที่ใช้ตัดสิน — ไม่สามารถตรวจสอบย้อนกลับได้',
    }
  }

  const agreement = agreementFromConfidence(output.confidence)
  const note =
    agreement === 'agree'
      ? `ความมั่นใจ ${(output.confidence * 100).toFixed(0)}% พร้อมบริเวณอ้างอิง ${output.regions.length} จุด สอดคล้องกับเหตุผลที่ให้มา`
      : agreement === 'uncertain'
        ? `ความมั่นใจ ${(output.confidence * 100).toFixed(0)}% อยู่ในช่วงที่ควรให้แพทย์ยืนยันด้วยตา`
        : `ความมั่นใจต่ำ (${(output.confidence * 100).toFixed(0)}%) — แนะนำให้แพทย์ประเมินใหม่ทั้งหมด`

  return { agentId: output.agentId, agreement, note }
}

/**
 * Cross-agent checks — the part no single agent can do, because each only sees
 * its own question.
 */
function findConflicts(outputs: AgentOutput[]): SupervisorConflict[] {
  const conflicts: SupervisorConflict[] = []
  const fibrosis = findValue(outputs, 'fibrosis')
  const steatosis = findValue(outputs, 'steatosis')
  const lesion = findValue(outputs, 'lesion') as LesionResult | null
  const fluke = findValue(outputs, 'fluke') as FlukeResult | null

  const findings = lesion?.findings ?? []

  if (fibrosis === 'F4' && steatosis === 'S0' && findings.length === 0) {
    conflicts.push({
      conflictId: 'cf-cirrhosis-isolated',
      agents: ['fibrosis', 'steatosis', 'lesion'],
      description:
        'รายงานตับแข็ง (F4) โดยไม่พบไขมันพอกตับและไม่พบรอยโรคใด ๆ — เป็นไปได้แต่พบไม่บ่อย ควรทบทวนภาพซ้ำก่อนสรุป',
      severity: 'warning',
    })
  }

  if (fibrosis === 'F0' && steatosis === 'S3') {
    conflicts.push({
      conflictId: 'cf-severe-steatosis-no-fibrosis',
      agents: ['fibrosis', 'steatosis'],
      description:
        'ไขมันพอกตับรุนแรง (S3) แต่ไม่พบพังผืดเลย (F0) — เป็นไปได้ในระยะแรก แต่การลดทอนคลื่นเสียงจาก S3 อาจบดบังลักษณะพังผืด',
      severity: 'info',
    })
  }

  if ((steatosis === 'S2' || steatosis === 'S3') && findings.length > 0) {
    const deepLowConfidence = findings.some((f) => f.confidence < 0.6)
    if (deepLowConfidence) {
      conflicts.push({
        conflictId: 'cf-attenuation-limits-lesion',
        agents: ['steatosis', 'lesion'],
        description:
          'ไขมันพอกตับระดับปานกลางถึงมากทำให้คลื่นเสียงถูกลดทอน ความน่าเชื่อถือของการตรวจหารอยโรคในชั้นลึกจึงลดลง — รอยโรคที่ความมั่นใจต่ำควรตรวจซ้ำ',
        severity: 'warning',
      })
    }
  }

  if (fluke === 'Positive' && fibrosis === 'F0') {
    conflicts.push({
      conflictId: 'cf-fluke-without-fibrosis',
      agents: ['fluke', 'fibrosis'],
      description:
        'พบร่องรอยพยาธิใบไม้ตับแต่ไม่พบพังผืดรอบท่อน้ำดีเลย — ควรตรวจสอบว่า agent ทั้งสองมองบริเวณเดียวกันหรือไม่',
      severity: 'warning',
    })
  }

  const critical = findings.filter((f) => CRITICAL_LESION_LABELS.has(f.label))
  if (critical.length > 0) {
    conflicts.push({
      conflictId: 'cf-critical-lesion',
      agents: ['lesion'],
      description: `พบรอยโรคที่ต้องให้ความสำคัญเร่งด่วน: ${critical
        .map((f) => f.label)
        .join(', ')} — ควรส่งตรวจเพิ่มเติมโดยไม่รอผลอื่น`,
      severity: 'critical',
    })
  }

  return conflicts
}

function computeRisk(outputs: AgentOutput[], conflicts: SupervisorConflict[]): RiskLevel {
  let risk: RiskLevel = 'low'

  const fibrosis = findValue(outputs, 'fibrosis')
  if (fibrosis) risk = worst(risk, FIBROSIS_RISK[fibrosis])

  const steatosis = findValue(outputs, 'steatosis')
  if (steatosis) risk = worst(risk, STEATOSIS_RISK[steatosis])

  if (findValue(outputs, 'fluke') === 'Positive') risk = worst(risk, 'high')

  const lesion = findValue(outputs, 'lesion') as LesionResult | null
  for (const finding of lesion?.findings ?? []) {
    if (CRITICAL_LESION_LABELS.has(finding.label)) risk = worst(risk, 'critical')
  }

  if (conflicts.some((c) => c.severity === 'critical')) risk = worst(risk, 'critical')

  return risk
}

function buildImpression(outputs: AgentOutput[], risk: RiskLevel): string {
  const parts: string[] = []
  const fibrosis = findValue(outputs, 'fibrosis')
  const steatosis = findValue(outputs, 'steatosis')
  const lesion = findValue(outputs, 'lesion') as LesionResult | null
  const fluke = findValue(outputs, 'fluke') as FlukeResult | null

  if (steatosis) {
    parts.push(
      steatosis === 'S0'
        ? 'ไม่พบลักษณะไขมันพอกตับ'
        : `พบไขมันพอกตับระดับ ${steatosis}`,
    )
  }
  if (fibrosis) {
    parts.push(fibrosis === 'F0' ? 'ไม่พบพังผืด' : `ระดับพังผืด ${fibrosis}`)
  }
  if (lesion) {
    parts.push(
      lesion.findings.length === 0
        ? 'ไม่พบรอยโรคเฉพาะที่'
        : `พบรอยโรค ${lesion.findings.length} จุด (${lesion.findings.map((f) => f.label).join(', ')})`,
    )
  }
  if (fluke) {
    parts.push(
      fluke === 'Positive'
        ? 'พบร่องรอยที่เข้าได้กับพยาธิใบไม้ตับ'
        : 'ไม่พบร่องรอยพยาธิใบไม้ตับ',
    )
  }

  const riskText: Record<RiskLevel, string> = {
    low: 'ภาพรวมความเสี่ยงต่ำ',
    moderate: 'ภาพรวมความเสี่ยงปานกลาง ควรติดตาม',
    high: 'ภาพรวมความเสี่ยงสูง ควรส่งตรวจเพิ่มเติม',
    critical: 'ภาพรวมความเสี่ยงสูงมาก ควรดำเนินการโดยเร็ว',
  }

  return `${parts.join(' · ')} — ${riskText[risk]}`
}

function buildRecommendations(
  outputs: AgentOutput[],
  conflicts: SupervisorConflict[],
): string[] {
  const recommendations: string[] = []

  if (outputs.some((o) => o.simulated)) {
    recommendations.push(
      'มี agent ที่ยังใช้ค่าจำลอง — ผลชุดนี้ใช้เพื่อทดสอบระบบเท่านั้น ยังไม่ใช้ตัดสินใจทางคลินิก',
    )
  }
  if (conflicts.some((c) => c.severity === 'critical')) {
    recommendations.push('ส่งตรวจเพิ่มเติมโดยไม่ต้องรอผลพารามิเตอร์อื่น')
  }
  if (findValue(outputs, 'fluke') === 'Positive') {
    recommendations.push('ตรวจอุจจาระหาไข่พยาธิเพื่อยืนยัน')
  }
  const steatosis = findValue(outputs, 'steatosis')
  if (steatosis === 'S2' || steatosis === 'S3') {
    recommendations.push('ประเมินภาวะเมตาบอลิกร่วม และนัดติดตามการทำงานของตับ')
  }
  const lowConfidence = outputs.filter((o) => !o.simulated && o.confidence < 0.65)
  if (lowConfidence.length > 0) {
    recommendations.push(
      `ให้แพทย์ทบทวนด้วยตาเป็นพิเศษสำหรับ: ${lowConfidence.map((o) => o.agentId).join(', ')}`,
    )
  }

  return recommendations
}

export const ruleBasedSupervisor: SupervisorRunner = {
  async run(input: SupervisorInput, signal?: AbortSignal): Promise<SupervisorReview> {
    const started = performance.now()
    await delay(560, signal)

    const outputs = input.agentOutputs
    const conflicts = findConflicts(outputs)
    const overallRisk = computeRisk(outputs, conflicts)

    return {
      perAgent: outputs.map(assessAgent),
      conflicts,
      overallRisk,
      impression: buildImpression(outputs, overallRisk),
      recommendations: buildRecommendations(outputs, conflicts),
      modelVersion: 'rule-supervisor-1.0',
      latencyMs: Math.round(performance.now() - started),
      // Not a stub: this logic is real, it simply is not an LLM.
      simulated: false,
      reviewedAt: now(),
    }
  },
}
