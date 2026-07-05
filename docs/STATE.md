# STATE.md — สถานะโครงการ (ไฟล์ส่งมอบข้ามโมเดล)

> ไฟล์นี้คือ "ความจำกลาง" ของโครงการ — agent ทุกตัว (Claude/Codex/GLM/Kimi/อื่นๆ) อ่านก่อนเริ่ม
> และ**อัปเดตก่อนจบทุก session** (protocol ใน AGENTS.md) | อัปเดตล่าสุด: 5 ก.ค. 2026

## 🔵 เริ่มตรงนี้ (พรุ่งนี้/เมื่อกลับมา)

1. อ่าน: `AGENTS.md` → ไฟล์นี้ (STATE.md) → `docs/PHASE1-BRIEF.md` (สรุปปิด Phase 1)
2. sync โค้ดล่าสุด: `git pull` (ล่าสุด commit `179a861`, tree สะอาด, 24 commits)
3. เปิด dev stack: `docker compose up -d` (postgres/neo4j/redis) — จำเป็นสำหรับ test governance
4. ยืนยันสุขภาพระบบ: `uv run pytest -q` (ต้องได้ 123 passed) ก่อนเริ่มงานใหม่
5. ต้องมี `.env` (มี OpenRouter API key) — ไม่อยู่ใน git ผู้ใช้เก็บเอง; model: crowd=qwen3.5-flash-02-23, analyst=qwen3-235b-a22b-2507
6. **cap 10 agents ยังบังคับอยู่** — ห้าม bypass จนกว่าผู้ใช้สั่งขยาย
7. เลือกงานถัดไปจาก "งานถัดไป" ด้านล่าง (Phase 2 / ขยาย scale / เก็บงานคุณภาพ) — ถ้า non-trivial เสนอ plan ให้ผู้ใช้ก่อน

**หมายเหตุความต่อเนื่องข้ามโมเดล:** ความต่อเนื่องอยู่ที่ไฟล์เหล่านี้ + git history ไม่ใช่ที่บทสนทนา —
เปิดเครื่องมือใหม่ (Codex/GLM) แล้วอ่าน 3 ไฟล์นี้ก็ทำงานต่อได้เต็มบริบท โดยไม่ต้องมีประวัติแชทเดิม

## สถานะปัจจุบัน (TL;DR)

- เฟส: **Phase 1 (Trust MVP) — ครบทุก milestone P1-M1..M6 (5 ก.ค. 2026)** 🎉 exit criteria ผ่านครบ 4/4 (ดู PHASE1-BRIEF สรุปปิดเฟส)
- API layer เริ่มแล้ว: FastAPI `api/app.py` (`make api` / `uvicorn api.app:app`) — /dashboard.json /dashboard.html /health
- **cap 10 agents คงอยู่ตลอดทุกเฟสจนระบบเสร็จสมบูรณ์** (คำสั่งผู้ใช้) — ผู้ใช้จะสั่งขยายเอง
- **GitHub: `santipongth/chimlang` (private) push แล้ว + CI (Actions) รันเขียว** — push ทุก commit ต่อจากนี้ (gh CLI login ด้วย device flow แล้ว มี workflow scope)
- test: **123 ข้อเขียว** | ต้นทุนสะสม ~$0.55 | benchmark page: docs/reports/public-benchmark.md (rebuild ด้วย `scripts/build_benchmark_page.py` หลัง hindcast/resolve ใหม่ทุกครั้ง)
- hindcast batch มี run-to-run variance (4/5 ↔ 5/5 — target เสียงก้ำกึ่งพลิกได้): เผยแพร่ทุกรอบ ห้ามเลือกรอบสวย
- ถัดไป: **Phase 2 หรือขยาย scale** (รอผู้ใช้สั่ง) — Phase 2 = Rehearsal สด (REH-01/03/04/05), Sim-to-Signal + out-of-sample harness, war room, living memory (SIM-05); หรือผู้ใช้สั่งยกเลิก cap 10 agents เพื่อวัด exit criteria cost จริง (Standard ประเมิน ~$2.49 แล้ว) + scale ทดสอบ 100–1,000 agents
- ข้อมูลสำคัญจาก fidelity dial: Standard run (1000×30×5u) ประเมิน ~$2.49 แบบ voice-sparse → exit criteria cost ≤ $80 มีแนวโน้มผ่านสบายเมื่อได้วัดจริง
- ข้อจำกัดบังคับ: **ทุก run ≤ 10 agents** (คำสั่งผู้ใช้ 5 ก.ค. 2026) — บังคับใน `PersonaFactory.sample()` แล้ว

## แผนที่โค้ด (อะไรอยู่ไหน ทำไม)

| ที่ | คืออะไร | จุดสำคัญที่ห้ามพัง |
|---|---|---|
| `core/config.py` | Settings จาก .env | governance flags default = เปิด |
| `core/llm/` | adapter (tier crowd/analyst), pricing (fail-closed), cost guard | ทุก LLM call ต้องผ่านที่นี่ + `BudgetGuard.add_actual()` ทุกครั้ง |
| `core/run_context.py` | RunContext + gate `ensure_external_retrieval_allowed()` | hindcast_mode = block external retrieval ตาย (กฎเหล็กข้อ 2) |
| `trust/hindcast/` | loader (อ่านเฉพาะ before/), retrieval filter (fail-closed), Thai prompt filter, leak test + judge | `outcome.md` ห้ามเข้า context agent เด็ดขาด; judge parse-fail นับเป็น leak |
| `governance/pii.py` | PII detector ไทย + allow-list (`config/pii_allowlist.yaml`) | ingest ปฏิเสธรันถ้า detector ปิด; checksum เลขบัตรจริง |
| `graphlayer/` | extraction (analyst→JSON), normalize (alias map), Neo4jStore (provenance ทุก node/edge, query_indirect 2-3 hop) | relation ที่อ้าง entity นอกลิสต์ถูกตัด; MERGE idempotent |
| `simulation/` | persona factory (cap guard), channels 4 แบบ, engine round-based, voice layer (private vs public) | cap ≤10 raise ที่ factory; engine deterministic เต็มรูปต่อ seed; closed group = small-world 2 partitions |
| `scripts/` | CLI ทุกตัว: thai_benchmark, run_leak_test, ingest_corpus | ทุกตัวประเมิน cost ก่อนเริ่ม |
| `data/benchmark/` | ชุดคำถาม leak test + Thai benchmark | leak_if ข้อ a1 มีบั๊ก premise (หนี้เทคนิค M4) |

## การตัดสินใจสำคัญ + เหตุผล (ห้ามพลิกเงียบๆ — ดู ADR เต็มใน docs/adr/)

1. **LLM = OpenRouter, crowd `qwen/qwen3.5-flash-02-23`, analyst `qwen/qwen3-235b-a22b-2507`** (ADR-0001) — flash ชนะ Thai benchmark 22/24 (จับประชด/เกรงใจได้ ซึ่งเป็นหัวใจ FAB-02); qwen-2.5-7b ตก 3/24 ห้ามกลับไปใช้; ราคาใน `config/pricing.yaml` ต้องตรง OpenRouter เสมอ
2. **M1 gate ผ่านโดยมติผู้ใช้บน human review** — อัตโนมัติค้าง 3.0% เพราะโจทย์ a1 เขียน premise ผิดข้อเท็จจริงเอง; agent ไม่เคยเผยข้อเท็จจริงหลัง cutoff ตลอด 99 คำตอบ; **สถาปัตยกรรม retrieval+prompt filter เพียงพอ ไม่ต้องใช้ model cutoff เก่า** (ตอบ Open Question #1 ของ PRD)
3. **Prompt กำกับ agent ต้องมี**: "ตอบภาษาไทยเท่านั้น" (กันตัวจีนหลุด), "ห้ามกุชื่อ/ตัวเลข — จำไม่ได้ให้บอกว่าไม่แน่ใจ เรียกคนด้วยบทบาท" (กัน hallucination), strip `<think>` tag จากคำตอบ crowd เสมอ (`trust/hindcast/leaktest.py::sanitize_answer` — M3 ควรย้ายไปใช้ร่วมกลาง)
4. **LLM judge pattern**: temperature 0 + บังคับ JSON + few-shot ตัวอย่างการตัดสิน + retry 1 ครั้งเมื่อ parse พัง + parse-fail นับเป็นผลลบแบบ conservative — ใช้ pattern นี้กับ judge ตัวถัดๆ ไป
5. **Extraction non-determinism**: OpenRouter รับ seed แบบ best-effort — entity หลักคงที่ entity รองแกว่งได้; NFR-07 freeze ที่ snapshot graph ไม่ใช่ re-run

## หนี้เทคนิค

- [x] ~~แก้ leak_if a1~~ (5 ก.ค. — แจ้งผู้ใช้แล้ว, comment ใน yaml ชี้ M1 final report)
- [x] ~~leak test True-DTAC~~ (0.0% ผ่าน) | ~~hindcast ชุด 3–5~~ (ครบ 5) | ~~sanitize ไป core~~
- [ ] ห่อ `query_indirect` เป็น REST endpoint (FastAPI ใน `api/`) — คิว M5 หรือ Phase 1
- [ ] exit criteria #2 (Standard run ≤ $80): วัดจริงได้เมื่อผู้ใช้ยกเลิก cap 10 agents — ระหว่างนี้มีแต่ประมาณการจาก token log
- [ ] Windows console เป็น cp1252 — ทุก script ที่ print ไทยต้องรันด้วย `PYTHONIOENCODING=utf-8` (พิจารณาใส่ใน script เองที่ M5)

## งานถัดไป: M5 — Governance Hooks (GOV-03/04 + TRUST-01 ขั้นต่ำ) — ปิดเฟส

จาก PHASE0-BRIEF:
1. Watermark module: ทุก export ฝัง visible + machine-readable (run id, วันที่, "AI simulation — not a real poll") — ทางผ่านเดียว
2. Audit log append-only ใน PostgreSQL: DB trigger กัน UPDATE/DELETE (ทดสอบกับ DB จริงใน docker ไม่ mock)
3. Prediction Registry ขั้นต่ำ: ทุก run เขียน record ≥1 (claim, ทิศทาง, confidence, วิธีวัด, วันครบกำหนด) + trigger append-only
4. ปิดเฟส: สรุปเทียบ exit criteria 3 ข้อ + อัปเดต checklist ทั้งหมด

## บทเรียนจาก M4

- ผล what-if รอบแรก CI คร่อม 0 → เผยว่า engine ไม่มี belief revision — อ่านตัวเลขดิบแล้วตามไปแก้ model ไม่ใช่แค่รายงานผ่าน/ตก
- hindcast prediction: ระบบทายถูกข้อที่สวนกระแส (โหวตนายกฯ) เพราะ agent วิเคราะห์โครงสร้างเสียง ส.ว. จาก before docs — สัญญาณว่าทำนายจากข้อมูล ไม่ใช่ sentiment
- ข้อจำกัดที่ต้องพูดตรงๆ เสมอ: เหตุการณ์ hindcast อยู่ใน training data — prior contamination ตัดไม่ได้ 100% แม้ leak test ผ่าน; ความเชื่อมั่นแท้จริงต้องมาจากเหตุการณ์อนาคต (Phase 1 Calibration Engine)

## บทเรียนจาก M3 (กัน agent ถัดไปเดินซ้ำรอย)

- benchmark FAB-01 ต้อง iterate 3 รอบกว่าจะถูก: (1) กลุ่ม LINE ตาม segment → เล็กเกินที่ n=10
  (2) วัดแบบ first-channel ในรันรวม → sample starvation; กลุ่มเดียว/คน → clique โดดไม่มีสะพาน
  ข่าวตันที่กลุ่มแรก (ผ่านแบบ degenerate — จับได้เพราะดูตัวเลขดิบ ไม่ใช่แค่ p/f)
  (3) ทางแก้: กลุ่มข้าม segment 2 กลุ่ม/คน (small-world) + วัดแบบ isolated-channel + sign test
- เกณฑ์นัยสำคัญ: ใช้ sign test (one-sided binomial) ตามถ้อยคำ AC — อย่าตั้งเปอร์เซ็นต์ ad-hoc
- voice layer พิสูจน์แล้วว่า flash แสดง say-do gap/เกรงใจ/ประชดได้จริงเมื่อส่ง priors เข้า prompt

## บันทึกการส่งมอบ (append — บรรทัดละ session)

- 2026-07-05 (Claude Fable 5): วางแผน Phase 0 + M-1/M0/M1/M2 เสร็จ — M1 gate ผ่านโดยมติผู้ใช้ (รายละเอียด docs/reports/), M2 ได้ graph 114 entities + indirect query; สร้าง AGENTS.md + STATE.md สำหรับส่งมอบข้ามโมเดล; ถัดไป: M3 เริ่มที่ spike OASIS
- 2026-07-05 (Claude Fable 5): **M3 เสร็จ** — ADR-0002 (runtime เอง, มติผู้ใช้), persona factory + cap guard, 4 channels + engine deterministic, benchmark FAB-01 ผ่าน sign test (59/60 p=5e-17; 45/58 p=1.5e-5) หลัง iterate โครงกลุ่ม 3 รอบ, voice layer เห็น say-do gap จริง; ถัดไป: M4
- 2026-07-05 (Claude Fable 5): **M4 เสร็จ** — SIM-04 fork+belief revision (delta −18.0% CI ไม่คร่อม 0), รายงาน what-if ครบ field บังคับ, hindcast 5 ชุด + batch **ผ่าน 4/5 (exit criteria #1 ✅)**, leak test True-DTAC 0.0%, แก้ leak_if a1; เหลือ M5 ปิดเฟส
- 2026-07-05 (Claude Fable 5): **M5 เสร็จ = Phase 0 ครบทุก milestone** — watermark (fail-closed, จุด export เดียว), audit log + prediction registry append-only ด้วย PostgreSQL trigger (test ยิง SQL ตรง), ครบวงจรใน run_whatif (audit→predict→finalize→watermark export ยืนยัน record ใน DB); governance store อยู่ governance/store.py, watermark อยู่ governance/watermark.py
- 2026-07-05 (Claude Fable 5): **เริ่ม Phase 1 + P1-M1..M3 เสร็จ** — fragility (5 universes, TRUST-05 บังคับจริง), calibration engine (Brier + resolution append-only + benchmark page มี variance note), provenance cards + silent majority + fidelity dial (standard ≈ $2.49); **GitHub push + CI เขียว** (`santipongth/chimlang`); ถัดไป P1-M4 Red Team Swarm
- 2026-07-05 (Claude Fable 5): **P1-M4..M6 เสร็จ = Phase 1 ครบทุก milestone** — Red Team Swarm (5 บทบาท, Attack Surface Report, GOV-05 guard), governance เฟสสอง (election mode auto-classify + no-persuasion + RBAC), Executive Dashboard (DASH-01..04) + FastAPI (/dashboard.json|html, election block ที่ API); exit criteria Phase 1 ผ่าน 4/4; tests 123 เขียว; ถัดไป Phase 2 หรือขยาย scale (รอผู้ใช้)
