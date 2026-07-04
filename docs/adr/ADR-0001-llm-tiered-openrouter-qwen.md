# ADR-0001: กลยุทธ์ LLM แบบ tiered ผ่าน OpenRouter (Qwen flash/max)

- **สถานะ**: Accepted (5 ก.ค. 2026) — มีเงื่อนไขทบทวน (ดูท้ายเอกสาร)
- **เกี่ยวข้อง**: TECH-DECISIONS D5, PRD SIM-07, NFR-02, กฎ Cost guard ใน CLAUDE.md

## บริบท

Phase 0 ต้องการ LLM 2 ระดับ (D5 — tiered models): model เล็ก/ถูกสำหรับ crowd agents จำนวนหลักร้อยถึงพันตัว และ model ใหญ่สำหรับ analyst agent / report / entity extraction ข้อจำกัดสำคัญ:

1. **SIM-07 / กฎเหล็ก**: ทุก LLM call ต้องผ่าน adapter layer เดียวแบบ OpenAI-compatible ห้าม hardcode provider
2. **งบ dev จำกัดมาก**: $50/เดือน, เพดานต่อ run `RUN_BUDGET_USD_CAP=5`
3. **ภาษาไทยเป็น first-class**: crowd agent ต้อง reasoning ไทยได้จริง (ประชด/เกรงใจ/บริบทวัฒนธรรม)
4. ต้นทุนเป้าหมายระยะยาว: Standard run (1,000 agents × 30 rounds) ≤ $50–80

## ทางเลือกที่พิจารณา

| ทางเลือก | ข้อดี | เหตุที่ไม่เลือก (ตอนนี้) |
|---|---|---|
| Claude Haiku 4.5 + Sonnet 5 | คุณภาพไทยดีมาก | ไม่มี OpenAI-compatible endpoint ตรงๆ (ต้องมี driver แยกใน adapter), ราคา crowd tier สูงกว่า |
| OpenAI GPT mini-class + full | OpenAI-compatible โดยกำเนิด | ราคา crowd tier ยังสูงกว่าทางเลือก Qwen ที่งบ $50/เดือน |
| **Qwen flash + max ผ่าน OpenRouter** ✅ | ถูกสุดสำหรับ crowd agents พันตัว, OpenAI-compatible, สลับ model อื่นได้ใน endpoint เดียว (Typhoon, GPT-mini class, ฯลฯ) | คุณภาพภาษาไทยยังไม่ได้พิสูจน์ → ต้อง benchmark ก่อน |

## การตัดสินใจ

- ใช้ **OpenRouter** เป็น `LLM_BASE_URL` (OpenAI-compatible) — provider เดียว, key เดียว, สลับ model ด้วย config
- **crowd agent**: Qwen รุ่น flash-tier | **analyst**: Qwen รุ่น max-tier
- model slug จริงบน OpenRouter จะถูกยืนยันตอนเติม `.env` ใน M0 (ห้ามเดา slug ล่วงหน้าในโค้ด — อ่านจาก env เท่านั้น ตาม SIM-07)
- ทุก run ต้อง pin `model_version` (slug + วันที่) ลง run config เพื่อ reproducibility (NFR-07/NFR-10)

## ผลที่ตามมา

- adapter layer เขียนครั้งเดียวรองรับทุก provider ที่ OpenAI-compatible; ถ้าอนาคตต้องใช้ Anthropic ให้เพิ่ม driver ใต้ interface เดิม (ไม่แตะ business logic)
- ความเสี่ยงคุณภาพไทยของ flash-tier ถูกยกเป็นความเสี่ยงอันดับ 2 ของแผน Phase 0 — บรรเทาด้วย benchmark ก่อนผูกมัด

## เงื่อนไขทบทวน (revisit triggers)

1. **Thai mini-benchmark ใน M0** (10–20 ข้อ: บริบทไทย, ประชด, เกรงใจ, say-do gap) — ถ้า crowd candidate ทำได้แย่กว่าเกณฑ์ที่ยอมรับได้ ให้เลื่อนไปตัวเลือกถัดไปบน OpenRouter (Typhoon / GPT-mini class) แล้วบันทึกผลต่อท้าย ADR นี้
2. leak test M1 ชี้ว่าต้องใช้ model ที่มี knowledge cutoff เก่ากว่าเหตุการณ์ hindcast → เลือก model เพิ่มเฉพาะ hindcast mode (ADR ใหม่)
3. ต้นทุนจริงต่อ Quick run เกินประมาณการ 2 เท่า → ทบทวน tier/model

## บันทึกผล benchmark (เติมใน M0)

_(ยังไม่ได้รัน — จะเติมตาราง model × คะแนน × ราคา หลังรันใน M0)_
