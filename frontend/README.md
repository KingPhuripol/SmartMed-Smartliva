# SmartLiva — Clinical Intelligence Console

ระบบช่วยอ่านอัลตราซาวด์ตับ: **gated pipeline → agent เฉพาะทาง 4 ตัว → LLM supervisor →
แพทย์ตรวจสอบรายตัว → ส่งกลับไปเทรนโมเดล**

```bash
npm install
npm run dev
```

> รุ่นนี้โมเดลส่วนใหญ่ยังเป็น stub — ไม่มีข้อมูลออกนอกเบราว์เซอร์
> ทุกค่าที่มาจาก stub ติดป้าย **"ค่าจำลอง"** บนหน้าจอ ไม่ถูกแสดงเหมือนผลโมเดลจริง

## Flow

```
อัปโหลดภาพ
   ↓ 1 intake        รับภาพ วัดขนาด
   ↓ 2 quality       ตรวจ resolution ← ไม่ผ่าน = ปฏิเสธพร้อมบอกเกณฑ์และค่าที่วัดได้
   ↓ 3 organ         ใช่ US ตับมั้ย  ← ไม่ใช่ = ให้อัปโหลดใหม่
   ↓ 4 segmentation  U-Net วาดขอบตับ
   ↓ 5 triage        normal / abnormal ← normal = ข้าม agent
   ↓ 6 agents        พังผืด · ไขมัน · รอยโรค · พยาธิใบไม้ (ขนานกัน)
   ↓ 7 supervisor    ตรวจ agent รายตัว + หา conflict + ประเมินความเสี่ยงรวม
   ↓ 8 report        แพทย์ตรวจรายตัว → ออกรายงาน / ส่งไปเทรน
```

รายละเอียดทั้งหมดอยู่ใน [ARCHITECTURE.md](ARCHITECTURE.md)

## หน้าจอ

| ส่วน | ทำอะไร |
|---|---|
| ซ้าย 60% | ภาพ + layer ของทุก agent แยกสี · เปิด/ปิดทีละ agent · เครื่องมือให้แพทย์จิ้มจุด/ลากกรอบ |
| ขวา 40% | Supervisor panel (ความเสี่ยง + conflict) → การ์ด agent ทีละตัว → รายการจุดที่แพทย์ทำเครื่องหมาย |

แพทย์ตรวจ **แยกทีละ agent** ว่าถูกหรือผิด ถ้าผิดต้องกรอกเหตุผล — ปุ่มบันทึกจะยังกดไม่ได้
จนกว่าจะมีข้อความ เพราะข้อความนั้นคือ label ที่มีค่าที่สุดสำหรับการเทรนรอบถัดไป

## ต่อโมเดลจริง

แก้ไฟล์เดียว — [src/engine/index.ts](src/engine/index.ts)

```ts
export const analysisPipeline = createPipeline({
  organCheck: stubOrganCheck,      // → httpOrganCheck('/api/v1/organ')
  segmentation: stubSegmentation,  // → httpSegmentation('/api/v1/segment')
  triage: stubTriage,              // → httpTriage('/api/v1/triage')
  agents: AGENT_RUNNERS,           // → [httpAgent('fibrosis'), ...]
  supervisor: ruleBasedSupervisor, // → llmSupervisor({ ... })
})
```

ไม่มีไฟล์ UI ไหนต้องแก้ เพราะทุกอย่างอยู่หลัง interface ใน `src/domain/`

**เงื่อนไขเดียวของ segmentation:** ต้องส่ง mask มาเป็น **polygon แบบ normalized 0..1**
ไม่ใช่ bitmap — ถ้าโมเดลออกเป็น raster ให้ทำ marching-squares ที่ backend แล้วส่ง contour มา

## ค่าที่ต้องตั้งก่อนใช้จริง

⚠️ [src/config/quality.ts](src/config/quality.ts) — เกณฑ์ resolution ขั้นต่ำยังเป็น
placeholder (512×384) **ต้องแทนที่ด้วยตัวเลขจริงจากเครื่องอัลตราซาวด์ที่อุดร**
ค่านี้คือการตัดสินใจทางคลินิก ไม่ใช่ค่าคงที่ทางเทคนิค — จึงถูกอ้างอิงไว้ในทุกรายงาน

## โครงสร้างโค้ด

```
src/
  domain/     สัญญาข้อมูล (type ล้วน ไม่มี React ไม่มี fetch) — ห้ามเปลี่ยนพร่ำเพรื่อ
  engine/     pipeline · quality gate · supervisor · stub ของโมเดล
  config/     เกณฑ์คุณภาพ · สี agent · ข้อความ · ชื่อ stage
  components/ screens · viewer · review
  lib/        geometry · การจัดรูปแบบค่า · ภาพตัวอย่างสังเคราะห์
```

## ภาพตัวอย่าง

[src/lib/demoScan.ts](src/lib/demoScan.ts) สร้างภาพ B-mode แบบ procedural จาก seed คงที่
(speckle, เนื้อตับ echogenic, portal triad, กะบังลม, cyst พร้อม posterior enhancement)
มีป้าย `SYNTHETIC B-MODE` บนภาพเอง — **ไม่ใช่ข้อมูลผู้ป่วย**
