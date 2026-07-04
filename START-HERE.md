# START HERE — ชิมลาง (CHIMLANG) Starter Pack

ชุดเริ่มต้นสำหรับส่งงานให้ Claude Code พัฒนาระบบชิมลาง (ชื่อชั่วคราวเดิมใน PRD: SANAM)

## ไฟล์ในชุดนี้

| ไฟล์ | หน้าที่ |
|---|---|
| `CLAUDE.md` | บริบทถาวรที่ Claude Code อ่านทุก session — กฎ governance, conventions, โครง repo |
| `docs/PRD-SANAM.md` | ข้อกำหนดผลิตภัณฑ์ฉบับเต็ม v1.1 (47 requirements, 8 modules) |
| `docs/TECH-DECISIONS.md` | การตัดสินใจทางเทคนิค 10 ข้อ — **ต้องติ๊กก่อนเริ่ม** (มี default ให้ทุกข้อ) |
| `docs/PHASE0-BRIEF.md` | Backlog เฟสแรก (M0–M5) + prompt สำเร็จรูป 3 ชุด |
| `.env.example` | Template ตัวแปรลับ — copy เป็น `.env` แล้วเติมค่า |

## ขั้นตอนเริ่มงาน (ประมาณ 30 นาทีก่อนแตะ Claude Code)

1. **สร้าง git repo ใหม่ (private)** แล้ววางไฟล์ทั้งหมดจากชุดนี้ตามโครงสร้างเดิม
2. **ติ๊ก docs/TECH-DECISIONS.md** — ใช้ default ได้ทุกข้อถ้าไม่มีข้อจำกัดเฉพาะ ยกเว้น D5 (เลือก LLM + งบ) ที่ต้องเติมเอง
3. **เตรียมข้อมูลตัวอย่าง** ใน `data/samples/` ตามสเปคท้าย PHASE0-BRIEF.md — อย่างน้อย corpus 10 ไฟล์ + hindcast 1 ชุด (สำคัญมาก: M1 เริ่มไม่ได้ถ้าไม่มี)
4. **สร้าง `.env`** จาก `.env.example` แล้วเติม API key — อย่า commit (`.gitignore` ต้องมี `.env` และ `data/samples/` ถ้าไฟล์ใหญ่)
5. **เปิด Claude Code ที่ root ของ repo** → กด Shift+Tab เข้า Plan Mode → วาง **Prompt 1** จาก PHASE0-BRIEF.md
6. อ่านแผนที่ Claude Code เสนอ ตอบคำถามที่มันถาม แล้วค่อย approve — จากนั้นใช้ Prompt 2 (scaffold) และ Prompt 3 (PoC hindcast) ตามลำดับ

## กติกาการทำงานกับ Claude Code ที่แนะนำ

- ใช้ Plan Mode กับทุกงานที่กระทบหลายไฟล์ — อ่านแผนก่อน approve เสมอ
- จบทุกงานใหญ่ด้วย "รัน make test แล้วแก้ที่ fail" ให้ loop ปิดตัวเอง
- M1 (PoC Hindcast) คือ gate: ถ้าไม่ผ่านเกณฑ์ leak ≤ 2% ให้หยุดทบทวนสถาปัตยกรรม Trust Layer ก่อนลงทุนต่อ
- การเปลี่ยนการตัดสินใจทางเทคนิค: แก้ที่ TECH-DECISIONS.md + เขียน ADR สั้นๆ อย่าปล่อยให้ตัดสินใจกันในแชทแล้วหายไป

## หมายเหตุเรื่องชื่อ

"ชิมลาง (CHIMLANG)" เป็น working name — สำนวนไทยหมายถึงการลองเชิงดูสถานการณ์ก่อนลงมือจริง ตรวจสอบเครื่องหมายการค้า/โดเมนก่อนใช้เปิดตัวสาธารณะ ส่วนเอกสาร PRD ยังใช้ชื่อ SANAM อยู่ (ถือเป็นชื่อเดียวกัน)
