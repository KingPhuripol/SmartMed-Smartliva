import type { StageId } from '../domain'

export interface StageLabel {
  title: string
  detail: string
}

/** Physician-facing names for each pipeline stage. */
export const STAGE_LABELS: Record<StageId, StageLabel> = {
  intake: { title: 'รับภาพเข้าระบบ', detail: 'อ่านไฟล์และวัดขนาดภาพ' },
  quality: {
    title: 'ตรวจคุณภาพภาพ',
    detail: 'เทียบความละเอียดกับเกณฑ์ขั้นต่ำ เพื่อกันผลวิเคราะห์เบี่ยงเบน',
  },
  organ: { title: 'ตรวจว่าเป็นอัลตราซาวด์ตับ', detail: 'จำแนกอวัยวะก่อนวิเคราะห์ต่อ' },
  segmentation: { title: 'หาขอบเขตตับ', detail: 'U-Net วาดขอบเขตเนื้อตับ' },
  triage: { title: 'คัดกรองปกติ / ผิดปกติ', detail: 'ตัดสินว่าต้องส่งต่อ agent หรือไม่' },
  agents: {
    title: 'Agent เฉพาะทาง 4 ตัว',
    detail: 'พังผืด · ไขมัน · รอยโรค · พยาธิใบไม้ตับ (ทำงานขนานกัน)',
  },
  supervisor: {
    title: 'ตรวจสอบความสอดคล้อง',
    detail: 'ตรวจความสอดคล้องระหว่าง agent และประเมินความเสี่ยงรวม',
  },
  report: { title: 'ประกอบรายงาน', detail: 'รวมผลทั้งหมดเตรียมให้แพทย์ตรวจสอบ' },
}
