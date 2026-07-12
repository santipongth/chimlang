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

## สรุปปิด Phase 6 (12 ก.ค. 2569) — ครบ M1..M4

เมนู/ฟีเจอร์เทียบเท่า studio แล้ว: เลือก engine (Fabric/Debate) ใน wizard, ทุก run เก็บถาวร
(History ค้นหา/กรอง + Run detail + Replay ทีละรอบ), sources ต่อ run (PII gate ทุกชิ้น),
Settings page | Dashboard เดี่ยวถูกแทนด้วย Run detail (โมเดลเดียวกับ studio) —
endpoint /dashboard.json ยังอยู่เพื่อ compat | tests 285→298 | หมายเหตุ: การ verify
debate engine กับ LLM จริง (ไม่ mock) ยังไม่ได้ทำใน session นี้ — smoke ครั้งแรกจะเผางบจริงเล็กน้อย
