import type { AgentId } from '../domain'

/**
 * Presentation metadata for the agents — kept out of `src/domain/` so the
 * domain layer stays free of anything UI-shaped.
 *
 * Each agent owns a colour: labels on the image, the agent's card border and
 * its toggle in the viewer all use the same one, so "which agent drew this?"
 * is answerable at a glance.
 */
export interface AgentDisplay {
  agentId: AgentId
  label: string
  labelTh: string
  /** Short description of what the agent decides. */
  description: string
  /** CSS colour used for this agent's regions and accents. */
  color: string
  /** Tailwind-friendly variants derived from the same hue. */
  colorSoft: string
}

export const AGENT_DISPLAY: Record<AgentId, AgentDisplay> = {
  fibrosis: {
    agentId: 'fibrosis',
    label: 'Fibrosis',
    labelTh: 'พังผืดในตับ',
    description: 'METAVIR F0–F4 จากพื้นผิวและ texture ของเนื้อตับ',
    color: '#A78BFA',
    colorSoft: '#C4B5FD',
  },
  steatosis: {
    agentId: 'steatosis',
    label: 'Steatosis',
    labelTh: 'ไขมันพอกตับ',
    description: 'S0–S3 จาก echogenicity และการลดทอนของคลื่นเสียง',
    color: '#38BDF8',
    colorSoft: '#7DD3FC',
  },
  lesion: {
    agentId: 'lesion',
    label: 'Lesion',
    labelTh: 'รอยโรค',
    description: 'ตำแหน่ง ชนิด และขนาดของรอยโรคเฉพาะที่',
    // Magenta, not the red it used to be: #F43F5E was byte-identical to
    // --color-alert, so this agent's identity and "pathology" were the same
    // colour (CIEDE2000 = 0.00). Red now means severity and nothing else.
    // Measured worst-case separation across normal, deuteranopia and
    // protanopia: >= 18.0 from every status colour and >= 18.8 from every
    // other agent -- both better than the value it replaces.
    color: '#DD389D',
    colorSoft: '#FF73C3',
  },
  fluke: {
    agentId: 'fluke',
    label: 'Liver Fluke',
    labelTh: 'พยาธิใบไม้ตับ',
    description: 'ร่องรอย Opisthorchis viverrini ที่ท่อน้ำดี',
    color: '#FBBF24',
    colorSoft: '#FCD34D',
  },
}

/** Colour for the U-Net liver outline — distinct from every agent colour. */
export const SEGMENTATION_COLOR = '#34D399'

/** Colour for marks the physician draws themselves. */
export const PHYSICIAN_COLOR = '#F8FAFC'
