# AGENTS.md — คู่มือสำหรับ AI agent ทุกตัวที่ทำงานใน repo นี้

ไฟล์นี้คือจุดเริ่มต้นสำหรับ **ทุกโมเดล/เครื่องมือ** (Claude, Codex, Kimi, Cursor ฯลฯ)
โปรเจกต์นี้พัฒนาแบบสลับโมเดลได้ — ความต่อเนื่องอยู่ที่ไฟล์ ไม่ใช่ที่โมเดล

## ลำดับการอ่านก่อนเริ่มงาน (บังคับ)

1. `AGENTS.md` (ไฟล์นี้) — กติกากลาง
2. `CLAUDE.md` — กฎเหล็ก governance 7 ข้อ + conventions + คำสั่งหลัก (ใช้กับทุกโมเดล ไม่ใช่แค่ Claude)
3. `docs/STATE.md` — **สถานะล่าสุด**: อะไรเสร็จ ทำไมออกแบบแบบนี้ งานถัดไปคืออะไร
4. `docs/PHASE0-BRIEF.md` — backlog + checklist ของเฟสปัจจุบัน (scope = Phase 0 เท่านั้น)
5. `docs/adr/` — การตัดสินใจทางเทคนิคที่ตกลงแล้ว ห้ามพลิกโดยไม่เขียน ADR ใหม่ + ถามผู้ใช้

## หลักออกแบบที่ยึดร่วมกัน (อย่าเบี่ยง — ถ้าคิดว่าควรเปลี่ยน ให้เขียน ADR แล้วถามผู้ใช้ก่อน)

1. **Trust ก่อน feature**: ความสามารถพิสูจน์ความแม่น (hindcast, leak test, calibration) มาก่อนความสามารถจำลอง — M1 คือ gate ของทั้งโครงการด้วยเหตุนี้
2. **Fail-closed ทุกด่าน governance**: สงสัย = block (PII detector, retrieval filter, judge นับ parse-fail เป็น leak, model ไม่มีราคา = รันไม่ได้)
3. **LLM ผ่าน adapter เดียว** (`core/llm/`): business logic รู้จักแค่ tier (crowd/analyst) ไม่รู้จักชื่อ model; ทุก call ถูกคิดเงินผ่าน `BudgetGuard` — เกิน cap = abort
4. **Provenance + reproducibility**: ทุก node/edge/ผลลัพธ์ย้อนถึงไฟล์ต้นทาง+วันที่ได้; ทุก run มี seed + model version (ยอมรับว่า OpenRouter pin seed แบบ best-effort — ตัว freeze จริงคือ snapshot)
5. **วัดอย่างซื่อสัตย์**: ห้ามแก้เกณฑ์/แก้โจทย์ test เพื่อให้ผ่าน — ตัวเลขดิบบันทึกตามจริงเสมอ ข้อยกเว้นต้องผ่าน human review + มติผู้ใช้ (ดูวิธีที่ M1 ปิด gate ใน `docs/reports/M1-hindcast-poc-final.md`)
6. **ภาษาไทยเป็น first-class**: prompt, test fixture, ชุดคำถามทดสอบ ใช้ไทยจริง — และ prompt ทุกตัวสั่ง "ตอบภาษาไทยเท่านั้น" (crowd model เคยหลุดตัวจีน)
7. **Self-improvement loop**: เจอปัญหา → แก้ที่ต้นเหตุ → เขียน/อัปเดต test ครอบ → บันทึกบทเรียนลง STATE.md หรือ ADR

## ข้อจำกัดปัจจุบัน (คำสั่งผู้ใช้ — ยังมีผลจนกว่าผู้ใช้จะยกเลิก)

- **ทุก simulation run ใช้ agent ไม่เกิน 10 ตัว จนกว่าระบบจะเสร็จครบทุกเฟส** (ยืนยันซ้ำ 5 ก.ค. 2026 ตอนเริ่ม Phase 1) — ผู้ใช้เป็นคนสั่งขยายเอง ห้าม bypass cap
- งบ dev $50/เดือน, cap ต่อ run `RUN_BUDGET_USD_CAP` ใน `.env` — ทุก script ที่เรียก LLM ต้องประเมิน cost ก่อนเริ่มและผ่าน `BudgetGuard`
- Scope = Phase 0 เท่านั้น ห้ามเริ่มงานนอก scope โดยไม่ถาม

## วิธีทำงาน

- Setup: `uv sync` | Dev stack: `docker compose up -d` | Test: `uv run pytest -q` | Lint: `uv run ruff check . && uv run ruff format --check .`
- **test ต้องเขียวทั้งหมดก่อน commit ทุกครั้ง** — เขียน unit test คู่ทุก module ใหม่
- ไฟล์ชั่วคราว/ผลรัน → `.tmp/` (disposable) | secrets → `.env` เท่านั้น ห้าม log/commit
- milestone gate (เช่น M1) : รายงานผลแล้ว**หยุดรอผู้ใช้ตัดสิน** ไม่เดินต่อเอง

## Protocol ส่งมอบงาน (บังคับทุก session ทุกโมเดล)

ก่อนจบ session:
1. อัปเดต `docs/STATE.md` (ส่วน "สถานะปัจจุบัน" + เพิ่มบรรทัดใน "บันทึกการส่งมอบ")
2. ติ๊ก checklist ใน `docs/PHASE0-BRIEF.md` ตามที่คืบจริง
3. ตัดสินใจเทคนิคใหม่/พลิกของเดิม → เขียน `docs/adr/ADR-XXXX-*.md`
4. commit ทุกอย่าง (ข้อความ commit ภาษาไทย อธิบาย "ทำไม" ไม่ใช่แค่ "ทำอะไร") — working tree ต้องสะอาด
