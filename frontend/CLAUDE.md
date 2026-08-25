# SmartLiva — คู่มือสำหรับ Claude Code

ระบบช่วยอ่านอัลตราซาวด์ตับ: gated pipeline → agent เฉพาะทาง 4 ตัว → LLM supervisor →
แพทย์ตรวจสอบรายตัว → ส่งกลับไปเทรนโมเดล

**อ่าน [ARCHITECTURE.md](ARCHITECTURE.md) ก่อนแก้โค้ดใด ๆ** blueprint ฉบับเต็มอยู่ที่
`~/Desktop/SmartLIVA/2026-08-11-blueprint.md`

---

## กฎที่ห้ามละเมิด

1. **ทิศทาง dependency ห้ามย้อน** — `domain/` ← `engine/` ← `components/`
   `src/domain/` ต้องไม่ import React, ไม่ import fetch, ไม่ import อะไรจาก `engine/` หรือ `components/`
   ถ้าเผลอ import ย้อนทิศ แปลว่าวางของผิดชั้น ให้ย้ายของ ไม่ใช่เพิ่ม import

2. **พิกัดทุกอย่าง normalized 0..1** — `Region.points` เก็บเป็นสัดส่วนเสมอ
   การแปลงเป็น pixel เกิดที่เดียวคือ `components/viewer/ImageCanvas.tsx` ห้ามคำนวณ pixel ที่อื่น

3. **`StudyRecord` เขียนครั้งเดียว** — ผลจาก AI ห้ามถูกแก้หลัง pipeline จบ
   คำตัดสินของแพทย์อยู่ใน `PhysicianReview` แยกกันคนละ object เสมอ
   ถ้าเขียนทับกัน จะเสียทั้ง audit trail ทางการแพทย์และ training signal พร้อมกัน

4. **`PhysicianReview.events` append-only** — แก้ผิดคือเพิ่ม event ใหม่ ห้ามลบหรือแก้ของเดิม

5. **การปฏิเสธใช้ reason code ไม่ใช่ประโยค** — engine คืน code เท่านั้น
   ข้อความไทย/อังกฤษอยู่ใน `config/messages.ts` ที่เดียว

6. **ค่าจาก stub ต้องติดธง `simulated: true`** เสมอ และ UI ต้องแสดงป้าย "ค่าจำลอง"
   ห้ามแสดงตัวเลขจาก stub ให้ดูเหมือนผลจากโมเดลจริง — นี่เป็นเรื่องความปลอดภัยทางคลินิก ไม่ใช่เรื่องความสวยงาม

7. **`verdict: 'incorrect'` ต้องมี `reason` ที่ไม่ว่าง** — บังคับด้วย `isVerdictSettled()`
   ห้าม bypass ด้วยการซ่อนปุ่มอย่างเดียว ต้องบล็อกที่ตรรกะด้วย

8. **ทุก stage คืนสถานะแบบมีชนิด** — ห้ามคืน `null` ลอย ๆ ให้ปลายทางเดา
   ใช้ `StageStatus` + `Halt` ที่บอกว่าหยุดด่านไหนเพราะอะไร

---

## จุดต่อขยาย มีแค่ 5 interface

ทั้งหมดอยู่ใน `src/domain/` และประกอบร่างที่ `src/engine/index.ts` ไฟล์เดียว

| Interface | ไฟล์ | ใช้ทำอะไร |
|---|---|---|
| `OrganCheckRunner` | `domain/pipeline.ts` | ตรวจว่าเป็น US ตับ |
| `SegmentationRunner` | `domain/pipeline.ts` | วาดขอบตับ |
| `TriageRunner` | `domain/pipeline.ts` | normal / abnormal |
| `AgentRunner<K>` | `domain/agents.ts` | agent เฉพาะทาง |
| `SupervisorRunner` | `domain/supervisor.ts` | ตรวจซ้ำข้าม agent |

เสียบโมเดลจริง = เขียน implementation ใหม่ แล้วสลับใน `engine/index.ts` **ห้ามแก้ไฟล์ UI**

---

## คำสั่ง

```bash
npm run dev     # dev server (ใช้ผ่าน preview tools ไม่ใช่ Bash)
npm run build   # tsc -b && vite build — ต้องผ่านก่อน commit
npm run lint    # oxlint
```

TypeScript เปิด `erasableSyntaxOnly` → **ห้ามใช้ parameter properties ใน constructor**
(`constructor(private readonly x)` จะ compile ไม่ผ่าน ให้ประกาศ field แยก)
และเปิด `verbatimModuleSyntax` → import type ต้องใช้ `import type`

---

## แนวการเขียน UI

- Tailwind v4 · design token อยู่ใน `@theme` ที่ `src/index.css`
  ใช้ `bg-ai` `text-verified` `border-alert` `text-modified` แทนการ hardcode สี
- สีประจำ agent อยู่ที่ `config/agentDisplay.ts` — ใช้ค่าจากที่นั่นทั้งบนภาพ บนการ์ด และใน layer toggle
- ตัวเลขทุกตัวใส่ class `tnum` (mono + tabular) เพื่อให้อ่านเทียบกันได้
- ภาษา: UI เป็นไทย ศัพท์แพทย์คงอังกฤษ (F0–F4, S0–S3, Cyst)
- ห้ามใส่ข้อความ error เป็น string ในโค้ด — ไปที่ `config/messages.ts`

---

## เพิ่ม agent ตัวใหม่ (ตัวอย่างงานที่พบบ่อย)

1. `domain/agents.ts` — เติม `AgentId`, `AGENT_IDS`, `AgentValueMap`
2. `engine/stubs/agents/<ชื่อ>Agent.ts` — implement `AgentRunner<'ชื่อ'>`
3. `engine/stubs/agents/index.ts` — เติมเข้า `AGENT_RUNNERS`
4. `config/agentDisplay.ts` — เติมชื่อ ชื่อไทย คำอธิบาย และ**สีที่ไม่ซ้ำใคร**
5. `lib/agentFormat.ts` — เติม case ใน `formatAgentValue` / `describeAgentValue`
6. `components/review/AgentValueEditor.tsx` — เติม control ให้แพทย์แก้ค่า

การ์ด · layer toggle · รายงาน · payload ที่ส่งไปเทรน จะตามมาเองทั้งหมด ไม่ต้องแตะ

---

## สิ่งที่ยังไม่มี (อย่าเพิ่งสมมติว่ามี)

- auth / ตัวตนผู้ตรวจ (`ReviewEvent.actor` ยัง hardcode `'physician'`)
- persistence — refresh แล้วข้อมูลหายหมด ยังไม่มี backend
- การส่งข้อมูลออกจริง — ปุ่มส่งไปเทรนยังไม่ยิง network (รอเคลียร์ PDPA)
- DICOM — รับแค่ PNG/JPEG/WebP/BMP จึงไม่มี pixel spacing จริง `sizeMm` เป็นค่าประมาณ

⚠️ `config/quality.ts` เกณฑ์ resolution ยังเป็น placeholder รอตัวเลขจริงจากเครื่อง US ที่อุดร
