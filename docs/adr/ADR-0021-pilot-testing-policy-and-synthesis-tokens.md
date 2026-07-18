# ADR-0021 — นโยบายทดสอบช่วง pilot + เพดาน synthesis token ตั้งได้จาก Settings

สถานะ: Accepted
วันที่: 18 ก.ค. 2026
มติ: ผู้ใช้สั่งโดยตรง — "เพดาน synthesis ให้ตั้งจากหน้า Settings ได้" และ
"เลิกมี mock test เป็น gate ตอนนี้อยู่ในช่วงใช้งานจริง ฉันจะ test เองและถ้าพบปัญหาฉันจะแจ้ง"

## บริบท

1. เหตุการณ์ analyst truncation (run a00d908f) แสดงว่าเพดาน token ของ Executive Readout
   เป็นค่า operational ที่ขึ้นกับขนาด run/model ที่ผู้ใช้เลือก — ควรปรับได้เองแบบเดียวกับ
   model/ราคา (ADR-0006) โดยไม่ต้องแก้โค้ด
2. โครงการเข้าสู่ช่วง pilot ใช้งานจริงโดยผู้ใช้เป็นคนทดสอบหลัก — mock/stubbed test
   ที่เป็น gate ทำให้รอบงานช้าโดยไม่เพิ่มความมั่นใจเท่าการใช้งานจริง

## มติ

1. **`llm_synthesis_max_tokens` ตั้งได้จากหน้า Settings** (หมวด LLM): 0 = ใช้ default 2,000;
   ช่วงที่ยอมรับ 500–16,000; bounded retry ได้เพดาน `max(base+500, base×1.5)` อัตโนมัติ;
   cost estimate (BudgetGuard preflight + readiness) ใช้ค่า effective เดียวกัน —
   fail-closed contract ของ Executive Readout (ADR ก่อนหน้า) ไม่เปลี่ยน
2. **Mock/stubbed tests ไม่เป็น release gate ระหว่าง pilot**: CI job
   `Backend unit / mocked contracts` และ `Browser stubbed / accessibility` เป็น
   `continue-on-error` (informational — ยังรันและรายงานผล แต่ไม่ block push/merge);
   gate ที่ block เหลือ `Live integration / real API + worker processes` เท่านั้น
3. **Acceptance ช่วง pilot = ผู้ใช้ทดสอบจริงและแจ้งปัญหา** — agent ไม่ต้องรัน
   verification matrix เต็ม (multi-env/browser sweep) ก่อนส่งมอบ เว้นแต่แตะ governance
   หรือผู้ใช้สั่ง; ไม่ทำงาน calibration เพิ่มจนกว่าผู้ใช้สั่ง
4. กฎเหล็ก governance ทั้ง 7 ข้อ, BudgetGuard และ fail-closed behaviors **ไม่เปลี่ยน**

## ผลกระทบ

- แก้ข้อความ "test ต้องเขียวทั้งหมดก่อน commit ทุกครั้ง" ใน AGENTS.md/CLAUDE.md ให้สะท้อน
  นโยบาย pilot นี้ — unit tests ยังเขียน/รักษาไว้ (คุณค่า regression ยังอยู่) แต่ไม่ block การส่งมอบ
- เมื่อพ้นช่วง pilot (ผู้ใช้ประกาศ) ให้ทบทวน ADR นี้ก่อนคืนสถานะ gate
