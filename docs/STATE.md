# STATE.md — สถานะโครงการ (ไฟล์ส่งมอบข้ามโมเดล)

> ไฟล์นี้คือ "ความจำกลาง" ของโครงการ — agent ทุกตัว (Claude/Codex/Kimi/อื่นๆ) อ่านก่อนเริ่ม
> และ**อัปเดตก่อนจบทุก session** (protocol ใน AGENTS.md) | อัปเดตล่าสุด: 5 ก.ค. 2026

## สถานะปัจจุบัน (TL;DR)

- เฟส: **Phase 0** | milestone เสร็จ: M-1, M0, M1 (gate), M2, **M3** | **ถัดไป: M4** (Injectable Events + รายงาน)
- test: 54 ข้อเขียว | ต้นทุนสะสม ~$0.19 จากงบ $50/เดือน | dev stack: docker compose (postgres+pgvector, neo4j, redis)
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

## หนี้เทคนิค (คิวไว้ M4 ยกเว้นระบุอื่น)

- [ ] แก้ `leak_if` ของโจทย์ a1 (นับ leak เมื่อระบุชื่อจริงผู้ชนะ/ยืนยันสถานะผู้ว่าฯ) — อย่าแก้โดยไม่บอกผู้ใช้ เพราะผูกกับประวัติ gate
- [ ] รัน leak test กับเหตุการณ์ที่ 2 (`2565-true-dtac-merger`) ยืนยันผลไม่ผูกเหตุการณ์เดียว
- [ ] เพิ่ม hindcast ชุดที่ 3–5 (exit criteria ต้องผ่าน ≥ 3/5)
- [ ] ห่อ `query_indirect` เป็น REST endpoint (FastAPI ใน `api/`)
- [ ] ย้าย `sanitize_answer` จาก trust/hindcast ไป core (M3 ใช้ด้วย)

## งานถัดไป: M4 — Injectable Events + รายงานพื้นฐาน (SIM-04)

จาก PHASE0-BRIEF:
1. Inject event กลาง run → fork 2 branches ด้วย seed เดียวกันถึง round N → delta + ช่วงความเชื่อมั่น (AC ของ SIM-04)
   — engine ปัจจุบัน deterministic เต็มรูปแล้ว: fork = สร้าง FabricSimulation 2 ตัว seed เดียวกัน inject ต่างกัน (ก่อน round N ต้อง identical — มี test ครอบ)
2. รายงาน markdown/HTML: สรุปรายกลุ่ม + ตัวอย่าง reasoning trail (ใช้ voice layer) + voice share vs population share
3. เคลียร์หนี้เทคนิคจากคิว: hindcast ชุด 3–5 + leak test True-DTAC + แก้ leak_if a1 (แจ้งผู้ใช้ก่อน) + REST endpoint

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
