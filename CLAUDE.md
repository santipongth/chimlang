# ชิมลาง (CHIMLANG) — AI Social Simulation Platform

Multi-agent social simulation สำหรับ "ซ้อมอนาคต" (Scenario Rehearsal) — จำลองปฏิกิริยาของสังคมไทยใน Digital Sandbox ก่อนตัดสินใจจริง

- คู่มือ agent ทุกโมเดล + protocol ส่งมอบงานข้ามโมเดล: @AGENTS.md | สถานะล่าสุด: @docs/STATE.md (**อัปเดตก่อนจบทุก session**)
- Spec ฉบับเต็ม: @docs/PRD-SANAM.md (PRD v1.1 — ชื่อชั่วคราวเดิม "SANAM" = ชิมลาง)
- การตัดสินใจทางเทคนิค: @docs/TECH-DECISIONS.md (อ่านก่อนเลือก library/framework ใดๆ)
- Scope ปัจจุบัน: **Phase 6 (Studio Parity — engine เลือกได้/run persistence/sources/settings)** — ดู @docs/PHASE6-BRIEF.md (Phase 0-5 ปิดครบแล้ว: ดู brief แต่ละเฟสใน docs/) ห้ามเริ่มงานนอก scope โดยไม่ถามก่อน

## โครงสร้าง repo (เป้าหมาย)

- `core/` — โครงสร้างร่วม: config, LLM adapter (SIM-07), cost estimator + budget guard
- `api/` — backend service (REST API, orchestration)
- `simulation/` — agent runtime, persona factory, social fabric channels
- `graphlayer/` — GraphRAG ingestion, knowledge graph, entity/relationship mapping
- `trust/` — prediction registry, hindcast runner, multi-universe orchestrator
- `governance/` — PII detector, watermark, audit log, election-mode policy
- `web/` — dashboard frontend
- `data/samples/` — corpus ทดสอบ (ห้ามมี PII, ไฟล์ใหญ่ให้ gitignore)
- `docs/` — PRD, ADR, brief
- `tests/` — unit + integration tests

## คำสั่งหลัก (อย่าลบ section นี้)

- Setup: `make setup` = `uv sync`
- Run dev: `make dev` = `docker compose up -d` (postgres+pgvector, neo4j, redis)
- Test: `make test` = `uv run pytest -q` — ต้องผ่านก่อน commit ทุกครั้ง
- Lint/format: `make lint` = `uv run ruff check . && uv run ruff format --check .`
- เครื่อง Windows ที่ไม่มี `make`: รันคำสั่งฝั่งขวาโดยตรง (Makefile เป็น canonical สำหรับ CI/Linux)

## กฎเหล็ก Governance (IMPORTANT — ห้ามละเมิดไม่ว่ากรณีใด)

กฎเหล่านี้มาจาก PRD Module G และ Trust Layer ถ้างานใดขัดกับกฎเหล่านี้ ให้หยุดและแจ้งผู้ใช้ ห้ามหาทางอ้อม:

1. **ห้ามเขียนโค้ดที่ ingest หรือจัดเก็บข้อมูลส่วนบุคคล (PII)** — pipeline นำเข้าข้อมูลทุกตัวต้องผ่าน PII detector และ block เมื่อพบรายชื่อบุคคล เบอร์โทร อีเมล เลขบัตร (ยกเว้นบุคคลสาธารณะในบริบทข่าว) (GOV-01)
2. **Agent external retrieval (SIM-11) ต้องปิดใน Hindcast Mode เสมอ** — ทุก code path ที่ agent ดึงข้อมูลภายนอก ต้องตรวจ flag `hindcast_mode` ก่อน และมี leak test กำกับ (TRUST-03)
3. **Prediction Registry เป็น append-only** — ห้ามมี code path สำหรับแก้ไขหรือลบ prediction record ทุก simulation run ต้องเขียน record อย่างน้อย 1 รายการ (TRUST-01)
4. **ทุก export (PDF/ภาพ/ตาราง) ต้องผ่าน watermark module** ก่อนถึงมือผู้ใช้ (GOV-03)
5. **ห้าม implement ฟีเจอร์สร้างคอนเทนต์ชักจูง** (ad copy, สคริปต์หาเสียง) จากผลจำลอง (GOV-05)
6. **Scenario ประเภทเลือกตั้ง/การเมือง**: บังคับ output ระดับ aggregate เท่านั้น ปิด Sim-to-Signal และติดป้าย simulation_estimate / not_field_poll / aggregate_only (GOV-02)
7. **Influence graph (SIM-09) ให้ผลระดับ segment ในโลกจำลองเท่านั้น** — ห้ามมี feature ที่ map ไปยังบุคคลจริง

## Engineering conventions

- **Reproducibility first**: ทุก simulation run รับ `seed`, pin `model_version` และ freeze data snapshot — run เดิมต้อง reproduce ได้จาก run id (NFR-07)
- **Traceability**: ทุกตัวเลข aggregate ต้องย้อนถึง reasoning trail ระดับ agent ได้ — เก็บ trail เสมอ อย่า optimize ทิ้ง (NFR-08)
- **LLM calls ผ่าน adapter layer เดียว** (OpenAI-compatible) — ห้าม hardcode provider หรือ model name ในโค้ด business logic (SIM-07)
- **Cost guard**: ทุก run คำนวณ cost estimate ก่อนเริ่ม และเคารพ `RUN_BUDGET_USD_CAP` จาก env — เกิน cap ให้ abort พร้อมรายงาน
- **Cap ต่อ run (อัปเดต 6 ก.ค. 2026 — ผู้ใช้สั่งขยาย scale)**: จาก 10 → **ไม่เกิน 1,000 agents/run** (ระดับ standard); ระดับ deep 5,000 ยังต้องขออนุมัติผู้ใช้ก่อน — BudgetGuard + `RUN_BUDGET_USD_CAP` เป็นด่านต้นทุนจริงทุก run เสมอ
- ภาษาไทยเป็น first-class: agent reasoning และ test fixtures ใช้ข้อความไทยจริง ระวัง tokenizer/encoding ทุกจุดที่ประมวลผลข้อความ
- Secrets อยู่ใน `.env` เท่านั้น (ดู `.env.example`) — ห้าม commit, ห้าม log, ห้ามใส่ในไฟล์นี้

## Workflow

- งาน non-trivial (หลายไฟล์ / ออกแบบใหม่): เสนอ plan ให้ approve ก่อน implement
- เขียน unit test คู่ทุก module — โดยเฉพาะ hindcast/data-cutoff logic ต้องมี adversarial leak test
- อัปเดต checklist `[ ]` ใน docs/PHASE0-BRIEF.md เมื่อ milestone คืบหน้า
- เมื่อพบว่า PRD กับความเป็นจริงทางเทคนิคขัดกัน: บันทึกเป็น ADR สั้นๆ ใน `docs/adr/` แล้วถามผู้ใช้ ห้ามตัดสินใจแทนเงียบๆ
