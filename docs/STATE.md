# STATE.md — สถานะโครงการ (ไฟล์ส่งมอบข้ามโมเดล)

> ไฟล์นี้คือ "ความจำกลาง" ของโครงการ — agent ทุกตัว (Claude/Codex/Kimi/อื่นๆ) อ่านก่อนเริ่ม
> และ**อัปเดตก่อนจบทุก session** (protocol ใน AGENTS.md) | อัปเดตล่าสุด: 5 ก.ค. 2026

## สถานะปัจจุบัน (TL;DR)

- เฟส: **Phase 0** | milestone เสร็จ: M-1, M0, M1 (gate), M2 | **กำลังทำ: M3**
- test: 44 ข้อเขียว | ต้นทุนสะสม ~$0.17 จากงบ $50/เดือน | dev stack: docker compose (postgres+pgvector, neo4j, redis)
- ข้อจำกัดบังคับ: **ทุก run ≤ 10 agents** (คำสั่งผู้ใช้ 5 ก.ค. 2026)

## แผนที่โค้ด (อะไรอยู่ไหน ทำไม)

| ที่ | คืออะไร | จุดสำคัญที่ห้ามพัง |
|---|---|---|
| `core/config.py` | Settings จาก .env | governance flags default = เปิด |
| `core/llm/` | adapter (tier crowd/analyst), pricing (fail-closed), cost guard | ทุก LLM call ต้องผ่านที่นี่ + `BudgetGuard.add_actual()` ทุกครั้ง |
| `core/run_context.py` | RunContext + gate `ensure_external_retrieval_allowed()` | hindcast_mode = block external retrieval ตาย (กฎเหล็กข้อ 2) |
| `trust/hindcast/` | loader (อ่านเฉพาะ before/), retrieval filter (fail-closed), Thai prompt filter, leak test + judge | `outcome.md` ห้ามเข้า context agent เด็ดขาด; judge parse-fail นับเป็น leak |
| `governance/pii.py` | PII detector ไทย + allow-list (`config/pii_allowlist.yaml`) | ingest ปฏิเสธรันถ้า detector ปิด; checksum เลขบัตรจริง |
| `graphlayer/` | extraction (analyst→JSON), normalize (alias map), Neo4jStore (provenance ทุก node/edge, query_indirect 2-3 hop) | relation ที่อ้าง entity นอกลิสต์ถูกตัด; MERGE idempotent |
| `simulation/` | (M3 — กำลังสร้าง) persona factory + social fabric 4 ช่องทาง | อ่าน `data/samples/population/segments.yaml` |
| `scripts/` | CLI ทุกตัว: thai_benchmark, run_leak_test, ingest_corpus | ทุกตัวประเมิน cost ก่อนเริ่ม |
| `data/benchmark/` | ชุดคำถาม leak test + Thai benchmark | leak_if ข้อ a1 มีบั๊ก premise (หนี้เทคนิค M4) |

## การตัดสินใจสำคัญ + เหตุผล (ห้ามพลิกเงียบๆ — ดู ADR เต็มใน docs/adr/)

1. **LLM = OpenRouter, crowd `qwen/qwen3.5-flash-02-23`, analyst `qwen/qwen3-235b-a22b-2507`** (ADR-0001) — flash ชนะ Thai benchmark 22/24 (จับประชด/เกรงใจได้ ซึ่งเป็นหัวใจ FAB-02); qwen-2.5-7b ตก 3/24 ห้ามกลับไปใช้; ราคาใน `config/pricing.yaml` ต้องตรง OpenRouter เสมอ
2. **M1 gate ผ่านโดยมติผู้ใช้บน human review** — อัตโนมัติค้าง 3.0% เพราะโจทย์ a1 เขียน premise ผิดข้อเท็จจริงเอง; agent ไม่เคยเผยข้อเท็จจริงหลัง cutoff ตลอด 99 คำตอบ; **สถาปัตยกรรม retrieval+prompt filter เพียงพอ ไม่ต้องใช้ model cutoff เก่า** (ตอบ Open Question #1 ของ PRD)
3. **Prompt กำกับ agent ต้องมี**: "ตอบภาษาไทยเท่านั้น" (กันตัวจีนหลุด), "ห้ามกุชื่อ/ตัวเลข — จำไม่ได้ให้บอกว่าไม่แน่ใจ เรียกคนด้วยบทบาท" (กัน hallucination), strip `<think>` tag จากคำตอบ crowd เสมอ (`trust/hindcast/leaktest.py::sanitize_answer` — M3 ควรย้ายไปใช้ร่วมกลาง)
4. **LLM judge pattern**: temperature 0 + บังคับ JSON + few-shot ตัวอย่างการตัดสิน + retry 1 ครั้งเมื่อ parse พัง + parse-fail นับเป็นผลลบแบบ conservative — ใช้ pattern นี้กับ judge ตัวถัดๆ ไป
5. **Extraction non-determinism**: OpenRouter รับ seed แบบ best-effort — entity หลักคงที่ entity รองแกว่งได้; NFR-07 freeze ที่ snapshot graph ไม่ใช่ re-run

## หนี้เทคนิค (คิวไว้ M4 ยกเว้นระบุอื่น)

- [ ] แก้ `leak_if` ของโจทย์ a1 (นับ leak เมื่อระบุชื่อจริงผู้ชนะ/ยืนยันสถานะผู้ว่าฯ) — อย่าแก้โดยไม่บอกผู้ใช้ เพราะผูกกับประวัติ gate
- [ ] รัน leak test กับเหตุการณ์ที่ 2 (`2565-true-dtac-merger`) ยืนยันผลไม่ผูกเหตุการณ์เดียว
- [ ] เพิ่ม hindcast ชุดที่ 3–5 (exit criteria ต้องผ่าน ≥ 3/5)
- [ ] ห่อ `query_indirect` เป็น REST endpoint (FastAPI ใน `api/`)
- [ ] ย้าย `sanitize_answer` จาก trust/hindcast ไป core (M3 ใช้ด้วย)

## งานปัจจุบัน: M3 — Agent Runtime + Thai Social Fabric v1

เป้าหมาย (จาก PHASE0-BRIEF): persona factory จาก `segments.yaml`, ช่องทาง 4 แบบพารามิเตอร์แพร่ต่างกัน
(closed group ช้า/trust สูง, public feed เร็ว/viral, algo feed non-network, offline word-of-mouth),
cultural priors เป็นพารามิเตอร์ agent (เกรงใจ/say-do gap/ประชด), reasoning trail + seed ทุก run

ลำดับที่วางไว้:
1. **Spike OASIS (time-box)**: ลอง integrate CAMEL-AI OASIS — ถ้าติดขัด/หนักเกินความต้องการ Phase 0
   (เราต้องการแค่ ≤10 agents round-based + 4 ช่องทาง custom) → เขียน ADR-0002 เสนอ runtime เบาเอง แล้ว**ถามผู้ใช้**
2. Persona factory: sample จาก segments.yaml ตามสัดส่วน (≤10 ตัว!), cultural priors + voice_activity ต่อตัว
3. Channel simulators 4 แบบ + rounds loop + reasoning trail
4. Benchmark AC ของ FAB-01: rumor แพร่ closed group ช้ากว่า public feed + correction เข้า closed group ช้ากว่า → รายงาน + รัน 2 seed
- Acceptance: unit tests (sampling ตามสัดส่วน, พารามิเตอร์ช่องทาง, reproducibility seed เดิม→ผลเดิม, trail ครบทุก agent) + benchmark FAB-01 ผ่าน

## บันทึกการส่งมอบ (append — บรรทัดละ session)

- 2026-07-05 (Claude Fable 5): วางแผน Phase 0 + M-1/M0/M1/M2 เสร็จ — M1 gate ผ่านโดยมติผู้ใช้ (รายละเอียด docs/reports/), M2 ได้ graph 114 entities + indirect query; สร้าง AGENTS.md + STATE.md สำหรับส่งมอบข้ามโมเดล; ถัดไป: M3 เริ่มที่ spike OASIS
