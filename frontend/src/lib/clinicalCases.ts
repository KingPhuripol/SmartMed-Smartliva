/**
 * 8 Real Clinical Benchmark Ultrasound Cases for SmartLiva
 */

export interface ClinicalBenchmarkCase {
  id: string
  title: string
  shortTitle: string
  subTitle: string
  image_url: string
  view: string
  width: number
  height: number
  liver_area: string
  s_stage: {
    stage: 'S0' | 'S1' | 'S2' | 'S3'
    conf: number
    label: string
  }
  fibrosis: {
    stage: 'F0' | 'F1' | 'F2' | 'F3' | 'F4'
    risk_tier: string
    p_f2: number
    p_f3: number
    p_f4: number
  }
  lesions: Array<{
    type: string
    confidence: number
    size_mm: number
    location: string
    box: [number, number, number, number]
  }>
  fluke: {
    status: 'Positive' | 'Negative'
    conf: number
  }
  doctor_note: string
  supervisor_warning?: string
  polygons?: Array<[number, number]>
}

export const CLINICAL_BENCHMARK_CASES: ClinicalBenchmarkCase[] = [
  {
    id: 'case1_normal_rh',
    title: 'เคสที่ 1: ตับปกติ กลีบขวา (Normal Liver)',
    shortTitle: 'ตับปกติ กลีบขวา',
    subTitle: 'Normal Liver · Intercostal',
    image_url: '/samples/case1_normal_rh.jpg',
    view: 'Intercostal View (กลีบขวา)',
    width: 541,
    height: 400,
    liver_area: '176.3 cm²',
    s_stage: {
      stage: 'S0',
      conf: 96,
      label: 'Grade S0 — ปกติ ไม่มีไขมันพอกตับ (<5%)',
    },
    fibrosis: {
      stage: 'F0',
      risk_tier: 'ความเสี่ยงต่ำ (Low Risk)',
      p_f2: 4,
      p_f3: 1,
      p_f4: 1,
    },
    lesions: [],
    fluke: {
      status: 'Negative',
      conf: 98,
    },
    doctor_note: 'ตรวจพบโครงสร้างเนื้อตับมีความเรียบสม่ำเสมอ ผิวขอบเขตตับเรียบ ไม่พบก้อนเนื้อหรือรอยโรค',
    polygons: [
      [0.22, 0.35], [0.38, 0.28], [0.58, 0.25], [0.75, 0.30],
      [0.85, 0.45], [0.88, 0.65], [0.78, 0.82], [0.55, 0.88],
      [0.32, 0.82], [0.18, 0.68], [0.16, 0.50]
    ]
  },
  {
    id: 'case2_normal_gbh',
    title: 'เคสที่ 2: ตับและถุงน้ำดี ใต้ชายโครง (Subcostal View)',
    shortTitle: 'ตับและถุงน้ำดี',
    subTitle: 'Subcostal View · ถุงน้ำดี',
    image_url: '/samples/case2_normal_gbh.jpg',
    view: 'Subcostal View (ตัดผ่านถุงน้ำดี)',
    width: 640,
    height: 480,
    liver_area: '168.5 cm²',
    s_stage: {
      stage: 'S0',
      conf: 94,
      label: 'Grade S0 — ปกติ การสะท้อนเสียงสม่ำเสมอ',
    },
    fibrosis: {
      stage: 'F0',
      risk_tier: 'ความเสี่ยงต่ำ (Low Risk)',
      p_f2: 6,
      p_f3: 2,
      p_f4: 1,
    },
    lesions: [],
    fluke: {
      status: 'Negative',
      conf: 97,
    },
    doctor_note: 'ถุงน้ำดีขอบเรียบ ไม่พบนิ่วหรือผนังหนา เนื้อตับโดยรอบการสะท้อนคลื่นเสียงปกติ',
    polygons: [
      [0.20, 0.30], [0.45, 0.22], [0.70, 0.26], [0.82, 0.40],
      [0.85, 0.62], [0.75, 0.80], [0.50, 0.85], [0.25, 0.78], [0.15, 0.55]
    ]
  },
  {
    id: 'case3_normal_lhv',
    title: 'เคสที่ 3: ตับกลีบซ้ายและหลอดเลือดดำ (Left Hepatic Vein)',
    shortTitle: 'ตับกลีบซ้าย',
    subTitle: 'Left Lobe · Epigastric',
    image_url: '/samples/case3_normal_lhv.jpg',
    view: 'Epigastric Sagittal View (กลีบซ้าย)',
    width: 640,
    height: 480,
    liver_area: '152.0 cm²',
    s_stage: {
      stage: 'S0',
      conf: 95,
      label: 'Grade S0 — ปกติ ไม่มีความทึบเสียง',
    },
    fibrosis: {
      stage: 'F0',
      risk_tier: 'ความเสี่ยงต่ำ (Low Risk)',
      p_f2: 5,
      p_f3: 2,
      p_f4: 1,
    },
    lesions: [],
    fluke: {
      status: 'Negative',
      conf: 99,
    },
    doctor_note: 'หลอดเลือดดำตับกลีบซ้ายเปิดกว้างปกติ เนื้อตับเนียนละเอียด ไม่พบลักษณะหยาบ',
    polygons: [
      [0.25, 0.32], [0.48, 0.25], [0.72, 0.28], [0.84, 0.45],
      [0.80, 0.70], [0.60, 0.84], [0.35, 0.82], [0.18, 0.60]
    ]
  },
  {
    id: 'case4_steatosis_s1',
    title: 'เคสที่ 4: ไขมันพอกตับระยะแรกเริ่ม (Mild Steatosis S1)',
    shortTitle: 'ไขมันพอกตับ S1',
    subTitle: 'Mild Steatosis · Hepatorenal',
    image_url: '/samples/case4_steatosis_s1.jpg',
    view: 'Right Intercostal (ตับเทียบเนื้อไตขวา)',
    width: 640,
    height: 480,
    liver_area: '184.2 cm²',
    s_stage: {
      stage: 'S1',
      conf: 91,
      label: 'Grade S1 — ไขมันพอกตับเล็กน้อย (5-33%)',
    },
    fibrosis: {
      stage: 'F1',
      risk_tier: 'ความเสี่ยงต่ำ-ปานกลาง (Low-Moderate Risk)',
      p_f2: 18,
      p_f3: 5,
      p_f4: 2,
    },
    lesions: [],
    fluke: {
      status: 'Negative',
      conf: 95,
    },
    doctor_note: 'พบเนื้อตับมีความสว่าง (Increased echogenicity) เล็กน้อยเมื่อเทียบกับเนื้อไต ยังเห็นผนังหลอดเลือดชัดเจน',
    polygons: [
      [0.22, 0.35], [0.45, 0.28], [0.72, 0.28], [0.86, 0.46],
      [0.82, 0.68], [0.65, 0.84], [0.38, 0.85], [0.18, 0.65]
    ]
  },
  {
    id: 'case5_steatosis_s2_ffc',
    title: 'เคสที่ 5: ไขมันพอกตับปานกลาง S2 + ก้อนไขมัน (FFC)',
    shortTitle: 'ไขมันพอกตับ S2 + FFC',
    subTitle: 'Moderate S2 · Segment IV',
    image_url: '/samples/case5_steatosis_s2_ffc.jpg',
    view: 'Hepatorenal Interface View',
    width: 640,
    height: 480,
    liver_area: '196.8 cm²',
    s_stage: {
      stage: 'S2',
      conf: 89,
      label: 'Grade S2 — ไขมันพอกตับปานกลาง (34-66%)',
    },
    fibrosis: {
      stage: 'F2',
      risk_tier: 'ความเสี่ยงปานกลาง (Significant Fibrosis)',
      p_f2: 68,
      p_f3: 22,
      p_f4: 6,
    },
    lesions: [
      {
        type: 'Focal Fatty Change (FFC)',
        confidence: 0.88,
        size_mm: 18,
        location: 'Segment IV',
        box: [0.42, 0.46, 0.16, 0.14]
      }
    ],
    fluke: {
      status: 'Negative',
      conf: 94,
    },
    doctor_note: 'พบความสว่างของเนื้อตับเพิ่มขึ้นชัดเจน และมีรอยโรคไขมันสะสมเฉพาะจุด (FFC) บริเวณ Segment IV แนะนำคุมอาหารและออกกำลังกาย',
    polygons: [
      [0.20, 0.34], [0.48, 0.26], [0.75, 0.28], [0.88, 0.48],
      [0.82, 0.72], [0.62, 0.86], [0.32, 0.84], [0.16, 0.62]
    ]
  },
  {
    id: 'case6_benign_hemangioma',
    title: 'เคสที่ 6: ก้อนเนื้อหลอดเลือดตับ (Hepatic Hemangioma)',
    shortTitle: 'ก้อนหลอดเลือดตับ',
    subTitle: 'Hemangioma · 22 mm',
    image_url: '/samples/case6_benign_hemangioma.jpg',
    view: 'Right Hepatic Lobe Dome View',
    width: 640,
    height: 480,
    liver_area: '180.4 cm²',
    s_stage: {
      stage: 'S0',
      conf: 93,
      label: 'Grade S0 — ปกติ',
    },
    fibrosis: {
      stage: 'F1',
      risk_tier: 'ความเสี่ยงต่ำ (Low Risk)',
      p_f2: 12,
      p_f3: 3,
      p_f4: 1,
    },
    lesions: [
      {
        type: 'Hepatic Hemangioma (Benign)',
        confidence: 0.94,
        size_mm: 22,
        location: 'Right Posterior Segment VII',
        box: [0.52, 0.40, 0.15, 0.14]
      }
    ],
    fluke: {
      status: 'Negative',
      conf: 96,
    },
    doctor_note: 'พบก้อนเนื้อสว่างขอบเขตเรียบชัดเจน (Hyperechoic well-defined lesion) สอดคล้องกับ Hemangioma ชนิดไม่อันตราย แนะนำตรวจติดตาม 6 เดือน',
    polygons: [
      [0.24, 0.32], [0.50, 0.25], [0.76, 0.28], [0.86, 0.46],
      [0.82, 0.70], [0.60, 0.85], [0.35, 0.84], [0.18, 0.60]
    ]
  },
  {
    id: 'case7_cirrhosis_f4_hcc',
    title: 'เคสที่ 7: ภาวะตับแข็ง + ก้อนสงสัยมะเร็งตับ (Cirrhosis F4 + HCC)',
    shortTitle: 'ตับแข็ง F4 + ก้อน HCC',
    subTitle: 'Cirrhosis F4 · Nodule 28mm',
    image_url: '/samples/case7_cirrhosis_f4_hcc.jpg',
    view: 'Right Lobe Subcostal View',
    width: 640,
    height: 480,
    liver_area: '162.1 cm²',
    s_stage: {
      stage: 'S1',
      conf: 87,
      label: 'Grade S1 — มีไขมันร่วมกับเนื้อตับหยาบ',
    },
    fibrosis: {
      stage: 'F4',
      risk_tier: 'ภาวะตับแข็ง (Cirrhosis F4 - High Risk)',
      p_f2: 94,
      p_f3: 88,
      p_f4: 82,
    },
    lesions: [
      {
        type: 'Suspected HCC (Malignant Nodule)',
        confidence: 0.92,
        size_mm: 28,
        location: 'Segment VI',
        box: [0.45, 0.50, 0.18, 0.16]
      }
    ],
    fluke: {
      status: 'Negative',
      conf: 92,
    },
    doctor_note: 'ผิวตับหยักเป็นคลื่น (Nodular liver surface) เนื้อตับหยาบมาก สอดคล้องกับตับแข็ง F4 ร่วมกับพบก้อนเนื้อทึบเสียง (Hypoechoic nodule) ขนาด ~28 mm ส่งต่อ CT Triphasic ด่วน',
    supervisor_warning: 'ตรวจพบภาวะตับแข็ง METAVIR F4 ร่วมกับก้อนเนื้อในตับ มีความเสี่ยงสูงต่อภาวะ Hepatocellular Carcinoma (HCC) แนะนำส่งตรวจ CT/MRI Triphasic เพิ่มเติม',
    polygons: [
      [0.22, 0.36], [0.46, 0.28], [0.72, 0.30], [0.84, 0.48],
      [0.80, 0.70], [0.62, 0.84], [0.36, 0.82], [0.18, 0.64]
    ]
  },
  {
    id: 'case8_malignant_biliary_risk',
    title: 'เคสที่ 8: ก้อนเนื้อตับร้ายแรง + เสี่ยงท่อน้ำดีสูง (CCA / Malignant)',
    shortTitle: 'ก้อนเสี่ยงท่อน้ำดีสูง',
    subTitle: 'Suspected CCA · Fluke Positive',
    image_url: '/samples/case8_malignant_biliary_risk.jpg',
    view: 'Porta Hepatis / Central View',
    width: 640,
    height: 480,
    liver_area: '174.6 cm²',
    s_stage: {
      stage: 'S0',
      conf: 91,
      label: 'Grade S0 — ปกติ',
    },
    fibrosis: {
      stage: 'F3',
      risk_tier: 'พังผืดระดับรุนแรง (Advanced Fibrosis F3)',
      p_f2: 85,
      p_f3: 74,
      p_f4: 38,
    },
    lesions: [
      {
        type: 'Intrahepatic Mass (Suspected CCA)',
        confidence: 0.95,
        size_mm: 34,
        location: 'Central / Left Duct Confluence',
        box: [0.40, 0.44, 0.20, 0.18]
      }
    ],
    fluke: {
      status: 'Positive',
      conf: 96,
    },
    doctor_note: 'พบการขยายตัวของท่อน้ำดีในตับ (Intrahepatic duct dilatation) ร่วมกับก้อนเนื้อบริเวณขั้วตับ และผลประเมินพยาธิใบไม้ในตับเป็นบวก แนะนำส่งตรวจ MRCP และพบแพทย์เฉพาะทางตับและทางเดินน้ำดี',
    supervisor_warning: 'พบสัญญาณความเสี่ยงต่อพยาธิใบไม้ในตับและท่อน้ำดีอักเสบเรื้อรังร่วมกับก้อนเนื้อขนาด 34 mm แนะนำตรวจอุจจาระหาไข่พยาธิและตรวจ MRCP ด่วน',
    polygons: [
      [0.24, 0.34], [0.48, 0.26], [0.74, 0.28], [0.86, 0.46],
      [0.82, 0.72], [0.64, 0.86], [0.38, 0.84], [0.18, 0.62]
    ]
  }
]
