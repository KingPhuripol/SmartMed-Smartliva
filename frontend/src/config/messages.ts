import type { HaltReason, QualityRejectCode, QualityWarningCode } from '../domain'

/**
 * Reject/warning codes resolved to human text.
 *
 * The pipeline never produces sentences — only codes — so every message the
 * physician sees is defined here, in both languages, and can be changed without
 * touching engine logic.
 */
export interface Message {
  en: string
  th: string
}

export const QUALITY_REJECT_MESSAGES: Record<QualityRejectCode, Message> = {
  RESOLUTION_TOO_LOW: {
    en: 'Image resolution is below the minimum required for analysis.',
    th: 'ความละเอียดของภาพต่ำกว่าเกณฑ์ขั้นต่ำที่ใช้วิเคราะห์ได้',
  },
  PIXEL_COUNT_TOO_LOW: {
    en: 'Total pixel count is too low — detail loss would bias the models.',
    th: 'จำนวนพิกเซลรวมน้อยเกินไป รายละเอียดที่หายไปจะทำให้ผลวิเคราะห์เบี่ยงเบน',
  },
  ASPECT_RATIO_OUT_OF_RANGE: {
    en: 'Aspect ratio is outside the expected range for an ultrasound frame.',
    th: 'สัดส่วนภาพอยู่นอกช่วงที่คาดว่าเป็นภาพอัลตราซาวด์ (อาจเป็นภาพครอปหรือภาพหน้าจอ)',
  },
  FILE_TOO_LARGE: {
    en: 'File exceeds the maximum accepted size.',
    th: 'ไฟล์มีขนาดเกินกว่าที่ระบบรับได้',
  },
  UNSUPPORTED_FORMAT: {
    en: 'File format is not supported.',
    th: 'ไม่รองรับไฟล์รูปแบบนี้',
  },
  IMAGE_UNREADABLE: {
    en: 'The image could not be decoded.',
    th: 'ไม่สามารถอ่านไฟล์ภาพได้ ไฟล์อาจเสียหาย',
  },
}

export const QUALITY_WARNING_MESSAGES: Record<QualityWarningCode, Message> = {
  LIKELY_RECOMPRESSED: {
    en: 'Image appears heavily recompressed — results may be less reliable.',
    th: 'ภาพน่าจะผ่านการบีบอัดซ้ำ ผลวิเคราะห์อาจเชื่อถือได้น้อยลง',
  },
  NEAR_MINIMUM_RESOLUTION: {
    en: 'Resolution is only just above the minimum.',
    th: 'ความละเอียดสูงกว่าเกณฑ์ขั้นต่ำเพียงเล็กน้อย',
  },
  UNUSUAL_ASPECT_RATIO: {
    en: 'Aspect ratio is unusual for this modality.',
    th: 'สัดส่วนภาพผิดไปจากภาพอัลตราซาวด์ทั่วไป',
  },
}

export const HALT_MESSAGES: Record<HaltReason, Message> = {
  QUALITY_REJECTED: {
    en: 'Image did not pass the quality gate.',
    th: 'ภาพไม่ผ่านการตรวจคุณภาพ',
  },
  NOT_LIVER_ULTRASOUND: {
    en: 'This does not appear to be a liver ultrasound.',
    th: 'ภาพนี้ไม่ใช่อัลตราซาวด์ตับ',
  },
  SEGMENTATION_FAILED: {
    en: 'The liver boundary could not be delineated.',
    th: 'ไม่สามารถหาขอบเขตตับได้',
  },
  ENGINE_ERROR: {
    en: 'An unexpected error occurred during analysis.',
    th: 'เกิดข้อผิดพลาดระหว่างการวิเคราะห์',
  },
  CANCELLED: {
    en: 'Analysis was cancelled.',
    th: 'ยกเลิกการวิเคราะห์',
  },
}
