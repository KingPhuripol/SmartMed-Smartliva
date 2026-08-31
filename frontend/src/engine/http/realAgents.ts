import type {
  AgentInput,
  AgentOutput,
  AgentRunner,
  FibrosisStage,
  FlukeResult,
  LesionResult,
  SteatosisStage,
} from '../../domain'
import type { LiverUsServiceConfig } from '../../config/service'
import { LIVER_US_SERVICE } from '../../config/service'
import { stubFibrosisAgent } from '../stubs/agents/fibrosisAgent'
import { stubLesionAgent } from '../stubs/agents/lesionAgent'
import { stubSteatosisAgent } from '../stubs/agents/steatosisAgent'
import { stubFlukeAgent } from '../stubs/agents/flukeAgent'

async function getBlob(input: AgentInput, signal?: AbortSignal): Promise<Blob> {
  const res = await fetch(input.intake.source, { signal })
  return res.blob()
}

/**
 * Real HTTP Agent Runner for Fibrosis Staging (F0–F4) with offline fallback.
 */
export function createHttpFibrosisRunner(
  cfg: LiverUsServiceConfig = LIVER_US_SERVICE,
): AgentRunner<'fibrosis'> {
  return {
    agentId: 'fibrosis',
    async run(input: AgentInput, signal?: AbortSignal): Promise<AgentOutput<'fibrosis'>> {
      try {
        const blob = await getBlob(input, signal)
        const form = new FormData()
        form.append('file', blob, input.intake.fileName)
        if (input.intake.clinical?.view) {
          form.append('view', input.intake.clinical.view)
        }

        const res = await fetch(`${cfg.baseUrl}/api/v1/agents/fibrosis`, {
          method: 'POST',
          body: form,
          signal,
        })

        if (!res.ok) {
          throw new Error(`Fibrosis agent call failed with HTTP ${res.status}`)
        }

        const data = await res.json()
        return {
          agentId: 'fibrosis',
          value: (data.value as FibrosisStage) || 'F0',
          confidence: data.confidence ?? 0.85,
          regions: data.regions ?? [],
          rationale: data.rationale ?? 'Fibrosis evaluation completed.',
          modelVersion: data.modelVersion ?? 'fibrosis-ensemble-2.0.0',
          inferenceMs: data.inferenceMs ?? 150,
          simulated: false,
        }
      } catch {
        return stubFibrosisAgent.run(input, signal)
      }
    },
  }
}

/**
 * Real HTTP Agent Runner for YOLOv8 Focal Lesion Detection with offline fallback.
 */
export function createHttpLesionRunner(
  cfg: LiverUsServiceConfig = LIVER_US_SERVICE,
): AgentRunner<'lesion'> {
  return {
    agentId: 'lesion',
    async run(input: AgentInput, signal?: AbortSignal): Promise<AgentOutput<'lesion'>> {
      try {
        const blob = await getBlob(input, signal)
        const form = new FormData()
        form.append('file', blob, input.intake.fileName)
        form.append('conf_thres', '0.25')

        const res = await fetch(`${cfg.baseUrl}/api/v1/agents/lesion`, {
          method: 'POST',
          body: form,
          signal,
        })

        if (!res.ok) {
          throw new Error(`Lesion agent call failed with HTTP ${res.status}`)
        }

        const data = await res.json()
        return {
          agentId: 'lesion',
          value: (data.value as LesionResult) || { findings: [] },
          confidence: data.confidence ?? 0.90,
          regions: data.regions ?? [],
          rationale: data.rationale ?? 'Lesion detection completed.',
          modelVersion: data.modelVersion ?? 'yolov8-lesion-2.0.0',
          inferenceMs: data.inferenceMs ?? 80,
          simulated: false,
        }
      } catch {
        return stubLesionAgent.run(input, signal)
      }
    },
  }
}

/**
 * Real HTTP Agent Runner for Hepatic Steatosis (S0–S3) with offline fallback.
 */
export function createHttpSteatosisRunner(
  cfg: LiverUsServiceConfig = LIVER_US_SERVICE,
): AgentRunner<'steatosis'> {
  return {
    agentId: 'steatosis',
    async run(input: AgentInput, signal?: AbortSignal): Promise<AgentOutput<'steatosis'>> {
      try {
        const blob = await getBlob(input, signal)
        const form = new FormData()
        form.append('file', blob, input.intake.fileName)

        const res = await fetch(`${cfg.baseUrl}/api/v1/agents/steatosis`, {
          method: 'POST',
          body: form,
          signal,
        })

        if (!res.ok) {
          throw new Error(`Steatosis agent call failed with HTTP ${res.status}`)
        }

        const data = await res.json()
        return {
          agentId: 'steatosis',
          value: (data.value as SteatosisStage) || 'S0',
          confidence: data.confidence ?? 0.85,
          regions: data.regions ?? [],
          rationale: data.rationale ?? 'Steatosis assessment completed.',
          modelVersion: data.modelVersion ?? 'steatosis-attenuation-2.0.0',
          inferenceMs: data.inferenceMs ?? 50,
          simulated: false,
        }
      } catch {
        return stubSteatosisAgent.run(input, signal)
      }
    },
  }
}

/**
 * Real HTTP Agent Runner for Liver Fluke & CCA Risk with offline fallback.
 */
export function createHttpFlukeRunner(
  cfg: LiverUsServiceConfig = LIVER_US_SERVICE,
): AgentRunner<'fluke'> {
  return {
    agentId: 'fluke',
    async run(input: AgentInput, signal?: AbortSignal): Promise<AgentOutput<'fluke'>> {
      try {
        const blob = await getBlob(input, signal)
        const form = new FormData()
        form.append('file', blob, input.intake.fileName)
        if (input.intake.clinical?.history) {
          form.append('history_json', JSON.stringify(input.intake.clinical.history))
        }
        if (input.intake.clinical?.lab) {
          form.append('lab_json', JSON.stringify(input.intake.clinical.lab))
        }

        const res = await fetch(`${cfg.baseUrl}/api/v1/agents/fluke`, {
          method: 'POST',
          body: form,
          signal,
        })

        if (!res.ok) {
          throw new Error(`Fluke agent call failed with HTTP ${res.status}`)
        }

        const data = await res.json()
        const rawVal = data.value
        const normalizedValue: FlukeResult =
          rawVal === 'Probable' || rawVal === 'Possible' || rawVal === 'Positive'
            ? 'Positive'
            : 'Negative'

        return {
          agentId: 'fluke',
          value: normalizedValue,
          confidence: data.confidence ?? 0.90,
          regions: data.regions ?? [],
          rationale: data.rationale ?? 'Fluke findings evaluated.',
          modelVersion: data.modelVersion ?? 'fluke-risk-2.0.0',
          inferenceMs: data.inferenceMs ?? 60,
          simulated: false,
        }
      } catch {
        return stubFlukeAgent.run(input, signal)
      }
    },
  }
}
