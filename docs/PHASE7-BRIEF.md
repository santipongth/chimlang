# PHASE 7 BRIEF — News Desk + Media Diet (SIM-11 เต็มรูป)

เริ่ม 12 ก.ค. 2569 — **ผู้ใช้ approve แนวทาง "โต๊ะข่าวกลาง + media diet" + เลือก RSS + Search API ตั้งแต่ M1 + "เริ่มเลย ทำครบ M1-M4"**
เป้าหมาย: agent ใน debate ได้ข้อมูลสดจากอินเทอร์เน็ต **ผ่านโต๊ะข่าวกลาง** (ไม่ใช่ agent ยิงเน็ตเอง)
และแต่ละกลุ่มเห็นข่าวไม่เหมือนกันตาม **media diet** (channel_mix ของ segment) = จำลอง selective exposure

ผลวิจัย (12 ก.ค.): ไม่มี social simulation ไหนให้ agent ดึงเน็ตสดระหว่างรัน (OASIS/GenSim/AgentSociety
ใช้วิธี inject โดยผู้วิจัย) — persona-conditioned retrieval คือส่วน novel จริงของเรา

## หลักออกแบบ (ห้ามเบี่ยง)

1. **Agent ไม่แตะเน็ตเอง** — ทุก fetch ผ่านโต๊ะข่าวกลาง (executor เดียว, dedupe, cap จำนวน)
2. **Snapshot-first (NFR-07)**: ทุกชิ้นที่ดึงมา freeze ลง DB (url+เวลา+hash+เนื้อหา) **ก่อนใช้** —
   replay อ่านจาก DB เท่านั้น ไม่ยิงเน็ตซ้ำ
3. **Gate hindcast ทุก code path ที่แตะเน็ต** (`ensure_external_retrieval_allowed`) + leak test (กฎเหล็กข้อ 2)
4. **PII gate ทุกชิ้นแบบ fail-closed** (GOV-01) — pattern เดียวกับ sources.py (block ทั้งชิ้น + บันทึกเหตุผล)
5. Search key อยู่ `.env` (`TAVILY_API_KEY`) — ไม่มี key = โหมด RSS อย่างเดียว (degrade ไม่ใช่พัง)

## Milestones

### P7-M1 — โต๊ะข่าวกลาง + snapshot ✅ (12 ก.ค. 2569)
- [x] `simulation/newsdesk.py`: ตาราง news_items (run_id, provider, url, title, content, fetched_at, hash, channel_tags, status)
- [x] provider: RSS (รายการ feed จาก `NEWS_RSS_FEEDS` env + ต่อ run) + Tavily search adapter (ไม่มี key = ข้าม search พร้อมสถานะ)
- [x] `gather(dsn, ctx, ...)` — gate hindcast ก่อนเสมอ, PII gate ทุกชิ้น, dedupe ด้วย content hash, cap ≤ 30 items/run + ≤ 8 search queries/run
- [x] replay: `load_items(dsn, run_id)` อ่านจาก DB เท่านั้น

### P7-M2 — Media Diet รายกลุ่ม ✅ (12 ก.ค. 2569)
- [x] channel classification ต่อ item (heuristic จาก provider: RSS→public_feed หนัก, search→algo_feed หนัก — บันทึกตรงๆ ว่าเป็น heuristic)
- [x] `segment_feed(items, segment, subject, k, seed)` — คะแนน = channel_mix ของกลุ่ม × ความสด × 3-gram relevance; deterministic ต่อ seed
- [x] test: สองกลุ่มที่ mix ต่างกันเห็นชุดข่าวต่างกันจริง; seed เดิม = feed เดิมเป๊ะ

### P7-M3 — ผูกเข้า Debate + เส้นทางหลักฐาน ✅ (12 ก.ค. 2569)
- [x] debate: agent แต่ละตัวได้ "ฟีดข่าวของกลุ่มตัวเอง" ใน prompt (แยก block จากเอกสารผู้ใช้)
- [x] query intent: agent ตอบ JSON มี field `want_to_know` (optional) → โต๊ะข่าวรวบ dedupe แล้วค้นระหว่างรอบ (cap ต่อรอบ) → รอบถัดไปได้ข่าวใหม่
- [x] POST /runs: `live_news: true` (debate เท่านั้น) → gather ก่อนรัน + intent ระหว่างรอบ; payload เก็บรายการข่าว + สถานะ
- [x] UI: toggle "🌐 โต๊ะข่าวสด" ในขั้นแหล่งข้อมูล; tab เส้นทางหลักฐาน แสดงชิ้นข่าว (ที่มา+เวลา+สถานะ PII)

### P7-M4 — Governance + วัดผล + ADR-0008 ✅ (12 ก.ค. 2569)
- [x] leak test: hindcast ctx → gather ต้อง raise (ทุก provider); PII item → block
- [x] reproducibility test: replay จาก snapshot + seed เดิม = feed เดิมเป๊ะ ไม่แตะเน็ต
- [x] budget: ประเมิน token เพิ่มจาก news block เข้า estimate เดิม; search cap กันยิงรัว
- [x] ADR-0008 (สถาปัตยกรรม news desk + ข้อจำกัด heuristic channel) + STATE/security note

## ข้อจำกัดที่บันทึกตรงๆ

- channel classification เป็น heuristic จาก provider ไม่ใช่ข้อมูลจริงว่าข่าวชิ้นนั้นแพร่ช่องไหน —
  refine ได้เมื่อมีข้อมูลการแพร่จริง (item เก็บ channel_tags แยกจึงเปลี่ยน mapping ได้ไม่แตะโครง)
- Tavily คุณภาพภาษาไทยยังไม่ benchmark อย่างเป็นระบบ (ใช้ query ไทยได้ แต่ผล mixed) — ต้อง
  ทดสอบจริงเมื่อผู้ใช้ใส่ key; ไม่มี key ระบบทำงานโหมด RSS ได้เต็ม
- ข่าวจริงมีชื่อบุคคลสาธารณะ — PII allowlist บริบทข่าวครอบอยู่ (GOV-01 ข้อยกเว้นเดิม)

## Post-phase hardening addendum (15 ก.ค. 2026) ✅

งานนี้เป็น hardening ต่อจาก Phase 7 ที่ปิดแล้ว ไม่ใช่ milestone ใหม่ แต่บันทึกเป็น checklist เพื่อให้ protocol ส่งมอบข้ามโมเดลครบ:

- [x] News Desk provider success cache: เพิ่ม `news_fetch_cache` TTL 6 ชั่วโมง สำหรับ RSS/Tavily success โดยยัง snapshot failure/skipped ลง `news_items`
- [x] Migration ledger: `scripts/db_migrations.py` มี `schema_migrations` และ version `2026-07-15-run-lifecycle-newsdesk-cache`
- [x] Partial repair API: `POST /runs/{run_id}/refresh-news` และ `POST /runs/{run_id}/resynthesize` พร้อม audit และ guard queued/running
- [x] Deterministic resynthesis: rebuild synthesis/metrics จาก stored `debate_posts` โดยไม่เรียก LLM
- [x] Job Center observability: เพิ่ม `runs_24h/recent` metrics, loading skeleton, 24h run trend
- [x] Run Detail repair UX: เพิ่มปุ่ม Refresh news/Resynthesize และ reload payload หลัง repair
- [x] Tests/verification: เพิ่ม coverage cache/refresh/resynthesis; `uv run pytest -q`, ruff, format check, และ web build ผ่าน

## Post-phase hardening addendum #2 (15 ก.ค. 2026) ✅

งานนี้เป็น hardening ต่อจากคำสั่งผู้ใช้ให้ทำทุกข้อจากรีวิว core engine + frontend:

- [x] UI correctness: แก้ `SocialSignalMap` ให้นับตาม `channel_tags` จริง ไม่ fallback นับทุก provider
- [x] Pre-run Readiness & Cost Estimate: เพิ่ม `POST /runs/readiness` ผ่าน router ใหม่ `api/routers/runs.py` และแสดงใน New Run review
- [x] Run Trust Scorecard: เพิ่ม deterministic scorecard ใน run detail response และ UI
- [x] Evidence/Retrieval Upgrade: เพิ่ม rich evidence retrieval (`retrieve_evidence`) พร้อม BM25-style scoring, vector fallback metadata, citation spans, source quality, duplicate detection
- [x] Debate Engine Protocol Upgrade: เพิ่ม failure taxonomy, claim decomposition, contention graph, per-round disagreement map และ protocol rebuild ใน resynthesize
- [x] Run Lineage/Audit Trail: เพิ่ม `parent_run_id`, `run_events`, retry lineage และ audit trail ใน RunDetail
- [x] Frontend Polish: เพิ่ม readiness panel, validation target, evidence highlights, debate protocol panel, stacked 24h run trend
- [x] API Structure: เริ่มแยก router package โดยย้าย endpoint ใหม่กลุ่ม runs/preflight ออกจาก `api/app.py`
- [x] Tests/verification: `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .`, `web npm.cmd run build` ผ่าน

## Post-phase hardening addendum #3 (15 ก.ค. 2026) ✅

งานนี้เป็น production hardening จากเหตุ prediction ค้าง queued และ PostgreSQL deadlock:

- [x] แก้ schema setup contention: `RunStore.setup()` ทำครั้งเดียวต่อ process และ serialize ข้าม API/worker ด้วย PostgreSQL advisory lock
- [x] ลด AccessExclusiveLock: ไม่ `DROP/ADD sim_runs_status_check` เมื่อ constraint ปัจจุบันรองรับ lifecycle ครบแล้ว
- [x] Cancellation safety: worker เปลี่ยน run เป็น running ได้เฉพาะสถานะ queued ไม่ปลุก stale canceled task จาก Redis
- [x] Operational recovery: ล้าง retry ซ้ำ 2 งาน, เปิด Celery worker, ตรวจ ping ผ่าน และยืนยันคิวถูกดึง
- [x] Verification: concurrent endpoint stress 100/100 ได้ HTTP 200; `uv run pytest -q` ผ่าน 345 tests; ruff check/format ผ่าน
- [x] Governance: งานจริงถูก BudgetGuard block ที่ยอดเดือน `$96.01/$50.00`; ไม่ปรับเพดานโดยไม่มีมติผู้ใช้
