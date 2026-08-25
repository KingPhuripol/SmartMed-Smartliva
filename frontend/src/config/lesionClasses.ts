/** Classes the lesion agent can emit, and which of them demand urgency. */
export const LESION_CLASSES = [
  'Cyst',
  'Hemangioma',
  'Focal fatty sparing',
  'Calcification',
  'Abscess',
  'Suspicious mass',
] as const

export type LesionClass = (typeof LESION_CLASSES)[number]

/**
 * Labels that escalate the study's risk level and colour the report.
 * Kept as data, not scattered `if` statements, so adding a class is one edit.
 */
export const CRITICAL_LESION_LABELS: ReadonlySet<string> = new Set([
  'Abscess',
  'Suspicious mass',
])

/**
 * What a physician can name when marking something the model missed, with no
 * agent in context — a free mark on the image is most often a lesion the
 * detector did not catch.
 */
export const SUSPECTED_OPTIONS = [...LESION_CLASSES, 'อื่น ๆ'] as const

export type SuspectedLabel = (typeof SUSPECTED_OPTIONS)[number]

/**
 * What the mark can be called depends on which agent is being corrected. A mark
 * drawn against the fibrosis agent is pointing at a texture or a contour, not at
 * a cyst — offering the lesion classes there asks the physician to describe one
 * finding in another finding's vocabulary, and the answer lands in the training
 * record that way too.
 */
export const SUSPECTED_OPTIONS_BY_AGENT = {
  // B-mode signs a radiologist actually grades fibrosis on.
  fibrosis: [
    'ผิวตับเป็นปุ่ม (surface nodularity)',
    'เนื้อตับหยาบไม่สม่ำเสมอ (coarse echotexture)',
    'ผนัง portal tract หนาขึ้น (periportal cuffing)',
    'ขอบล่างตับมน (blunted inferior edge)',
    'สัดส่วนกลีบตับเปลี่ยน (caudate hypertrophy)',
    'มีน้ำในช่องท้อง / ม้ามโต',
    'อื่น ๆ',
  ],
  // The four conventional criteria, plus the uneven-distribution case that is
  // the usual reason a global stage is wrong.
  steatosis: [
    'ตับสว่างกว่าเปลือกไต (hepatorenal contrast)',
    'คลื่นเสียงลดทอนในชั้นลึก (posterior attenuation)',
    'เห็นกะบังลมไม่ชัด',
    'ผนังหลอดเลือดในตับเบลอ (vessel blurring)',
    'ไขมันกระจายไม่สม่ำเสมอ (focal sparing / deposition)',
    'อื่น ๆ',
  ],
  lesion: [...LESION_CLASSES, 'อื่น ๆ'],
  // Opisthorchis viverrini findings as they are described on ultrasound.
  fluke: [
    'ผนังท่อน้ำดีหนาและ echo สูง (periductal fibrosis)',
    'ท่อน้ำดีในตับโป่ง (duct dilatation)',
    'ถุงน้ำดีโตหรือบีบตัวไม่ดี',
    'มีตะกอนในถุงน้ำดี',
    'สงสัย cholangiocarcinoma',
    'อื่น ๆ',
  ],
} as const satisfies Record<string, readonly string[]>

/** The option that means "none of the above" and needs the physician to say what. */
export const OTHER_OPTION = 'อื่น ๆ'

/** Options for a mark, given the agent it was drawn against (if any). */
export function suspectedOptionsFor(agentId: string | undefined): readonly string[] {
  if (!agentId) return SUSPECTED_OPTIONS
  const byAgent = SUSPECTED_OPTIONS_BY_AGENT as Record<string, readonly string[]>
  return byAgent[agentId] ?? SUSPECTED_OPTIONS
}

/** Labels a fresh mark carries before the physician has named it. */
export const UNNAMED_MARK_LABELS: ReadonlySet<string> = new Set([
  'จุดที่สงสัย',
  'บริเวณที่สงสัย',
])
