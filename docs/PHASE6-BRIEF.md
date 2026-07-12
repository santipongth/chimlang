# PHASE 6 BRIEF — Studio Parity (engine เลือกได้ + run persistence + sources + settings)

เริ่ม 12 ก.ค. 2569 — **ผู้ใช้ approve M1-M4** ("ทำ M1, M2, M3, M4 ต่อได้เลย")
เป้าหมาย: เมนู/UI/ฟีเจอร์เทียบเท่า swarm-visionary-forge.lovable.app/studio ครบ
โดยรักษาจุดที่เราเข้มกว่า (seed determinism, BudgetGuard, PII gate, append-only, fail-closed)

## สิ่งที่ไม่เลียนแบบจาก SwarmSight (ยืนยันซ้ำ)

Math.random ไร้ seed | outcome แก้ย้อนหลัง | ไม่มี cost guard | agent พังนับต่อเงียบๆ | ingest ไร้ PII gate

## Milestones

### P6-M1 — Engine registry + Debate engine ✅ (12 ก.ค. 2569)
- [x] `simulation/engines.py`: registry {fabric, debate} — label/คำอธิบาย/cost profile/cap ต่อ engine
- [x] `simulation/debate.py`: agent LLM โพสต์โต้กันเป็นรอบ (default 3) — **seeded ทุกจุดสุ่ม**,
      JSON {content ไทย ≤60 คำ, stance, sentiment}, parse พัง = ติดธง failed ไม่ปนใน metrics (fail-closed),
      crowd tier + reasoning=False, synthesis ด้วย analyst + mechanical fallback, BudgetGuard + estimate ก่อนรัน
- [x] cap เฉพาะ debate: ≤ 40 agents/run (latency+cost — fabric ยังคง 1,000)
- [x] stance series → tipping detection (map [-1,1] → [0,1] ใช้ detector เดิม)
- [x] wizard เพิ่มขั้น "เครื่องยนต์" (การ์ดเลือก Fabric/Debate แบบ studio)

### P6-M2 — Run persistence + History + Run detail + Replay ✅ (12 ก.ค. 2569)
- [x] `core/runstore.py`: ตาราง sim_runs (run_id, engine, subject, config, payload JSONB, status) +
      debate_posts (round/agent/segment/content/stance/sentiment/failed) — operational (ลบได้)
- [x] `POST /runs` (RUN perm + election guard + PII gate ที่ subject): รัน engine ที่เลือก → เก็บผล →
      **audit + register prediction ≥1 + finalize** (กฎเหล็กข้อ 3 — UI run ก็เป็น simulation run จริง)
- [x] `GET /simruns.json` (ค้นหา/กรอง engine/status) + `GET /runs/{run_id}.json` (payload + posts)
- [x] หน้า History ใหม่ (แทน list เดิม — คิว prediction ยังอยู่) + Run detail (tabs: ภาพรวม/ดีเบต/รายงาน)
      + **Replay slider ทีละรอบ** สำหรับ debate
- [x] ลบ run ได้ (operational) — audit การลบ; prediction/audit เดิมคงอยู่ (append-only)

### P6-M3 — Sources ต่อ run (ไฟล์/URL/RSS) ✅ (12 ก.ค. 2569)
- [x] `simulation/sources.py`: run_sources + run_chunks (PG) — fetch/strip/parse RSS → **PII gate
      ทุกเอกสาร (fail-closed)** → chunk 800/overlap 100 → เก็บ
- [x] retrieval: lexical top-k (pg_trgm ถ้ามี / fallback scoring ใน Python) — บันทึกตรงๆ ว่ายังไม่ใช่
      vector search (ยังไม่มี embedding model ใน stack — เพิ่มภายหลังได้ไม่แตกโครง)
- [x] debate prompt แนบ context chunks ที่ retrieve ได้ (อ้างอิงจากเอกสารจริง)
- [x] wizard เพิ่มขั้น "แหล่งข้อมูล" (upload .txt/.md, URL, RSS) — โผล่เฉพาะ engine debate
- [x] จำกัด: ไฟล์ ≤ 2MB, ≤ 10 sources/run — กัน DoS ตัวเอง

### P6-M4 — Settings page + view preferences ✅ (12 ก.ค. 2569)
- [x] ตาราง app_settings (single-tenant row): default engine/agents/domain/rounds, default tab
- [x] `GET/PUT /settings.json` (RUN perm สำหรับเขียน) — webhook แสดงแค่สถานะ (secret อยู่ .env เท่านั้น)
- [x] หน้า Settings: ค่า default + จัดการ persona packs (ลบ/ดู) + สถานะ webhook + ลิงก์เอกสาร
- [x] wizard อ่านค่า default จาก settings

### P6-M5 — ตั้งค่า LLM ครบที่หน้า Settings (ADR-0007) ✅ (12 ก.ค. 2569 — ผู้ใช้สั่ง)
- [x] `core/secretbox.py`: เข้ารหัส/ถอด secret ด้วย Fernet + master key จาก `.env` (`CHIMLANG_SECRET_KEY`) — ไม่มี master = เก็บ key ไม่ได้ (fail-closed), master ผิด = ถอดไม่ได้ (ไม่คืนมั่ว)
- [x] API key เก็บ ciphertext ใน DB ผ่าน `PUT /settings/llm-key` (ADMIN) แยกจาก PUT ปกติ; GET แสดงแค่ masked + source (db/env/none), กรอง ciphertext ออกทุก response
- [x] ราคาโมเดลตั้ง/แก้จาก UI (ทับ yaml + เพิ่มใหม่) — fail-closed เดิมคง (ไม่มีราคา=รันไม่ได้)
- [x] งบ 2 ระดับ: ต่อรัน (ทับ .env) + **รวมต่อเดือน** (`core/llm/budget.py` — track spend สะสม, เกิน=block ก่อนรัน); debate adapter เช็คทั้งสอง + record_spend ทุกรัน
- [x] UI: ช่อง key (password + มาสก์ + เตือนถ้าไม่มี master), ตารางราคาแก้ได้, งบ + progress bar spent/cap
- [x] อัปเดตกฎเหล็ก CLAUDE.md/AGENTS.md (secret bootstrap ยัง .env; LLM key เข้ารหัสได้) + ADR-0007
- [x] tests +9 (secretbox roundtrip/fail/wrong-key, key masked ไม่รั่ว, protected key, monthly budget, override)

### P6-M6 — พูลของ persona + มุมมองที่เปิดใช้ + 3 tabs (ผู้ใช้สั่งจาก studio) ✅ (12 ก.ค. 2569)
- [x] `/personas/pool.json?pack_id=` — segments + สัดส่วนที่จะใช้จริง (default สำมะโน / pack); wizard แสดง "พูลของ persona" พับได้ (bar สัดส่วนรายกลุ่ม)
- [x] view toggles ในขั้น agents (ภาพรวมบังคับ + การถกเถียง[debate]/แผนภาพสวอร์ม/เส้นทางหลักฐาน) → เก็บใน `sim_runs.config.views` (ว่าง=ครบ)
- [x] RunDetail เพิ่ม 2 tabs + filter ตาม views: **แผนภาพสวอร์ม** (debate=stance scatter ต่อ agent, fabric=belief รายกลุ่ม) + **เส้นทางหลักฐาน** (debate=sources+chunks ที่ retrieve, fabric=tipping+trail — ซื่อสัตย์กับกลไกจริง ไม่แกล้งมี graph)
- [x] tests +3 (pool census/pack/404, views เก็บเฉพาะที่เลือก, ว่าง=ครบ)

## แผนระยะยาว (เพิ่มจากมติผู้ใช้รอบนี้)

- **MiroFish external adapter** — engine ภายนอกผ่าน engine_configs (base_url + encrypted key)
  แบบ SwarmSight; เลื่อนจนกว่าจะมี MiroFish endpoint จริงให้ทดสอบ (ไม่ ship ปุ่มที่พิสูจน์ไม่ได้)
- Vector embeddings สำหรับ sources retrieval (เมื่อเลือก embedding model ได้)
- GA hardening ชุดเดิม (ดู PHASE5-BRIEF)

## สถานะ

| M | สถานะ |
|---|---|
| M1 Engine registry + Debate | ✅ 12 ก.ค. |
| M2 Run persistence + History/Replay | ✅ 12 ก.ค. |
| M3 Sources | ✅ 12 ก.ค. |
| M4 Settings | ✅ 12 ก.ค. |
| M5 LLM config ครบ (key เข้ารหัส/ราคา/งบ) | ✅ 12 ก.ค. |
| M6 pool preview + views + 3 tabs | ✅ 12 ก.ค. |

## สรุปปิด Phase 6 (12 ก.ค. 2569) — ครบ M1..M4

เมนู/ฟีเจอร์เทียบเท่า studio แล้ว: เลือก engine (Fabric/Debate) ใน wizard, ทุก run เก็บถาวร
(History ค้นหา/กรอง + Run detail + Replay ทีละรอบ), sources ต่อ run (PII gate ทุกชิ้น),
Settings page | Dashboard เดี่ยวถูกแทนด้วย Run detail (โมเดลเดียวกับ studio) —
endpoint /dashboard.json ยังอยู่เพื่อ compat | tests 285→298 | **smoke กับ LLM จริงผ่านแล้ว** (4 agents × 2 รอบ: 8/8 posts, $0.0004, เสียงไทยมีคาแรกเตอร์
ประชด/เกรงใจจริง, stance เคลื่อน −0.38→−0.50, synthesis จาก analyst ไม่ใช่ fallback)
