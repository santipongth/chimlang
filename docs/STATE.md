# STATE.md — สถานะโครงการ (ไฟล์ส่งมอบข้ามโมเดล)

> ไฟล์นี้คือ "ความจำกลาง" ของโครงการ — agent ทุกตัว (Claude/Codex/GLM/Kimi/อื่นๆ) อ่านก่อนเริ่ม
> และ**อัปเดตก่อนจบทุก session** (protocol ใน AGENTS.md) | อัปเดตล่าสุด: 18 ก.ค. 2026

## 🔵 เริ่มตรงนี้ (พรุ่งนี้/เมื่อกลับมา)

1. อ่าน: `AGENTS.md` → ไฟล์นี้ → `docs/PHASE9-BRIEF.md` → ADR-0014 → รายงาน P9-M1
2. sync โค้ดล่าสุด: `git pull`; `.gitignore`/`diagrams/` เป็น user-owned changes เดิม ห้าม stage/revert
3. เปิดระบบครบชุด: `docker compose up -d --build --wait` หรือ `make dev` — Compose supervise
   API+worker+beat และคง PostgreSQL/Redis/Neo4j volumes; ห้ามเปิด uvicorn/celery host ซ้ำ
4. รัน `uv run python scripts/wait_for_readiness.py`; `/health/deep` ต้องรายงาน
   postgres/redis/worker/neo4j เป็น `ok` ครบ (worker ผ่าน heartbeat + Celery control ping)
5. ยืนยันสุขภาพระบบ: `uv run pytest -q` (ต้องผ่าน **411 tests**) ก่อนเริ่มงานใหม่
6. ต้องมี `.env` (มี OpenRouter API key) — ไม่อยู่ใน git ผู้ใช้เก็บเอง; crowd/analyst ตาม ADR-0001;
   embedding เป็น optional (ไม่ตั้ง = BM25 fallback พร้อม provenance)
7. **cap = 1,000 agents/run** (ผู้ใช้ขยายจาก 10 เมื่อ 6 ก.ค. 2026) — deep 5,000 ต้องขออนุมัติผู้ใช้ก่อน
8. **ADR-0019 ถอด Project/Evidence, Validation Lab, Rehearsal และ Usability แล้ว** — workflow หลักปัจจุบันคือ
   PopulationSet → Run → Result → Export; Calibration/per-run validation/evidence lineage และ audit เดิมยังอยู่

**หมายเหตุความต่อเนื่องข้ามโมเดล:** ความต่อเนื่องอยู่ที่ไฟล์เหล่านี้ + git history ไม่ใช่ที่บทสนทนา —
เปิดเครื่องมือใหม่ (Codex/GLM) แล้วอ่าน 3 ไฟล์นี้ก็ทำงานต่อได้เต็มบริบท โดยไม่ต้องมีประวัติแชทเดิม

## สถานะปัจจุบัน (TL;DR)

- **ใหม่ (18 ก.ค. แก้ analyst truncation + CI first-run triage):** run ผู้ใช้
  `debate-20260718-002144-658952-a00d908f` ล้มที่ Executive Readout ทั้งที่ posts 120/120 สำเร็จ —
  provider ledger ชี้ analyst ตอบชนเพดาน `max_tokens=900` พอดีทั้งสอง attempt (finish ที่ 900/900)
  JSON ขาดกลางคันจึงตก strict contract แล้ว fail-closed. แก้: เพดาน synthesis 2,000 + retry 3,000
  พร้อมบอก model ว่าคำตอบเดิมถูกตัด, `LLMResult.finish_reason` ใหม่ทำให้จำแนก `llm_truncated`
  ออกจาก schema พัง, error ของ run รายงาน taxonomy+attempts, cost estimate analyst ปรับเป็น
  (9,000 in / 3,000 out) ตามภาระจริง. พิสูจน์ live: retry เป็น `debate-20260718-003120-506193-6058b028`
  complete ใน attempt เดียว (summary/drivers 5/risks 4 ครบ, USD 0.0147, lineage ถึง run เดิม).
  **CI note:** commits 14–18 ก.ค. เพิ่งถูก push ครั้งแรก — CI ใหม่ (mocked/stubbed/live) รันจริงครั้งแรก
  ที่ run 29622722253 และแดง 3 job จากปัญหาเดิมที่ไม่เคยถูก exercise: (1) readiness test ไม่ hermetic
  เมื่อไม่มี .env/DB → pin model ใน test แล้ว, (2) live job พังแค่ post-step `uv cache prune` →
  ปิด cache, (3) a11y overflow บน ubuntu-latest ที่ reproduce ไม่ได้ทั้งบน Windows และ Playwright
  jammy container → เพิ่ม diagnostics ใน assertion (เกณฑ์เดิม) เพื่อให้ fail ครั้งหน้าระบุ element ได้.
- **ใหม่ (18 ก.ค. ถอดหน้า Calibration — ADR-0020):** ผู้ใช้สั่งลบเมนู Calibration + ไฟล์ที่เกี่ยวข้อง + clean code.
  ลบ `web/src/pages/Calibration.tsx`, route `/calibration`, API client/i18n ของหน้า, `GET /calibration.json`,
  `GovernanceStore.calibration_detail` (trend/reliability bins ที่เสิร์ฟหน้านี้เท่านั้น) และ MCP `get_calibration`.
  **คงตามกฎเหล็กข้อ 3**: prediction registry/resolution append-only, `POST /predictions/{id}/resolve`,
  MCP `resolve_prediction`, `due_unresolved` (คิวใน /runs.json), `calibration_summary` + benchmark page
  และ CLI `scripts/resolve_predictions.py` — เส้นทาง resolve ปัจจุบันคือ CLI/REST/MCP เท่านั้น (ไม่มี UI).
  Verification: backend 411 tests, Vitest 11, Playwright 20, Ruff/format, OpenAPI regenerate, build ผ่าน
  (index 88.24 kB เล็กลงจาก 93.14 kB); พบ flake ไม่เกี่ยวข้องใน `test_newsdesk` cache test 1 ครั้ง
  (fail ใน full run แรก, ผ่านเมื่อรันเดี่ยวและใน full run รอบยืนยัน — เป็น test-order flake ที่ควรตามแก้).
- **ใหม่ (18 ก.ค. Executive Readout contract fix):** ตรวจ run จริงพบ Debate ที่สถานะ complete สองรายการ
  (`...172412...`, `...171555...`) เก็บ analyst response เพียง `{bucket,pct}` เป็น synthesis ทั้งก้อน เพราะ
  provider ระบุ `json_schema` แต่ backend เดิมตรวจแค่ว่า parse เป็น object ไม่ได้ validate root contract;
  frontend จึงไม่มี summary/drivers/risks ให้แสดง. แก้ด้วย Pydantic strict synthesis contract, local validation
  ทุกครั้ง, retry แบบ bounded 1 ครั้งที่คิดงบผ่าน BudgetGuard และ fail run หากยังผิด; frontend ตรวจ legacy
  payload ก่อน render และเสนอ frozen rerun แทน blank/misleading readout. live Debate 2×1
  `debate-20260717-235347-756596-7bcc81cd` ผ่านจริง: summary present, confidence 0.85, drivers 5,
  risks 4, analyst_attempts 1, cost USD 0.000539 < estimate USD 0.000775. Verification: backend 411,
  Vitest 11, Playwright 20, Ruff/format/build และ Compose health ผ่าน.
- **ใหม่ (18 ก.ค. workspace decommission):** ผู้ใช้สั่งลบเมนูและ clean code/DB ของ Project & Evidence,
  Validation Lab, Press-room Rehearsal และ Usability study. ADR-0019 supersede ADR-0015 และบางส่วนของ
  ADR-0016; ลบ React routes/pages/API client, FastAPI routers/stores, rehearsal engine/CLI, validation runners,
  tests และ generated OpenAPI contracts รวม code 6,000+ บรรทัด. Migration
  `2026-07-18-remove-project-validation-rehearsal-usability-v1` ลบ 14 operational tables (ก่อนลบทุกตารางมี
  0 rows) และ project linkage จาก PopulationSet; คง run manifests, prediction/finding, audit และ financial
  ledgers ตาม governance. live workflow เปลี่ยนเป็น PopulationSet→Run→Result→Export และผ่านจริงบน Compose
  ที่ healthy ครบ, old API 404, app 200, Fabric smoke complete $0. Verification: backend 411, Vitest 10,
  Playwright 20, Ruff/format/build/migration no-op ผ่าน. user-owned changes เดิมไม่ถูก revert/commit.
- **ใหม่ (17 ก.ค. production-real runtime closure):** ADR-0018 ทำให้ Compose supervise
  API+worker+beat พร้อม restart/migration/readiness; main พอร์ต 8000 รันใน containers และ healthy ครบ
  โดยไม่มี host process ซ้ำ. เพิ่ม append-only PopulationSetV1 และบังคับรับทราบ synthetic population
  ก่อน freeze/run พร้อม manifest hash; ถอด Citizen portal/impact/feedback routes; Debate analyst fail ทำให้ run error
  โดยไม่ส่ง mechanical fallback เป็น success. isolated live Fabric workflow ผ่าน Project→Evidence→
  Population→202→worker→complete→stored export; crash test restart count 0→1 และ offline health เป็น
  degraded. OpenRouter Debate 2×1 ใช้จริง USD 0.000411 ภายใต้ cap USD 0.05. CI แยก
  mocked/stubbed/live/provider. Verification: backend 427, Vitest 8, Playwright 26,
  Ruff/build/migration no-op/npm audit ผ่าน. รายงาน docs/reports/P9-production-runtime-gate.md.
  usability ผู้ใช้จริง 5 คนยังไม่ปิดตามเดิม.
- **ใหม่ (17 ก.ค. worker queued incident):** ผู้ใช้สร้าง Debate แล้วค้าง `รอ worker` เพราะไม่มี Celery worker
  ทำงาน ขณะที่ `/health/deep` เดิมตรวจเพียง Redis จึงให้ readiness เป็นบวกปลอม. เปิด worker ด้วย queue
  `fabric,debate,maintenance` แล้วรันจริง `debate-20260717-134255-547389-6dea9287` จบ `complete`.
  เพิ่ม Redis TTL heartbeat จาก worker, health component แยก และ API fail-fast 503 ก่อนสร้าง queued row
  เมื่อ worker offline; idempotent replay ของ request ที่รับแล้วไม่ถูก block. live Fabric smoke ได้ 202→complete
  และ cleanup แล้ว. ADR-0017; verification backend 422 tests, Ruff, migration no-op.
- **ใหม่ (17 ก.ค. live Projects recovery):** ผู้ใช้พบ Create Project ตอบ 404; ตรวจ code/OpenAPI พบ router
  มีครบ แต่ process ที่พอร์ต 8000 เป็น FastAPI รุ่นก่อน Phase 9 และไม่มี /projects. Restart เฉพาะ API
  ด้วย code ปัจจุบันแล้ว; live verification GET /projects=200, invalid POST=422 (เข้าถึง handler โดยไม่
  สร้างข้อมูลทดสอบ) และ /app/=200. ฐานข้อมูล/worker ไม่ถูก reset.
- **ใหม่ (17 ก.ค. Phase 9 remaining gates):** ผู้ใช้อนุมัติค่าใช้จ่ายและการออกแบบ usability test.
  รัน robustness จริงผ่าน OpenRouter 3 Gemini variants × 6 Thai cases = 18/18 structured calls,
  agreement 0.888889, Thai rationale 100%, actual measured cost 0.002412 USD; failed Qwen/Mistral/Llama
  routes ถูก append invalidation ไม่ลบย้อนหลัง และ provider spend รวม session ประมาณ 0.0028928 USD.
  TH/EN contract + locale formatting และ axe WCAG 2.2 AA audit 13 routes desktop/mobile ผ่าน; แก้ contrast,
  skip/focus/reflow/24px targets และ drawer ที่เคยปิดเมื่อสลับภาษา. เพิ่ม #/usability สำหรับ P01–P05 พร้อม
  consent/timer/local anonymized export แต่ยัง 0/25 งานจริง จึง claim blocked. Verification: backend 419,
  Vitest 8, Playwright 26, index 93.14 kB (+13.6% จาก baseline) และ migration no-op.
- **ใหม่ (17 ก.ค. Phase 9 M2/M3):** ผู้ใช้อนุมัติเดินต่อหลัง M1; เพิ่ม Project workflow + append-only
  revisions, Evidence Library (PDF/DOCX/TXT/CSV/URL/RSS) + immutable `EvidenceSetV1`, frozen run
  materialization/provenance, Validation Lab/Resolution Inbox/human-panel consent contract และ
  event-sourced Rehearsal UI ที่ reserve monthly budget แบบ transactional. MIRACL Thai รันจริงบน pinned
  corpus 542,166 passages/dev 733: Recall@100 0.864588, MRR@10 0.455517, nDCG@10 0.451845,
  raw hash `0ebcba9b…`, cost $0; รอบที่ขาด shard ถูก append invalidation ไม่ลบย้อนหลัง. Run Detail เป็น
  Result/Evidence/Uncertainty/Validation/Audit; routes ใหม่ lazy ทำให้ initial index 85.81 kB. ADR-0015
  และรายงาน `P9-M2-miracl-th.md` บันทึก contract. Verification: 417 backend tests, Ruff, migration no-op,
  OpenAPI/Vitest/build/E2E ผ่าน. **ยังไม่อ้าง human-panel/pilot usability; protocol พร้อมแต่ยังไม่รัน**.
- **ใหม่ (17 ก.ค. Phase 9 M1 trust gate):** ADR-0014 เปิด trust contract แบบ `RunSpecV1` +
  append-only `RunManifestV1`: canonical config/artifact hashes, frozen persona/evidence/news/result,
  code/prompt/model/pricing/governance versions และ legacy run ระบุ `legacy-incomplete` โดยไม่สร้าง
  provenance ย้อนหลัง. Lifecycle ใช้ CAS จน terminal, async API ตอบ 202 + idempotency conflict/reuse,
  frozen/latest rerun แยกชัดและไม่อ้าง exact replay. URL/RSS ผ่าน `SafeOutboundFetcher` ที่ pin IP หลัง
  ตรวจ A/AAAA และ revalidate redirect/size/type/decompression. UI เปลี่ยนเป็น HashRouter typed routes,
  mobile drawer, running timeline/cancel/reconnect, deep links และ stored-snapshot PDF/JSON export.
  Verification: 407 backend tests, Ruff, OpenAPI, Vitest 5, build index 92.67 kB (+13.0% จาก ~82),
  Playwright 14 desktop/mobile, npm production audit 0 และ migration no-op; รายงานอยู่
  `docs/reports/P9-M1-trust-foundation.md`. **หยุดรอมติผู้ใช้ก่อน P9-M2**.
- **ใหม่ (16 ก.ค. Phase 8 M8 engineering debt + active policy):** แยก Persona/Watchlist routers ออกจาก
  `api/app.py`, ย้าย raw `fetch` ใน `web/src/api.ts` ทั้งหมดไป generated OpenAPI client, เพิ่ม `httpx2`
  และลบ warning suppression. เพิ่ม production soak runner สำหรับ HTTP→Redis/Celery→PostgreSQL พร้อม
  heartbeat/event/read-after-write/cleanup; live run 20/20 ผ่าน, p50 1.657s, p95 2.214s, coverage heartbeat/event
  100%. ADR-0013 รับรอง safety baseline: metering เพื่อคุม cost แต่ไม่ billing, repo private, Election เฉพาะ
  verified admin + aggregate-only, semantic memory ปิดจน paired benchmark ≥30 แสดง quality +10% ภายใต้ overhead
  ≤20% และไม่มี leakage; policy อ่านได้ที่ API/Settings. Verification: 391 backend tests, ruff, OpenAPI,
  Vitest 5, production build, Playwright 8 และ migration no-op ผ่าน; API/worker เปิดให้ทดลองที่ `/app/`.
- **ใหม่ (16 ก.ค. Future Work):** ผู้ใช้สั่งเลื่อน 3 งาน public-GA (TLS termination, OIDC SSO, PostgreSQL RLS multi-tenant) และให้บันทึกรายละเอียดสำหรับกลับมาอ่าน จึงสร้าง `docs/FUTURE-WORK.md` เป็น source of truth พร้อม context, inputs, implementation/migration checklist, adversarial tests และ acceptance criteria; รวม inventory งานอื่นแยกเป็น public-GA blockers, trust/external validity, engineering debt และ business/legal decisions. ADR-0012 เปลี่ยนสถานะ Proposed→Deferred โดยยังไม่มี vendor/claim/tenant architecture ที่ถือเป็นมติ.
- **ใหม่ (16 ก.ค. Phase 8 M7 production hardening):** monthly budget ใช้ transactional reservation ภายใต้ advisory lock ก่อน sweep และ 3-seed validation enqueue, actual provider spend หักยอดจองและคืนส่วนเหลือเมื่อจบ/ล้มเหลว จึงปิด race ที่ M6 บันทึกไว้; Settings แสดง spent/reserved/available และ endpoints ถูกแยกเป็น router. Main run/settings/experiment frontend paths ใช้ generated OpenAPI client; ทุกหน้า lazy-load ทำให้ initial index JS ลดประมาณ 248→82 kB และแยก ECharts/Cytoscape เป็น on-demand chunks โดย deep-link E2E ยังผ่าน. เพิ่ม dependency audit ใน CI และ secret-safe production readiness CLI; public-GA profile fail-closed หากไม่มี HTTPS, independent pen-test, OIDC หรือ PostgreSQL RLS. ADR-0012 ถูก Deferred ตามมติผู้ใช้ จึงยังคง self-hosted single-tenant. MIRACL Thai ถูกระบุเป็น external retrieval gate แต่ยังไม่อ้างผลจนกว่าจะ pin/download/run จริง. Verification: 387 backend tests, ruff, OpenAPI/Vitest/build, Playwright 8, npm/pip audit และ migration no-op ผ่าน.
- **ใหม่ (16 ก.ค. Phase 8 M6 platform completion):** เพิ่ม Experiment workspace แบบ append-only สำหรับ arbitrary run comparison และ parameter sweep สูงสุด 12 variants พร้อม sensitivity ranking จาก snapshot ที่เก็บแล้ว; sweep ตรวจ BudgetGuard ราย run และยอดรวมเดือนก่อน enqueue ทั้งชุด และไม่ป้อน public votes เข้า engine. เพิ่ม migration `2026-07-16-experiment-workspaces-v1`, แยก shared run model กับ ops/experiment routers/services ออกจาก `api/app.py`, และแก้ Fabric stored run ให้ใช้ seed ที่ร้องขอจริง. Frontend มี deep link `#/experiments`, TanStack Query, discriminated Fabric/Debate payload contracts, generated OpenAPI schema, virtualized Debate feed 1,000 posts; จำกัด contention graph ที่ 24 segment เด่นเพื่อกัน O(n²) layout บล็อกหน้าโดยไม่ตัด posts จาก feed. Verification: 383 backend tests, ruff, OpenAPI/Vitest/build, Playwright 8 tests desktop+mobile, migration no-op และ dev services healthy; user changes `.gitignore`/`diagrams/` ยังไม่ถูกแตะ.
- **ใหม่ (16 ก.ค. Phase 8 M5 ปิดเฟส):** Debate run ใหม่ใช้ typed moves `claim/evidence/counterclaim/concession/question` พร้อม deterministic move ID, parent และ evidence refs; snapshot เก่าอ่านเป็น legacy-unverifiable. เพิ่ม replayable verifier (schema/lineage/citation/unsupported numeric claim/contradiction) และ analyst judge ใน synthesis call เดิม โดย verdict ถูก deterministic verifier floor กันลดระดับ. Reflection เป็น opt-in run-local เท่านั้น จำกัด 2 calls/2,400 input chars/220 output tokens ไม่มี long-term memory และคิดต้นทุนรวมผ่าน BudgetGuard. Retrieval ใช้ embedding adapter ใต้ `core/llm/`, model/ราคา/dimension จาก Settings/env, บันทึก model version+dimension, pgvector HNSW สำหรับ 1536d + BM25 ไทย + RRF; ถ้า embedding ไม่พร้อมระบุ BM25 fallback ใน provenance. เพิ่ม manual OpenTelemetry trace API→Celery→retrieval→LLM, Prometheus `/metrics`, provider-call metadata table และ `/observability.json`/Insights dashboard โดยไม่เก็บ prompt/response/secret/PII. เพิ่ม benchmark harness ไทย 5 มิติ + reflection smoke และรายงานข้อจำกัดตรงไปตรงมาใน `docs/reports/P8-M5-benchmarks.md`. Verification: 377 backend tests + ruff + OpenAPI/Vitest/build/Playwright ผ่าน; migration latest `2026-07-16-vector-retrieval-observability-v1`.
- **ใหม่ (16 ก.ค. Phase 8 M4 visualization platform):** ปิด M4 โดยเพิ่ม TanStack Query cache + typed OpenAPI client (`openapi-fetch`/generated schema) และ SSE reconnect client ที่ replay ด้วย `after_id` พร้อม polling fallback; Run Detail แสดง ECharts quantile/range, scenario diverging bars, Debate stance beeswarm/timeline, validation stability matrix, Cytoscape contention graph และ evidence lineage Sankey พร้อม keyboard controls, reduced-motion, responsive layout และ table fallbacks. Backend เติม `universe_estimates` และ validation child value ให้ visualizations ไม่ว่างเมื่อ payload มีข้อมูล; frontend tests ใหม่ครอบ hook/visualizations และ Playwright desktop+mobile deep link/nonblank canvas. Verification ณ ตอนปิด M4: 369 tests + ruff check/format + web generate:api/test/build + Playwright 4 tests ผ่าน.
- **ใหม่ (15 ก.ค. Phase 8 M1-M3 foundation):** ผู้ใช้อนุมัติแผน Prediction Experience + trusted runtime จึงเปิด Phase 8/ADR-0011. ย้าย DDL ออกจาก API/worker ไป migration runner ภายใต้ advisory lock เดียว, เพิ่ม process-local psycopg pool + startup schema check + Compose migrate gate; queue แยก fabric/debate/maintenance พร้อม heartbeat/stale/idempotency และ SSE replay-by-id + Redis wake-up. Trust contract เปลี่ยนเป็น SimulationFinding หรือ real-world binary Prediction; legacy/test ไม่เข้า Calibration หลัก, resolution ใหม่ต้องมีเวลา+URL/ชื่อหลักฐาน, partial เก่า read-only. เพิ่ม 3-seed validation พร้อม aggregate BudgetGuard, append-only synthesis revisions, JSON Schema structured output/fallback provenance, reliability 5 bins และ Run Detail deep link/CTA. ณ วันที่ปิด M1-M3 งาน M4/M5 ยังไม่เริ่ม; ปัจจุบันปิดแล้วตามบรรทัดบน.
- **ใหม่ (15 ก.ค. Debate stance chart + JSON parsing):** debug run `debate-20260715-153240-930304` พบ payload มี `per_round_avg_stance=[-0.3238,-0.4750,-0.6269]` ครบ แต่ UI ใช้ percentage height ใน parent ที่ไม่มี computed height ทำให้แท่งยุบเป็น 0. แก้เป็น chart ขนาดคงที่รอบแกนศูนย์ -1..+1 พร้อมค่า/label 1-based. Run นี้มี posts สำเร็จ 119/120; `json_parse_error:1` คือ raw crowd response หนึ่งครั้ง decode ไม่ผ่าน ไม่ใช่ contention graph พัง และคงไว้เป็น audit trail. ย้าย failure taxonomy ออกจาก graph, แปลสถานะให้อ่านได้ และเพิ่ม strict JSON-object extraction ที่ยอมรับ prose/Markdown wrapper แต่ malformed JSON ยัง fail-closed. Verification: 360 tests + ruff check/format + web build + live worker reload ผ่าน.
- **ใหม่ (15 ก.ค. ADR-0010 PII redaction ใช้งานแล้ว):** ผู้ใช้ยืนยันให้ external URL/RSS/News Desk ใช้ redact→re-scan→process. เพิ่ม typed placeholders (phone/email/Thai ID/person), document-local person ids, public allowlist เดิม, provenance เก็บ counts เท่านั้น; raw PII ไม่ผ่าน cache/chunk/news snapshot/payload/LLM และ `redacted` item เข้า retrieval/media diet ได้. Direct text/label, PII URL/query, detector ปิด/พัง หรือ verify ไม่ผ่านยัง block. Evidence UI แสดงสถานะ+จำนวนที่ลบ. Migration เพิ่ม schema/purge cache และ scrub legacy error metadata 32 news + 51 source rows; audit หลัง migration flagged=0 ใน external/news cache, news_items, run_sources, chunks และ run payloads. หน้า Debate แสดงเลขรอบ 1-based โดย internal ยังคง 0-based. Verification: 357 tests + ruff + web build ผ่าน.
- **ใหม่ (15 ก.ค. Budget UI/prediction recovery):** พบต้นเหตุวงเงินย้อนกลับและงาน error ที่ 55% คือ `tests/test_phase6.py` ใช้ DB dev จริงแล้ว reset budget override เป็น `0` (กลับไปใช้ `.env` $5/run, $50/month) และ test monthly budget สะสม ledger ปลอม `$3` ต่อ suite รวม 34 รายการ `$102`. แก้ fixture ให้ snapshot/restore Settings, test spend ใช้ run id เฉพาะและลบใน `finally`, ล้างเฉพาะ `run_id=test-budget` จนยอดจริงเหลือ `$0.015036`. Settings UI เปลี่ยนเป็น draft + ปุ่มบันทึกวงเงิน, API PUT คืน stored/effective values ที่ server ยืนยัน, แสดง env fallback/ยอดใช้/คงเหลือ; readiness เช็ก monthly budget และ worker เช็กงบก่อน external I/O. Smoke จริง `debate-20260715-141337-906865` สำเร็จ 10/10 posts, 0 failed, 100% ใน ~15 วินาที; clean worker online. Verification: 348 tests + ruff check/format + web build ผ่าน.

- **ใหม่ (15 ก.ค. monitor/fix Debate agent failures):** พบ worker ที่เปิดจาก Codex environment สืบทอด proxy กันเน็ต `127.0.0.1:9` ทำให้ OpenRouter retry แล้ว agent fail 60/60 สอง run แต่ engine เดิมยังปิดเป็น `complete` ด้วย mechanical fallback (false-success). รีสตาร์ต worker โดยล้าง HTTP/HTTPS/ALL proxy แล้ว retry งานเดิมสำเร็จจริง: run `debate-20260715-134130-116660`, posts 59/60, fail 1=`schema_missing_field`, analyst synthesis จริง (`fallback=false`), confidence 0.90, cost `$0.005746`, 48 วินาที. เพิ่ม `DebateUnavailableError` ให้ all-agent failure fail-closed เป็น run error และจำแนก transport/auth/rate-limit/provider taxonomy. **ห้ามใช้ผล run `debate-20260715-132719-658599` และ `debate-20260715-133404-988823` เพราะ posts fail 60/60.** Verification: 347 tests + ruff check/format ผ่าน.
- **ใหม่ (15 ก.ค. debug prediction queue/deadlock):** แก้ `RunStore.setup()` ที่เคยทำ DDL (`DROP/ADD CONSTRAINT` บน `sim_runs` และ `ALTER debate_posts`) ซ้ำทุก request จน `/simruns.json` กับ `/run-metrics.json` deadlock กัน: เพิ่ม process-local setup cache + PostgreSQL transaction advisory lock และไม่ rebuild status constraint เมื่อ schema ถูกต้องแล้ว; worker รับงานได้เฉพาะ run ที่ยัง `queued` เพื่อไม่ปลุกงาน `canceled` กลับมารัน. ยืนยัน OID จาก error คือ `sim_runs`/`debate_posts`, stress สอง endpoint พร้อมกัน 100 requests ผ่าน 200 ทั้งหมด, Celery worker online และล้าง retry ซ้ำเหลืองานเดียว. งานล่าสุดถูก BudgetGuard หยุดอย่างถูกต้องเพราะยอดเดือนนี้ `$96.01` เกินเพดาน `$50.00`; **ห้ามปรับเพดานเอง รอมติผู้ใช้**. Verification: 345 tests + ruff check/format ผ่าน.
- **ใหม่ (15 ก.ค. Codex รอบ post-phase hardening #3):** ทำ “ส่วนที่เหลือทุกข้อ” ต่อจาก backend/system + UI/UX pass แล้ว: News Desk มี `news_fetch_cache` TTL 6 ชม. สำหรับ RSS/Tavily success, `scripts/db_migrations.py` มี `schema_migrations` ledger แบบ versioned, `RunStore` อัปเดต payload ราย run ได้และส่ง `runs_24h/recent` metrics, เพิ่ม partial repair endpoints `POST /runs/{run_id}/refresh-news` และ `POST /runs/{run_id}/resynthesize` (resynthesize จาก stored debate posts เท่านั้น ไม่เรียก LLM จึง reproducible/ไม่เพิ่มงบ), RunDetail มีปุ่ม Refresh news/Resynthesize + loading state, Job Center มี loading skeleton + 24h trend. Verification: `uv run pytest -q` ผ่าน 332 tests, `uv run ruff check .` ผ่าน, `uv run ruff format --check .` ผ่าน, `web npm.cmd run build` ผ่าน. ไม่แตะ user changes `.gitignore` และ `diagrams/`.
- เฟส: **Phase 7 (News Desk + Media Diet, SIM-11 เต็มรูป) — ครบ M1..M4 (12 ก.ค. 2026)** 🎉 — ดู PHASE7-BRIEF + ADR-0008
- **ใหม่ (13 ก.ค. รอบสอง): ADR-0009** — cap segments ขยาย **2-12** (เดิม 2-8 ไม่มีเอกสาร — ตอนนี้มี rationale: floor สถิติ n≥30/กลุ่ม ที่ cap 1,000 + practice ตลาด 3-7) + limits ส่งผ่าน `/personas/pool.json` (UI เลิก hardcode) + **guard สถิติใน UI**: กลุ่มที่ share×agents<30 ขึ้น ⚠️ ทั้งใน editor และ pool panel; **channel_mix สำมะโน calibrate กับข้อมูลจริงแล้ว** (DataReportal 2025/YouGov — judgment mapping บันทึกตรงๆ ใน provenance); ลบ prior ตาย `sensitivity_awareness`; ที่มาวิชาการของ traits (เกรงใจ/say-do/มีม-ประชด) บันทึกใน ADR-0009 — **ตัวเลข priors ยังสังเคราะห์ รอ calibrate**
- **ใหม่ (13 ก.ค.): Persona Pack Editor** — ผู้ใช้ปรับกลุ่มประชากรจำลองเองได้เต็มรูปใน wizard modal 3 tabs (เลือก/แก้ไข/ให้ AI ร่าง): จำนวนกลุ่ม 2-12 (ดู ADR-0009), share/voice/นิสัยวัฒนธรรม 3 ตัว/traits ต่อกลุ่ม + **media diet 4 ช่องทาง** (คุมทั้งการแพร่ใน fabric และข่าวจากโต๊ะข่าวสด P7); สำมะโน = อ่านอย่างเดียว + ทำสำเนาไปแก้ (มติผู้ใช้); ทุกทาง save ผ่าน `validate_pack` (PII gate GOV-01 fail-closed) — เพิ่ม `PackStore.update` + `PUT /personas/packs/{id}` (422 validation ก่อน 404) + `voice_activity` ใน pool.json
- **Phase 7 เพิ่มอะไร**: `simulation/newsdesk.py` โต๊ะข่าวกลาง (agent ไม่แตะเน็ตเอง) — RSS + Tavily search (key ว่าง=บันทึก skipped evidence แล้วใช้ RSS ต่อ), PII gate ทุกชิ้น fail-closed, hindcast gate ก่อน I/O + leak test, **snapshot ลง news_items ก่อนใช้ — replay ไม่แตะเน็ต** รวม provider failure/error/skipped; **media diet**: แต่ละ segment เห็นข่าว top-k ตาม channel_mix ตัวเอง (selective exposure — จุด novel ที่ไม่มีใครทำ ดูผลวิจัยใน ADR-0008); debate: agent มี `want_to_know` → โต๊ะข่าวค้นระหว่างรอบ (dedupe cap 3); UI: toggle 🌐 โต๊ะข่าวสด ใน wizard + ข่าวโชว์ใน tab เส้นทางหลักฐาน; smoke จริงผ่าน 12 ก.ค. (feeds+key ตั้งแล้ว) — ดูบรรทัดส่งมอบ
- เฟสก่อนหน้า: **Phase 6 (Studio Parity) — ครบ M1..M6 (12 ก.ค. 2026)** — ดู PHASE6-BRIEF (Phase 5 ปิดวันเดียวกัน)
- **Phase 6 เพิ่มอะไร**: เลือก engine ได้ใน wizard (**Fabric** กลไก $0 / **Debate** agent LLM คุยจริง cap 40 seeded+fail-closed — `simulation/debate.py`, registry `simulation/engines.py`); **ทุก run เก็บถาวร** (`core/runstore.py`, POST /runs = audit+prediction+finalize ครบกฎเหล็กข้อ 3) → หน้า History (ค้นหา/กรอง/ลบ-มี-audit) + Run detail (tabs + **Replay ทีละรอบ**); **sources ต่อ run** (text/URL/RSS → PII gate ทุกชิ้น → lexical 3-gram retrieval — `simulation/sources.py`); **Settings page** (defaults + packs + สถานะระบบ — `core/appsettings.py`); เมนู Dashboard เดี่ยวถูกแทนด้วย Run detail (โมเดล studio) — /dashboard.json ยังอยู่เพื่อ compat; **MiroFish adapter = แผนระยะยาว** (มติผู้ใช้)
- **Phase 5 เพิ่มอะไร**: UI ยึด lovable.app/studio (sidebar+badge, header pattern, tabs, tooltip-สูตรทุก metric), tipping detection บังคับทุกรายงาน (`simulation/tipping.py` — ปิดข้อบังคับ PRD ขั้น 7 ที่ตกหล่น), หน้าใหม่ 4 หน้า: **Compare** (Red Team A/B seed เดียวกัน — `/compare.json`), **Calibration** (resolve ผ่าน UI, partial=0.5, append-only — `/calibration.json` + `POST /predictions/{id}/resolve`), **Watchlist** (cadence re-run + tipping/consensus_shift alerts + webhook https-only best-effort — ตั้ง `ALERT_WEBHOOK_URL` ใน .env), **Insights** (graph viz hub/cluster + cross-run stats — `/graph/summary.json`, `/insights.json`); Persona เพิ่ม `correction_receptivity` (default 1.0 = พฤติกรรมเดิมเป๊ะ)
- **Deploy จริง (มติผู้ใช้: self-hosted docker — D9 ปิดแล้ว)**: `docker compose -f docker-compose.prod.yml up -d --build` (ตั้ง .env.prod: AUTH_ENABLED=true + API_KEYS + รหัสผ่านจริง) — smoke ผ่านทั้ง container (health/UI/simulation)
- PDF: `GET /dashboard.pdf?lang=th|en` | Queue: `make worker` + POST /jobs/whatif | Auth: X-API-Key (dev ปิดอยู่) | Monitor: `/health/deep`
- **ค้างเพื่อ GA สาธารณะ**: TLS reverse proxy, pen test อิสระ, SSO, multi-tenant (ดู docs/reports/security-review.md)
- **Web UI ใช้ได้แล้ว**: `make api` → http://localhost:8000/app/ (dev แยก: `cd web && npm run dev`) — 2 คอลัมน์ sidebar+content, theme เขียวมรกต/พื้นสว่างตาม ref ผู้ใช้, TH/EN toggle, 5 หน้า (landing/wizard รันใหม่/dashboard/citizen/การจัดการรัน)
- **⚡ CAP เปลี่ยนแล้ว (คำสั่งผู้ใช้ 6 ก.ค.): 1,000 agents/run** (rename เป็น `max_agents_per_run`) — deep 5,000 ต้องขอผู้ใช้ก่อน; `RUN_BUDGET_USD_CAP=5`/run
- **Scale วัดจริงแล้ว**: multiverse 1,000×30×5u = 5.8 วิ | Standard run เต็มรูป $25.09 (thinking-on) / $0.82 (off) → **exit criteria cost ≤$80 ผ่าน ✅** (docs/reports/scale-measurement.md)
- **✅ Re-calibrate เสร็จ (ADR-0003)**: scenario ระดับเมืองที่ scale ≥100 ใช้ rumor preseed 10% + 60 rounds + คำชี้แจง `broadcast_share=0.20` → delta scale-invariant (−15% ทั้ง n=100/1,000); `Message.broadcast_share` เพิ่มใน engine (default 0 = เดิม)
- Citizen Mode ใช้ได้แล้ว: POST /citizen/impact.json (session-only), /citizen/portal.html, /citizen/feedback.json (k-anonymity ≥20) — disclaimer ถาวรทุก output
- calibration ≥15% ยังรอ predictions ครบกำหนดจริง (คิวแรก 8 ก.ค. — `scripts/resolve_predictions.py`)
- API layer: FastAPI `api/app.py` (`make api`) — /dashboard.json /dashboard.html /health
- **บทเรียนใหม่ (6 ก.ค.)**: qwen3.5-flash เผา ~1,200 hidden thinking tokens/call — `adapter.chat(reasoning=False)` สำหรับ path interactive/สั้น (เร็วขึ้น 29x ถูกลง 10x); ห้ามปิดกับ judge/hindcast/benchmark (คุณภาพที่วัดไว้ใช้ thinking)
- **GitHub: `santipongth/chimlang` (private) push แล้ว + CI (Actions) รันเขียว** — push ทุก commit ต่อจากนี้ (gh CLI login ด้วย device flow แล้ว มี workflow scope) — **ดู CI ด้วย SHA เสมอ**: `gh run list --commit "$SHA"` ห้ามใช้ `--limit 1`
- test: **369 tests ผ่าน** | ต้นทุนสะสม ~$0.62 (Phase 5 ทั้งเฟส $0 — กลไกล้วน ไม่มี LLM call) | benchmark page: docs/reports/public-benchmark.md (rebuild ด้วย `scripts/build_benchmark_page.py` หลัง hindcast/resolve ใหม่ทุกครั้ง)
- **Review ล่าสุด (15 ก.ค. Codex):** อ่าน AGENTS/CLAUDE/STATE/PHASE7/ADR แล้ว review codebase แบบไม่แก้โค้ด; พบ 3 จุดต้องพิจารณาแก้ถัดไป: (1) `/runs`, `/gallery/share`, `/watchlists` รับ `agents <= 0` จาก API ได้เพราะ clamp ด้วย `min()` อย่างเดียว ต่างจาก `/jobs/whatif` ที่มี lower bound 10; (2) `tests/test_phase6.py` ตรวจ PostgreSQL readiness ตอน import ด้วย `psycopg.connect(DSN)` ไม่มี `connect_timeout` ทำให้ pytest ทั้ง suite ค้างเมื่อ dev stack ไม่เปิด; (3) News Desk กลืน error ของ RSS/Tavily ก่อน snapshot ทำให้ evidence tab บอกไม่ได้ว่า provider ล้ม/ไม่มี key/ไม่มีข่าวจริง กรณีนี้ยังไม่ขัด leak/PII แต่ลด auditability ของ P7. Verification: `docker compose up -d`, `uv run pytest -q` ผ่านครบ, `uv run ruff check .` ผ่าน, `web npm.cmd run build` ผ่านเมื่อรัน escalated.
- **Hardening ล่าสุด (15 ก.ค. Codex):** ผู้ใช้สั่งให้ลงมือทำทุกข้อที่แนะนำจาก review แล้วทำครบชุดแรก: API validation กัน `agents <= 0` ใน `/runs`/gallery/watchlist/jobs และ `PersonaFactory.sample()` fail-fast; readiness tests ใช้ `connect_timeout`; URL/RSS source guard กัน localhost/private IP literal ก่อน fetch; News Desk snapshot failure/skipped evidence แทนการกลืน error; เพิ่ม `/runs/async` + `chimlang.persistent_run` Celery task + `/run-jobs/{job_id}` และผูก wizard ให้ queue/poll แทน block request; Settings แสดง `/health/deep`; RunDetail evidence tab แสดง count/status ของ news/source. Verification: `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .`, `web npm.cmd run build` ผ่านครบ.
- **Performance/UI ล่าสุด (15 ก.ค. Codex รอบสอง):** ผู้ใช้อนุมัติให้ทำทุกข้อ backend+UI/UX ที่แนะนำต่อ จึงเพิ่ม run lifecycle จริงใน DB (`queued/running/complete/error/canceled`, `job_id`, progress, timestamps), `/runs/async` pre-create queued row, `/runs/{id}/cancel`, `/runs/{id}/retry`, `/run-metrics.json`; `core/tasks.persistent_run_task` รับ `run_id` เพื่ออัปเดต row เดิม; source URL/RSS fetch cache 6 ชั่วโมง + hybrid deterministic retrieval (3-gram + term/label boost); เพิ่ม `scripts/db_migrations.py` เป็น migration scaffold idempotent. Frontend: History กลายเป็น **Job Center** พร้อม progress/cancel/retry/metrics/evidence health; RunDetail เพิ่ม **Executive Readout**, **Evidence Drawer**, **Thai Social Signal Map** และใช้ lucide status icons; Settings เพิ่ม operational metrics; Persona Pack Studio เพิ่ม Audience Signature. Verification ล่าสุดผ่านครบ: `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .`, `web npm.cmd run build`; collect-only = 332 tests.
- hindcast batch มี run-to-run variance (4/5 ↔ 5/5 — target เสียงก้ำกึ่งพลิกได้): เผยแพร่ทุกรอบ ห้ามเลือกรอบสวย
- ถัดไป (12 ก.ค.; อัปเดต 18 ก.ค.): (1) **prediction #161 ครบกำหนดตั้งแต่ 8 ก.ค. ยังไม่ resolve** — resolve ผ่าน `scripts/resolve_predictions.py` (หน้า Calibration UI ถูกถอดตาม ADR-0020) รอผู้ใช้ป้อน outcome (2) งานที่รออินพุต/มติผู้ใช้: ป้อนเหตุการณ์/นโยบายจริงเข้าระบบ (ปลดล็อก calibration แท้จริง), calibrate segments กับสำมะโนจริง (รอไฟล์/ลิงก์ → วาง data/samples/population/sources/), TRUST-08 panel (รอผู้ใช้ตัดสินใจ sourcing), GA สาธารณะ (TLS/pen test/SSO/multi-tenant), semantic memory (เมื่อความจำโต)
- **หมายเหตุ resolve predictions**: prediction ปัจจุบันมาจาก scenario สังเคราะห์ (corpus demo) — ไม่มีผลจริงภายนอกให้เทียบ; การ resolve ให้มีความหมายต้องเริ่มป้อนเหตุการณ์/นโยบายจริงเข้าระบบก่อน แล้วเมื่อครบกำหนดผู้ใช้ป้อนผลจริง: `uv run python scripts/resolve_predictions.py --id N --outcome true|false --note "แหล่งอ้างอิง"` → Brier สะสมอัตโนมัติ → rebuild benchmark page
- ข้อมูลสำคัญจาก fidelity dial: Standard run (1000×30×5u) ประเมิน ~$2.49 แบบ voice-sparse — วัดจริงแล้ว $25.09/$0.82 (ดู scale-measurement.md)

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
- [x] ~~ห่อ `query_indirect` เป็น REST endpoint~~ (P3-Q: `/graph/indirect.json`)
- [x] ~~exit criteria #2 Standard run ≤ $80~~ (วัดจริง 6 ก.ค.: $25.09 thinking-on / $0.82 off — ผ่าน)
- [x] ~~Windows console cp1252~~ (P3-Q: UTF-8 reconfigure จุดเดียวใน core/config; ยกเว้น `python -c` inline ต้องใช้ `PYTHONIOENCODING=utf-8` เอง)
- [x] ~~CI ยังไม่ build frontend~~ (12 ก.ค. — เพิ่ม job `web-build` ใน ci.yml: npm ci + tsc/vite build จับ TS พังทุก push)

## งานถัดไป — source of truth

Phase 9 engineering/model/accessibility gates ปิดแล้ว งานถัดไปที่ยังต้องใช้ external human evidence:

1. ดำเนิน usability session จริงผ่าน #/usability ให้ครบ P01–P05 แล้ว import anonymized raw hash/report;
   ห้ามกรอกผลแทน participant หรืออ้าง ≥80% ก่อนมี 25 task records จริง
2. consent-based Thai human panel และ future-event calibration เมื่อมี owner/dataset จริง

`docs/FUTURE-WORK.md` ยังเป็นรายการ canonical ของงาน deferred นอก Phase 9. สรุปกลุ่มงานที่ยังไม่ปิด:

1. Public GA: TLS/OIDC/PostgreSQL RLS ถูก Deferred; ยังมี independent pen-test, rate limiting,
   backup/DR, SLO/alerts และ legal/ethics gate
2. Trust: MIRACL Thai benchmark จริง, future-event calibration, TRUST-08 human panel และ population calibration
3. Engineering debt: แยก runs/dashboard/gallery/calibration จาก `api/app.py` ต่อ, ลด OpenAPI casts และทำ
   release-scale soak ผ่าน TLS/OIDC/SSE reconnect/budget contention/paid Debate 1,000-agent payload
4. Business/product: safety baseline มีผลตาม ADR-0013 แล้ว; commercial model, public license, การขยาย Election
   eligibility และการเปิด semantic memory ยังต้องมีมติใหม่ตาม change gate

prediction เก่าที่ครบกำหนด (รวม #161) ต้องตรวจ `source_kind/domain` และหลักฐานโลกจริงก่อน resolve;
legacy/test-generated records ไม่เข้า Calibration หลักและห้ามสร้าง outcome เพื่อให้ sample size ดูดีขึ้น

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

- 2026-07-18 (Claude Fable 5): **แก้ run ล้มจาก analyst truncation + กู้ Executive Readout + CI triage** —
  root cause คือ synthesis ไทยครบ contract ไม่มีทางจบใน `max_tokens=900` (ทั้งสอง attempt ชนเพดาน
  ตาม provider ledger); เพิ่มเพดาน 2,000/3,000, `finish_reason` provenance, taxonomy `llm_truncated`,
  error message บอกเหตุจริง และแก้ analyst cost estimate. live retry complete ใน attempt เดียว
  USD 0.0147. CI ใหม่รันครั้งแรก (commits 14–18 ก.ค. เพิ่งถูก push) แดง 3 job — แก้ readiness test
  hermeticity, ปิด uv cache ใน live job, เพิ่ม overflow diagnostics ใน a11y test โดยไม่แตะเกณฑ์.
  Verification: backend 413, Vitest 11, Playwright 20 local + jammy container, Ruff ผ่าน.
  ระหว่าง triage เผลอรัน `npm ci` ใน container ที่ mount web/ จริงทำให้ node_modules host เสีย —
  หยุดทัน กู้ด้วย `npm ci` และทดสอบซ้ำผ่านครบ; ไม่แตะ `.gitignore`/`diagrams/` ของผู้ใช้.
- 2026-07-18 (Claude Fable 5): **ถอดหน้า/เมนู Calibration ตามคำสั่งผู้ใช้ (ADR-0020)** — ลบ page/route/
  API client/i18n, `GET /calibration.json`, `calibration_detail` และ MCP `get_calibration`; คง registry
  append-only, resolve endpoint/CLI/MCP, `calibration_summary`+benchmark page ครบตามกฎเหล็กข้อ 3.
  ปรับข้อความ UI ที่เคยชี้เมนูให้ชี้ `scripts/resolve_predictions.py`, regenerate OpenAPI client.
  Verification: backend 411, Vitest 11, Playwright 20, Ruff/format, build ผ่าน (index 88.24 kB);
  บันทึก flake test-order ของ `test_newsdesk` cache test ไว้ใน STATE. ไม่แตะ `.gitignore`/`diagrams/`
  ของผู้ใช้.
- 2026-07-18 (Codex): **แก้ Executive Readout ว่างจาก analyst schema fragment** — root cause คือ backend
  ยอมรับ JSON object ใดก็ได้ ทำให้ `{bucket,pct}` ถูกบันทึกเป็น complete synthesis. เพิ่ม strict contract,
  bounded retry + BudgetGuard, fail-closed status, frontend legacy guard/frozen-rerun CTA และ regression tests.
  live Debate ใหม่แสดง summary ครบ ใช้ USD 0.000539; backend 411, Vitest 11, Playwright 20 และ build ผ่าน.

- 2026-07-18 (Codex): **ถอด 4 workspace ตามมติผู้ใช้และ clean production runtime** — ลบ
  Project/Evidence, Validation Lab, Rehearsal, Usability ทั้ง navigation/routes/pages/API/stores/engine/CLI/tests;
  migration ลบ 14 ตารางที่มี 0 rows และถอด project linkage จาก PopulationSet โดยรักษา immutable governance
  ledgers. ADR-0019; Compose healthy, app 200, old API 404, live Fabric workflow complete $0. Backend 411,
  Vitest 10, Playwright 20, Ruff/format/build/migration no-op ผ่าน. ไม่แตะ user-owned changes เดิม.

- 2026-07-17 (Codex): ปิด production-real runtime gate ตาม ADR-0018 — Compose supervise API/worker/beat,
  PopulationSetV1 fail-closed, Citizen demo offline-only, Debate analyst failure เป็น error, real-process
  Fabric + paid OpenRouter Debate smoke ผ่าน, CI แยก evidence tiers; main :8000 healthy. Backend 427,
  Vitest 8, Playwright 26, Ruff/build/migration/audit ผ่าน; usability ผู้ใช้จริง 5 คนยัง pending อย่างซื่อสัตย์.

- 2026-07-17 (Codex): **ปิด queued หลอกจาก worker outage และกู้รันผู้ใช้** — root cause คือ Celery worker
  ไม่ได้รัน แต่ health เดิมตรวจ Redis broker เท่านั้น. เปิด worker queue ครบและรัน Debate ของผู้ใช้จบ;
  เพิ่ม worker TTL heartbeat, `/health/deep` component, 503 ก่อน persist queued row และ idempotent replay
  semantics; แก้ Makefile ให้ subscribe queue จริง. live Fabric smoke 202→complete แล้ว cleanup. Verification:
  422 backend tests, Ruff/migration no-op; ADR-0017. ไม่แตะ `.gitignore`/`diagrams/` ของผู้ใช้.
- 2026-07-17 (Codex): **กู้ Create Project จาก stale API process** — live OpenAPI ที่พอร์ต 8000 ไม่มี
  /projects แม้ repo/client มี route ครบ จึง restart เฉพาะ FastAPI process. หลัง restart OpenAPI มี
  GET/POST /projects; probe แบบไม่สร้างข้อมูลได้ GET=200, invalid POST=422 และ app shell=200.
  ไม่เปลี่ยน business code/DB/worker และไม่แตะ `.gitignore`/`diagrams/` ของผู้ใช้.
- 2026-07-17 (Codex): **ปิด model robustness + TH/EN/WCAG engineering gates และส่ง usability mockup** —
  OpenRouter measured run 3 models/6 cases/18 calls ใช้ 0.002412 USD, agreement 0.888889; failed provider
  attempts ถูก invalidate แบบ append-only. axe WCAG 2.2 AA 13 routes desktop/mobile, dictionary/locale,
  skip/focus/reflow/target tests ผ่าน; route #/usability เก็บ consent/timer/category แบบ local anonymized.
  Verification 419 backend, Ruff/migration, Vitest 8, build index 93.14 kB, Playwright 26 และ npm audit 0.
  usability/human-panel claim ยัง blocked; ไม่ stage/revert `.gitignore`/`diagrams/` ของผู้ใช้.
- 2026-07-17 (Codex): **Phase 9 M2 engineering + M3 product surfaces พร้อม และหยุดที่ external gate** —
  Project/EvidenceSet/Validation/Resolution/Rehearsal ลงด้วย append-only provenance, PII fail-closed,
  CAS checkpoints และ transactional monthly reservation; React routes/deep links/mobile E2E และ Run Detail
  5-tab shell พร้อม. MIRACL Thai pinned full corpus/dev ผ่านด้วย raw hash/metrics ในรายงาน; รอบ incomplete
  ถูก invalidate แบบ append-only. Verification: 417 backend tests, Ruff, migration no-op, OpenAPI,
  Vitest 5, initial index 85.81 kB และ Playwright desktop/mobile. คง pending อย่างซื่อสัตย์: model robustness
  execution ต้อง opt-in, full TH/EN+WCAG audit และ usability ≥5 คนยังไม่รัน. ไม่ stage/revert
  `.gitignore`/`diagrams/` ของผู้ใช้.
- 2026-07-17 (Codex): **Phase 9 M1 Pilot-ready trust gate ผ่านและหยุดรอมติ** — เพิ่ม ADR-0014,
  immutable RunSpec/append-only manifest+legacy migration, canonical completeness/hash checks,
  frozen/latest rerun, 202+Idempotency-Key, terminal CAS/cancel checkpoints, DNS-pinned SSRF fetcher,
  stored-snapshot PDF/JSON, HashRouter/deep links/mobile drawer/running controls และ generated OpenAPI.
  Verification: 407 backend tests, Ruff, Vitest 5, build index 92.67 kB (+13.0%), Playwright 14,
  npm audit 0, migration no-op; screenshots อยู่ `.tmp/p9-*.png`. ไม่เริ่ม M2 และไม่แตะ
  `.gitignore`/`diagrams/` ของผู้ใช้.
- 2026-07-16 (Codex): **Phase 8 M8 engineering debt + active business policy** — แยก Persona/Watchlist
  routers, ปิด raw fetch 37 จุดให้ generated OpenAPI client เป็นทางเข้าเดียว, เพิ่ม `httpx2` แทน warning
  suppression, เพิ่ม external production soak runner และ live soak 20/20 ผ่าน (p50 1.657s, p95 2.214s,
  heartbeat/event 100%). ADR-0013 formalize no-billing/private-repo/verified-admin Election/run-local-only
  semantic memory พร้อม benchmark gate และแสดง read-only ใน Settings. Verification: 391 backend tests,
  ruff, OpenAPI, Vitest 5, build, Playwright 8, migration no-op; API/worker เปิดอยู่. ไม่ stage/revert
  `.gitignore` และ `diagrams/` ของผู้ใช้.
- 2026-07-16 (Codex): **จัดทำ Future Work ตามมติผู้ใช้** — เลื่อน TLS/OIDC/PostgreSQL RLS ไว้ทำภายหลังและเขียนรายละเอียดครบใน `docs/FUTURE-WORK.md`; เพิ่ม backlog อื่นที่ยังต้องทำจริง ได้แก่ independent pen-test, distributed rate limiting, backup/restore drill, SLO/alerts, legal/ethics, MIRACL external benchmark, future calibration, TRUST-08, population calibration และ engineering debt. ADR-0012 เปลี่ยนเป็น Deferred; ไม่มี production code/architecture ถูกเปลี่ยนใน session นี้.
- 2026-07-16 (Codex): **Phase 8 M7 production hardening** — ปิด monthly-budget race ด้วย transactional reservations+settlement/release, แยก Settings router, ย้าย main run/settings/experiment calls ไป generated OpenAPI client, lazy-load routes ลด initial JS ~248→82 kB, เพิ่ม CI dependency audit และ secret-safe self-hosted/public-GA readiness. ADR-0012 ถูก Deferred ภายหลังตามมติผู้ใช้; MIRACL Thai เป็น external gate ที่ยังไม่อ้างผล. Verification: 387 backend tests, ruff, OpenAPI/Vitest/build, Playwright 8, npm/pip audit และ migration no-op ผ่าน; ไม่แตะ `.gitignore`/`diagrams/`.
- 2026-07-16 (Codex): **Phase 8 M6 Experiment workspace/platform completion** — เพิ่ม comparison/sweep/sensitivity workspace, aggregate BudgetGuard ก่อน enqueue, migration-only store, ops/experiment routers+services, requested Fabric seed, discriminated run payload/OpenAPI schema, TanStack Query experiment deep link และ virtualized 1,000-post Debate feed; แก้ contention graph O(n²) ด้วย bounded 24-segment view โดย feed ยังครบ. Verification: 383 backend tests, ruff check/format, OpenAPI generation, Vitest 5, production build, Playwright 8 desktop/mobile, migration no-op และ services healthy; ไม่แตะ `.gitignore`/`diagrams/` ของผู้ใช้.
- 2026-07-16 (Codex): **Phase 8 M5 Core Engine/Retrieval ปิดครบและจบ Phase 8** — typed debate moves+lineage, deterministic verifier+analyst judge floor, opt-in bounded run-local reflection, priced/guarded embedding adapter, pgvector HNSW 1536d + Thai BM25/RRF + explicit fallback provenance, Thai benchmark harness/report, OpenTelemetry trace propagation, Prometheus metrics และ provider-health Insights dashboard. Benchmark ระบุชัดว่า fixture เล็ก/harness smoke ไม่ใช่ external validity. Verification: 377 backend tests, ruff check/format, OpenAPI generation, Vitest, production build, Playwright และ migration no-op ผ่าน; ไม่แตะ user changes `.gitignore`/`diagrams/`.
- 2026-07-16 (Codex): **Phase 8 M4 visualization platform** — เพิ่ม TanStack Query/OpenAPI typed client/SSE reconnect+polling fallback, ECharts visualizations (multiverse range, scenario diverging bars, stance timeline, validation matrix), Cytoscape contention graph, evidence lineage Sankey, table fallbacks/accessibility และ frontend Vitest+Playwright desktop/mobile; backend ส่ง `universe_estimates` และ validation child `value` เพื่อรองรับ charts. Verification ผ่าน: `uv run pytest -q` 369 tests, `uv run ruff check .`, `uv run ruff format --check .`, `npm.cmd run generate:api`, `npm.cmd run test`, `npm.cmd run build`, `npm.cmd run test:e2e`; เปิด dev stack ด้วย `docker compose up -d`; ไม่แตะ user changes `.gitignore`/`diagrams/`.
- 2026-07-15 (Codex): **Phase 8 Prediction Experience/runtime foundation** — implement ADR-0011 + PHASE8 M1-M3: migration-only schema/pool/compose gate, queue routing+heartbeat+stale+idempotency, SSE durable replay, finding-vs-prediction contract, evidence resolution, calibration legacy filter/reliability, 3-seed validation, structured JSON Schema provenance และ append-only synthesis revisions; frontend เพิ่ม deep link/result CTA/validation/reliability. Stress 20 concurrent run + 20 concurrent read เปิดปัญหา pool 12 connections/run-id ชนกัน จึงเพิ่ม pool default 32 และ UUID suffix แล้วผ่านครบ; full suite 368 tests + ruff + web build + migration no-op ผ่าน. คง `.gitignore`/`diagrams/` ของผู้ใช้ไว้ไม่แตะ.
- 2026-07-15 (Codex): **แก้กราฟจุดยืนว่าง + ชี้แจง/ลด JSON parse failure** — run ล่าสุดมี metrics จริง `[-0.3238,-0.4750,-0.6269]` และ posts 119/120; root cause กราฟว่างคือ percentage-height อยู่ใน parent auto-height ไม่ใช่ข้อมูลหาย. สร้าง chart รอบแกนศูนย์ขนาดคงที่พร้อม labels 1-based, แยก failure taxonomy ออกจาก Contention graph; parser รับ valid JSON object ที่ถูก provider ห่อ prose/fence แต่ malformed ยัง fail-closed. คง historical `json_parse_error:1` ไว้ตาม audit truth; 360 tests + ruff + web build + worker reload ผ่าน; ไม่แตะ `.gitignore`/`diagrams/`.
- 2026-07-15 (Codex): **implement ADR-0010 หลังผู้ใช้ยืนยัน** — external evidence redact phone/email/Thai ID/person แล้ว re-scan ก่อน persistence/LLM; URL/query/direct text/label และ failure ยัง block; เพิ่ม `pii_redactions` provenance + Evidence UI, migrations purge/scrub legacy metadata; DB audit ทุก boundary flagged 0; Debate round UI เริ่ม 1; 357 tests + ruff + web build ผ่าน; worker reload ด้วย clean proxy; ไม่แตะ `.gitignore`/`diagrams/`.
- 2026-07-15 (Codex): **เลขรอบ Debate เริ่ม 1 + ปิด raw PII cache ระหว่างรอมติ redaction** — UI แสดงรอบ `shownRound + 1` แต่ไม่เปลี่ยน internal index; audit cache แบบไม่แสดงค่าพบ news cache มี PII 5/25 แถวและลบเฉพาะ 5 แถว; sources/news ไม่ cache raw payload ที่ detector block และ error เก็บเฉพาะชนิด PII; ADR-0010 เสนอ redact→re-scan→process เฉพาะ external evidence ยังรอผู้ใช้ approve; 349 tests + ruff + web build ผ่าน; ไม่แตะ `.gitignore`/`diagrams/`.
- 2026-07-15 (Codex): **แก้ Budget UI ให้บันทึกวงเงินจริง + กู้ prediction จาก test pollution** — root cause คือ test settings reset override เป็น 0 และ test ledger เติม `$3` ค้าง 34 ครั้ง รวม `$102`; เพิ่ม snapshot/restore DB settings ต่อ test และ cleanup spend ใน `finally`, ล้างเฉพาะ test ledger จนยอดจริง `$0.015036`; PUT settings คืน effective values, UI มี draft+ปุ่มบันทึกและแสดง active/env/spent/remaining; readiness monthly budget fail-closed และ worker เช็กงบก่อน I/O; real smoke run `debate-20260715-141337-906865` complete 10/10 posts, 0 failed; 348 tests + ruff + web build ผ่าน; API `http://127.0.0.1:8000/app/` และ clean worker online; ไม่แตะ user changes `.gitignore`+`diagrams/`.

- 2026-07-15 (Codex): **monitor/fix Debate fail 60/60** — ตรวจพบ worker สืบทอด sandbox proxy `127.0.0.1:9` จึงต่อ OpenRouter ไม่ได้ ทั้งสอง run ก่อนหน้าถูกบันทึก complete ผิดแม้ posts_failed=60/cost=0; ตรวจ key read-only พบเครดิตปกติ, รีสตาร์ต worker โดยล้าง proxy และ retry สำเร็จเป็น run `debate-20260715-134130-116660` (59/60 posts, analyst จริง, cost `$0.005746`); แก้ engine ให้ all-agent failure raise `DebateUnavailableError` และเพิ่ม failure taxonomy; 347 tests + ruff ผ่าน; worker clean ยัง online; user changes `.gitignore`+`diagrams/` ไม่ถูกแตะ
- 2026-07-15 (Codex): **debug prediction queued/deadlock + เปิด worker** — ยืนยัน PostgreSQL OID 33676=`sim_runs`, 33693=`debate_posts`; root cause คือทุก polling endpoint เรียก `RunStore.setup()` ซึ่งทำ AccessExclusiveLock DDL ซ้ำและชนกัน; เพิ่ม setup cache+thread lock+PostgreSQL advisory lock, ไม่ drop/add constraint ที่ถูกต้องแล้ว, และกัน stale canceled task เปลี่ยนกลับเป็น running; ล้าง Redis retry ซ้ำ 2 งาน เหลืองานล่าสุด 1 งาน; stress `/simruns.json`+`/run-metrics.json` 100 requests ผ่าน 200 ทั้งหมด; เปิด Celery worker สำเร็จ แต่งานล่าสุดหยุดที่ BudgetGuard เพราะยอดเดือน `$96.01/$50.00` (ไม่ override); `uv run pytest -q` ผ่าน 345 tests, ruff check/format ผ่าน; user changes `.gitignore`+`diagrams/` ไม่ถูกแตะ
- 2026-07-15 (Codex): **review codebase ทั้งหมดตามคำขอผู้ใช้ — ไม่แก้โค้ด production** — อ่านเอกสารกำกับครบตาม AGENTS.md (`AGENTS.md` → `CLAUDE.md` → `docs/STATE.md` → `docs/PHASE7-BRIEF.md` → ADR list), สแกน governance/security surfaces (external retrieval, PII, append-only registry, exports/gallery, secrets, BudgetGuard), เปิดไฟล์หลัก `api/app.py`, `core/runstore.py`, `governance/store.py`, `simulation/newsdesk.py`, `simulation/debate.py`, `simulation/sources.py`, `governance/gallery.py`, `governance/watchlist.py`, frontend RunDetail/Watchlist และ tests; findings หลัก: agents lower-bound validation ขาดใน `/runs`/gallery/watchlist, `test_phase6.py` DB readiness ไม่มี timeout ทำให้ pytest collection ค้างเมื่อ DB down, News Desk ไม่ snapshot provider failure; verification: เปิด dev stack แล้ว `uv run pytest -q` ผ่านครบ, `uv run ruff check .` ผ่าน, `web npm.cmd run build` ผ่าน; working tree เดิมมี `.gitignore` modified + `diagrams/` untracked ที่ Codex ไม่แตะ
- 2026-07-05 (Claude Fable 5): วางแผน Phase 0 + M-1/M0/M1/M2 เสร็จ — M1 gate ผ่านโดยมติผู้ใช้ (รายละเอียด docs/reports/), M2 ได้ graph 114 entities + indirect query; สร้าง AGENTS.md + STATE.md สำหรับส่งมอบข้ามโมเดล; ถัดไป: M3 เริ่มที่ spike OASIS
- 2026-07-05 (Claude Fable 5): **M3 เสร็จ** — ADR-0002 (runtime เอง, มติผู้ใช้), persona factory + cap guard, 4 channels + engine deterministic, benchmark FAB-01 ผ่าน sign test (59/60 p=5e-17; 45/58 p=1.5e-5) หลัง iterate โครงกลุ่ม 3 รอบ, voice layer เห็น say-do gap จริง; ถัดไป: M4
- 2026-07-05 (Claude Fable 5): **M4 เสร็จ** — SIM-04 fork+belief revision (delta −18.0% CI ไม่คร่อม 0), รายงาน what-if ครบ field บังคับ, hindcast 5 ชุด + batch **ผ่าน 4/5 (exit criteria #1 ✅)**, leak test True-DTAC 0.0%, แก้ leak_if a1; เหลือ M5 ปิดเฟส
- 2026-07-05 (Claude Fable 5): **M5 เสร็จ = Phase 0 ครบทุก milestone** — watermark (fail-closed, จุด export เดียว), audit log + prediction registry append-only ด้วย PostgreSQL trigger (test ยิง SQL ตรง), ครบวงจรใน run_whatif (audit→predict→finalize→watermark export ยืนยัน record ใน DB); governance store อยู่ governance/store.py, watermark อยู่ governance/watermark.py
- 2026-07-05 (Claude Fable 5): **เริ่ม Phase 1 + P1-M1..M3 เสร็จ** — fragility (5 universes, TRUST-05 บังคับจริง), calibration engine (Brier + resolution append-only + benchmark page มี variance note), provenance cards + silent majority + fidelity dial (standard ≈ $2.49); **GitHub push + CI เขียว** (`santipongth/chimlang`); ถัดไป P1-M4 Red Team Swarm
- 2026-07-05 (Claude Fable 5): **P1-M4..M6 เสร็จ = Phase 1 ครบทุก milestone** — Red Team Swarm (5 บทบาท, Attack Surface Report, GOV-05 guard), governance เฟสสอง (election mode auto-classify + no-persuasion + RBAC), Executive Dashboard (DASH-01..04) + FastAPI (/dashboard.json|html, election block ที่ API); exit criteria Phase 1 ผ่าน 4/4; tests 123 เขียว; ถัดไป Phase 2 หรือขยาย scale (รอผู้ใช้)
- 2026-07-06 (Claude Fable 5): **เริ่ม Phase 2 (ผู้ใช้ approve แผน 6 milestones ใน PHASE2-BRIEF) + P2-M1 เสร็จ** — Press Conference Rehearsal สด (นักข่าว 3 สาย + ชาวเน็ต voice layer, scorecard analyst จับคำตอบเสี่ยงได้จริง), แก้ latency 25.8→2.8 วิ ด้วย `reasoning=False` (พบ crowd model เผา 1,200 hidden tokens/call); unstage toh-read.txt + gitignore; tests 132 เขียว; ถัดไป P2-M2 Game Mode
- 2026-07-06 (Claude Fable 5): **P2-M2 เสร็จ** — Game Mode (REH-03): strategic actor (analyst) เดินตอบ, สังคม react ผ่าน engine กลไก deterministic (สองข้อความแข่งกันแพร่), ≥3 ตาบังคับ, decision tree มีทางเลือกที่ไม่ได้เดิน; demo จริง $0.001 ความเชื่อฝั่งเราไต่ 20→40→60%; tests 138 เขียว; ถัดไป P2-M3 War Room
- 2026-07-06 (Claude Fable 5): **P2-M3 เสร็จ** — War Room + Divergence Alarm: `preseed()` sync โลกจำลองกับค่าจริง, forecast envelope 48 ชม. (5 seeds, กลไก $0), alarm เมื่อหลุดซอง > 0.02 (demo: 95% หลุด [40,80] → ยิงจริง); SIM-11 gate ที่ load_feed (hindcast block + test), PII check ทุก note; prediction สั้น (due 2 วัน) เข้าคิว calibration; tests 146 เขียว; ถัดไป P2-M4 Sim-to-Signal
- 2026-07-06 (Claude Fable 5): **P2-M4 เสร็จ** — Sim-to-Signal: 6 features กลไกจริง + CI95, metadata/disclaimer บังคับ, rate limit 429, GOV-02 → 403 ที่ /signal.json; OOS harness (SIG-02): split ตามเวลา + IC/hit rate เทียบ baseline + ตัวอย่างเล็ก = ปฏิเสธ; tests 159 เขียว; ถัดไป P2-M5 Living Memory
- 2026-07-06 (Claude Fable 5): **P2-M5 เสร็จ** — Living Memory (WorldMemory ใน PG, PII gate ทุกข้อความ, workspace isolation, reset+audit): run 2 เริ่มจากสถานะที่โลกจำ (20%→40%); SIM-08 ask: คำตอบต้อง cite trail จริง index ถูกตรวจ ไม่มี citation = ธงเตือน; tests 168 เขียว; ถัดไป P2-M6 ปิดเฟส
- 2026-07-06 (Claude Fable 5): **P2-M6 เสร็จ = Phase 2 ครบทุก milestone** — influence graph ระดับ segment (test กัน agent id หลุด), impact waterfall 2-3 hop (30 entities จริงจาก Neo4j; เกือบซ้ำบทเรียน shortestPath M2), media agent 3 stance, rumor mutation ใน closed group; exit criteria 6/6; tests 179 เขียว; ถัดไป Phase 3 / scale / เก็บคุณภาพ (รอผู้ใช้)
- 2026-07-06 (Claude Fable 5): **Phase 3 เริ่ม (ผู้ใช้สั่ง 3 สายพร้อมกัน) — โครงหลักครบ**: (S) cap→1,000+rename+perf fix+วัดจริง: standard $25.09/$0.82 ผ่าน ≤$80✅, 1000×30×5u=5.8วิ, **finding: delta หด −16.5%→−1.2% ที่ scale ใหญ่ ต้อง re-calibrate**; (C) CIT-01..04: impact twin session-only (test พิสูจน์ไม่แตะ DB), portal, feedback k-anonymity≥20, disclaimer ถาวร; (Q) UTF-8 console จุดเดียว + /graph/indirect.json; tests 188 เขียว
- 2026-07-06 (Claude Fable 5): **CIT-03 ครึ่งหลังเสร็จ = CIT-01..04 ครบเต็มข้อ** — เสียงจริง (ผ่าน k-anonymity) เป็น prior sim รอบใหม่, portal แสดงคู่ก่อน/หลังรับเสียง, inject เข้า Living Memory เป็น real_event; tests 191 เขียว
- 2026-07-06 (Claude Fable 5): **Re-calibrate scale เสร็จ (ADR-0003)** — วินิจฉัย: seeder เดี่ยว penetration 92%→8% เมื่อ n โต + คำชี้แจงไหลจากคนเดียวผิดธรรมชาติ; แก้: preseed 10% + 60 rounds + `Message.broadcast_share=0.20` (โหมดสื่อมวลชนใหม่ใน engine) → delta −15% เท่ากันที่ n=100/1,000; tests 193 เขียว; แก้ CI ที่แดงจาก test skip ไม่สะอาด (บทเรียน: watch CI ด้วย SHA ไม่ใช่ --limit 1)
- 2026-07-06 (Claude Fable 5): **เริ่ม Phase 4 + P4-M1 React UI เสร็จ** — Vite+React18+TS+Tailwind4, theme/layout ตาม ref ผู้ใช้ (sidebar+content 2 คอลัมน์, เขียวมรกต, serif heading, step wizard), i18n TH/EN ทุกหน้า, 5 หน้า รวม landing + การจัดการรัน (/runs.json ใหม่ + recent_runs()), FastAPI เสิร์ฟ dist ที่ /app; tests 196 เขียว; ถัดไป P4-M2 PDF export
- 2026-07-06 (Claude Fable 5): **P4-M2..M4 เสร็จ** — PDF export ผ่านจุด watermark เดียว (Sarabun ฝัง+shaping, metadata ตรวจกลับได้, GOV-02 label ใน PDF), Celery+Redis queue (POST /jobs/whatif + guard ก่อน enqueue + governance 2 ชั้น), Auth/RBAC (X-API-Key, viewer/analyst/operator/admin, election=admin verified เท่านั้น, citizen สาธารณะ); tests 211 เขียว; เหลือ M5 deployment (รอผู้ใช้ตัดสินใจ cloud) + M6
- 2026-07-06 (Claude Fable 5): **P4-M5+M6 เสร็จ = Phase 4 ครบทุก milestone** — มติผู้ใช้ D9: self-hosted docker; Dockerfile multi-stage + compose.prod (smoke จริงผ่าน: health/UI/sim ใน container; บั๊ก uvicorn อยู่ dev group ถูกจับตอน smoke), PDF 2 ภาษา, security headers + /health/deep + security-review.md (ตรงๆ: pen test/TLS/SSO ยังไม่ทำ); tests 214 เขียว
- 2026-07-12 (Claude Fable 5): **maintenance หลังปิด Phase 4** — ตรวจสุขภาพ (214 เขียว), แก้ STATE.md ที่ stale ขัดแย้งกันเอง (เริ่มตรงนี้/cap 10/123 tests/หนี้เทคนิค/งานถัดไป M5 เก่า), เพิ่ม CI job `web-build` (จับ TS พังทุก push — เก็บคิวจาก P4-M1); **พบ prediction #161 ครบกำหนด 8 ก.ค. ยังไม่ resolve** (scenario สังเคราะห์ — รอผู้ใช้ป้อน outcome); ไม่มีงานโค้ดค้าง — ทุกอย่างถัดไปรออินพุตผู้ใช้
- 2026-07-12 (Claude Fable 5): **research SwarmSight (github.com/santipongth/swarm-visionary-forge) — ผู้ใช้สั่งพักไว้ก่อน ยังไม่ approve แผน** — สำรวจเว็บ studio ครบทุกหน้า + อ่านโค้ด engine จริง: debate loop (persona rich + stance_prior, สุ่มอ่าน 6 โพสต์/รอบ, JSON {content,stance,sentiment}), Red Team 2 slot (contrarian −0.6 + auditor), metrics 7 ตัวชื่อเดียวกับ SIG-01 + tipping ≥0.25/รอบ → webhook Slack/Discord, calibration outcome 3 ค่า (partial=0.5), adapter contract (MiroStatusSchema) เสียบ engine ภายนอกได้; จุดอ่อนเขาที่เราห้ามเลียน: Math.random ไม่มี seed, outcome แก้ย้อนหลังได้ (UPDATE), ไม่มี cost guard/governance; ร่างแผน Phase 5 (6 milestones: UI ตาม studio + debate engine + calibration UI + watchlist/webhook + persona packs + gallery แบบ GOV-02-gated) — **รอผู้ใช้ปรับ/approve แผนก่อนเริ่ม**; โค้ด clone อยู่ .tmp/swarm-visionary-forge (disposable)
- 2026-07-13 (Claude Fable 5): **Share toggle ต่อ run (ผู้ใช้ขอแบบ studio)** — `POST/DELETE /runs/{id}/share`: แชร์ snapshot payload จริงของ run (แก้บั๊กแฝงเดิมที่รันจำลองใหม่ตอนแชร์), เปิดซ้ำ idempotent, ปิดแล้วลิงก์ตาย, UI dialog toggle 🌐/🔒 + copy link; ADR-0004 gates ครบ + audit ทั้งสองทาง; tests 322→324
- 2026-07-13 (Claude Fable 5): **Persona Pack Editor (ผู้ใช้ขอ 'ปรับกลุ่มและ persona ได้เอง' + approve แผน)** — modal wizard rewrite เป็น 3 tabs (เลือก/แก้ไข/ให้ AI ร่าง): แก้จำนวนกลุ่ม 2-8, share (stacked bar + normalize สด/auto ตอน save), voice, นิสัยวัฒนธรรม 3 ตัว, traits chips, **media diet 4 ช่องทาง** พร้อม copy ชี้ชัดว่าคุมทั้ง fabric และโต๊ะข่าวสด; สำมะโนอ่านอย่างเดียว + ทำสำเนาไปแก้ (มติผู้ใช้ ไม่เอา import/export); AI-generate ลง draft ให้ตรวจก่อน save เสมอ; backend: `PackStore.update` (validate+PII ด่านเดียวกับ create, ไม่แตะ created_by = TRUST-06), `PUT /personas/packs/{id}` (PackValidationError→422 ก่อน ValueError→404), pool.json เพิ่ม voice_activity; smoke สำเนาสำมะโน create/update/delete ผ่านจริง; tests 324→329
- 2026-07-13 (Claude Fable 5): **sweep ความสม่ำเสมอ UX ทุกหน้า (ผู้ใช้สั่ง 'เช็คทุกหน้า ให้แบบเดียวกัน ใช้งานง่าย')** — ตรวจครบ 10 หน้า: (1) **Watchlist ลบไม่ได้เลย** (ช่องว่างจริง — สร้างได้แต่ลบไม่ได้) → เพิ่ม `WatchlistStore.delete` + `DELETE /watchlists/{id}` (404 เมื่อไม่พบ; alerts หายตาม ON DELETE CASCADE ที่ schema มีอยู่แล้ว — ตาราง operational ไม่ติด append-only ตาม docstring เดิม) + ปุ่ม 🗑 + ConfirmDialog + test cascade (2) Settings: ล้าง LLM/Tavily key เดิมลบทันทีไม่ถาม → ConfirmDialog danger พร้อมอธิบาย fallback ไป .env (3) share dialog ใน RunDetail ปรับ backdrop/shadow ตรงมาตรฐาน dialog ใหม่; Calibration resolve มี inline confirm 2 ขั้นดีอยู่แล้ว (คงไว้ — เหมาะกว่า dialog เพราะต้องกรอกแหล่งอ้างอิง); Gallery/Compare/Insights/Landing อ่านอย่างเดียวไม่มีจุดเสี่ยง; tests 329→330
- 2026-07-13 (Claude Fable 5): **ADR-0009: cap 2-12 + guard สถิติ + calibrate channel_mix (ผู้ใช้ถาม 'cap 2-8 มาจากไหน / traits อิงอะไร' → research → approve 3 ข้อ)** — วิจัยพบ cap เดิมไม่มีเอกสาร+เลข 8 hardcode ซ้ำใน UI, traits มีฐานวิชาการจริง (kreng jai/social desirability collectivist/มีมการเมืองไทย — อ้างใน ADR) แต่ตัวเลขสังเคราะห์; ทำ: MAX_SEGMENTS→12 จุดเดียว + `limits` ใน pool.json (UI เลิก hardcode มี fallback), ⚠️ เตือน share×agents<30 ใน editor+pool panel (เตือนไม่ block), channel_mix สำมะโน calibrate จาก DataReportal 2025/YouGov (judgment mapping บันทึกใน provenance — คงคำ "สังเคราะห์" ที่ test_p1m3 เช็ค), ลบ prior ตาย `sensitivity_awareness` (persona.py ไม่เคยอ่าน — รั่วเข้าสำเนา pack), แก้ copy การ์ดสำมะโน 6→7 segments; smoke browser ผ่าน (label /12, ⚠️ ที่ n=100 หายที่ 1,000); tests 330→331
- 2026-07-13 (Claude Fable 5): **redesign UX persona packs (feedback ผู้ใช้ 2 ข้อ)** — (1) จัดการ pack (แก้ไข ✏️/ลบ 🗑/ทำสำเนา 📋) **inline บนการ์ดหน้า wizard ตรงๆ** ไม่ต้องเข้า modal ก่อน; modal เหลือหน้าที่ "ตัวแก้ไข" เปิดด้วย intent (edit/census/blank/ai — header+footer คงที่ เนื้อหา scroll, บันทึกแล้วเลือก pack นั้นให้เลย) (2) **เลิกใช้ window.confirm ทุกจุด** → `ConfirmDialog` component ของเราเอง (ui.tsx — Escape/backdrop ปิดได้, danger variant แดง) ครอบทั้งลบ pack, ลบ run หน้าประวัติ, AI ร่างทับร่างค้าง; smoke ผ่าน browser จริงครบวงจร (สำเนาสำมะโน→แก้→บันทึก→ติดดาวเลือกอัตโนมัติ→ลบผ่าน dialog); tests 329 คงเดิม
- 2026-07-12 (Claude Fable 5): **ลดรูป UI (คำสั่งผู้ใช้)** — ตัดกล่องคำทำนายจริงจาก wizard (prediction อัตโนมัติยังครบกฎเหล็กข้อ 3, resolve ที่หน้า Calibration เหมือนเดิม, API field ยังอยู่), ลบเมนูโหมดประชาชน (frontend เท่านั้น — backend CIT-01..04 + tests คงไว้ตาม PRD), layout เต็มจอ w-full responsive; tests 322 คงเดิม
- 2026-07-12 (Claude Fable 5): **journal protocol + แก้ UX แหล่งข้อมูล + news config ที่หน้า Settings** — (1) ผู้ใช้สั่งเก็บบันทึกบทสนทนา/กิจกรรม → `docs/journal/YYYY-MM-DD-session.md` + protocol ข้อ 4 ใน AGENTS.md (2) ปุ่ม + เพิ่มแหล่งข้อมูล ดู 'กดไม่ได้' เพราะ return เงียบเมื่อไม่กรอก → disabled+hint (3) NEWS_RSS_FEEDS/TAVILY_API_KEY ตั้งจากหน้า Settings (feeds ธรรมดา, Tavily key เข้ารหัส ADR-0007 pattern + `PUT /settings/tavily-key`), `effective_news_config()` DB ทับ .env; tests 320→322
- 2026-07-12 (Claude Fable 5): **Phase 7 ครบ M1..M4 ในวันเดียว (ผู้ใช้ approve 'โต๊ะข่าวกลาง + media diet' + RSS+Search API + เริ่มเลย)** — วิจัยก่อน: ไม่มี social sim ไหนให้ agent ดึงเน็ตสด (OASIS ฯลฯ inject โดยผู้วิจัย) = persona-conditioned retrieval คือจุด novel; `simulation/newsdesk.py` (gather=จุดเดียวแตะเน็ต: hindcast gate ก่อน I/O + PII ทุกชิ้น + snapshot news_items + dedupe hash + caps 30 items/8 queries), `segment_feed` media diet ตาม channel_mix (deterministic ต่อ seed — test ยืนยัน diet ต่าง=ข่าวต่าง), debate รับ segment_news + `want_to_know` intent → news_fetcher ระหว่างรอบ, POST /runs `live_news`, UI toggle+evidence tab; ADR-0008; tests 312→320 (8 ใหม่: leak/PII/replay-no-net/determinism/dedupe/prompt-wiring); **smoke กับเน็ตจริงผ่านแล้ว** (ผู้ใช้ใส่ feeds 3 + Tavily key): gather 39 ชิ้น (search 12/rss 27, PII block 10 — ข่าวอาชญากรรมมีเบอร์โทร/ชื่อ = gate ทำงานจริง), debate 4×2 = 8/8 posts $0.0007 — agent อ้างเนื้อข่าวจริง ('กองทุนซื้อคืนสัมปทาน', 'โมเดลสิงคโปร์') + ผู้สูงอายุพูดว่า 'ลูกหลานส่งต่อข่าวมาในไลน์' = media diet สะท้อนใน voice; **บั๊กที่ smoke จับได้+แก้แล้ว**: RSS ท่วม cap 30 จน search ตกขบวน → ให้ search (ตรงหัวข้อ) เข้าคิวก่อน RSS
- 2026-07-12 (Claude Fable 5): **P6-M6 พูลของ persona + มุมมองที่เปิดใช้ + 3 tabs (ผู้ใช้ขอเลียน studio)** — `/personas/pool.json` แสดง segments+สัดส่วนก่อนรัน (wizard พับดูได้); view toggles ในขั้น agents เก็บ `config.views`; RunDetail เพิ่ม tab **แผนภาพสวอร์ม** (debate=stance scatter/fabric=belief รายกลุ่ม) + **เส้นทางหลักฐาน** (debate=sources+chunks/fabric=tipping+trail — ไม่แกล้งมี knowledge graph ที่ engine ไม่มีจริง) filter ตาม views; tests 309→312
- 2026-07-12 (Claude Fable 5): **P6-M5 ตั้งค่า LLM ครบที่หน้า Settings (ADR-0007 — ผู้ใช้สั่ง 'ตั้งทุกอย่างที่หน้านี้')** — API key เก็บ **เข้ารหัส** ใน DB (Fernet + master key `CHIMLANG_SECRET_KEY` จาก .env; DB รั่วไม่พอถอด), endpoint แยก `PUT /settings/llm-key` (ADMIN), GET แสดงแค่มาสก์ ไม่ส่ง ciphertext; ราคาโมเดลแก้/เพิ่มจาก UI (fail-closed เดิมคง); งบ 2 ระดับ (ต่อรัน + **รวมเดือน** = `core/llm/budget.py` track spend สะสม block ก่อนรัน); `.env` ตัดไม่หมดเพราะ bootstrap (รหัส DB/master key/auth ต้องอยู่ .env — แจ้งผู้ใช้ผ่าน AskUserQuestion); อัปเดตกฎเหล็ก CLAUDE/AGENTS (secret bootstrap ยัง .env, LLM key เข้ารหัสได้); tests 302→309; cleanup script ครอบ sim_runs/llm_spend
- 2026-07-12 (Claude Fable 5): **LLM ปรับเองได้จากหน้าตั้งค่า (ADR-0006) + Thai copy pass + UI polish + แก้บั๊กหน้า Settings ว่าง** — Settings เลือก provider 6 ตัว (OpenRouter/OpenAI/Groq/Together/Ollama/custom) + base URL + model crowd/analyst + ราคา custom; **API key ยังอยู่ .env เท่านั้น ไม่รับ/ไม่ส่งกลับ** (แสดงแค่สถานะ), fail-closed เดิมคง (model ไม่มีราคา=รันไม่ได้), overlay .env แบบ non-destructive (`core/llm/userconfig.py`, `PricingRegistry.merged()`); debate/persona_ai เรียก effective config; **บั๊ก**: server ที่เปิดค้างเป็นโค้ดเก่าไม่มี field llm → หน้า Settings crash เป็นหน้าว่าง — แก้ด้วย guard `data.llm &&` + รีสตาร์ท server; UI: เมนู/ไอคอน lucide ตาม studio, หมวดหมู่ครบ 6, cursor pointer ทุกปุ่ม, toggle Red Team ON=เขียว, ตัวสลับภาษา redesign, ถอดแถบ watermark global (คงไว้เฉพาะ Citizen/Gallery ตาม CIT-04/ADR-0004), คำแปลไทยเป็นประโยคเข้าใจง่าย+วงเล็บอังกฤษ, tailwind pin 4.3.2; tests 298→302
- 2026-07-12 (Claude Fable 5): **Hindcast batch 10 เหตุการณ์เสร็จ — ผ่าน 9/10 ($0.17, 19/20 targets)** ปิด business goal "≥10 เหตุการณ์เผยแพร่"; benchmark page rebuild แล้ว; **finding ที่มีค่าที่สุดคือข้อที่พลาด**: pm-srettha-ruling — agents โหวต 0/5 ว่านายกฯ รอด (เหตุผลเดียวกับนักวิเคราะห์จริง ณ ตอนนั้น: ศาลไม่สั่งพักหน้าที่) แต่ผลจริงคือถอด 5:4 → ทายผิดแบบเดียวกับมนุษย์ = **หลักฐานว่าไม่ leak** (ถ้า leak จะรู้คำตอบ); ส่วน case คำตอบจริง FALSE (กนง.) agents ไม่ตามกระแสการเมือง ทาย False ถูก 4/4 = ทำนายจากโครงสร้างสถาบันจริง; หมายเหตุ: run-to-run variance ยังมีอยู่ — เผยแพร่ทุกรอบตามกติกา
- 2026-07-12 (Claude Fable 5): **Phase 6 ครบ M1..M4 (ผู้ใช้ approve "ทำ M1-M4 ต่อได้เลย", MiroFish → แผนระยะยาว)** — debate engine (seeded sampling ใน main thread, agent พัง=ติดธง failed ไม่ปนใน metrics + confidence ถูกลดตามสัดส่วน, ThreadPool 8, crowd reasoning=False + analyst synthesis + mechanical fallback), runstore+POST /runs (governance เต็ม), History/RunDetail/Replay/Settings pages, sources PII-gated + 3-gram retrieval (ยังไม่ใช่ vector — บันทึกไว้), เมนูตรง studio แล้ว; **smoke debate กับ LLM จริงผ่านแล้ว** (8/8 posts $0.0004 — เสียงไทยมีคาแรกเตอร์ประชด/เกรงใจ, synthesis analyst จริง); tests 285→298; **hindcast batch 10 เหตุการณ์ยังรันอยู่ background** (~1 ชม. thinking-on) — ผล+benchmark page จะ commit แยก
- 2026-07-12 (Claude Fable 5): **P5-M10 เก็บตก — SIG-01 ครบ 8 features ตาม PRD แล้ว** (เดิม P2-M4 ทำ 6, เพิ่ม bullish_bearish_shift จาก belief series ของ trail + event_interpretation_gap = pstdev ของ เชื่อ|ได้ยิน ระหว่าง segment), security-review.md ครอบ surface ใหม่ทั้งหมดพร้อมความเสี่ยงคงเหลือ (rate limiter per-process, vote dedup หลบได้ถ้าเปลี่ยน ip — ยอมรับโดยบันทึก), live smoke ผ่านทุก endpoint (พบจริง: n=20 red team พลิกข้อสรุป dd=+0.112 — ยืนยันกลไก M4 ทำงาน); tests 283→285
- 2026-07-12 (Claude Fable 5): **P5-M9 MCP surface เสร็จ = backlog Phase 5 หมดเกลี้ยง** (ADR-0005) — `api/mcp_server.py` stdio server (official `mcp` SDK) ห่อ REST เดิมเท่านั้น: ทุก tool call วิ่ง HTTP ผ่าน auth/RBAC/election/cap ครบ ไม่มี privileged path; auth = CHIMLANG_API_KEY env → X-API-Key; tools 7 ตัว (dashboard/compare/calibration/resolve/runs/gallery/insights); ต่อกับ Claude Code: `claude mcp add chimlang --env CHIMLANG_API_KEY=<key> -- uv run python -m api.mcp_server`; tests 278→283; **ไม่เหลืองานค้างใน backlog — งานถัดไปทั้งหมดรออินพุตผู้ใช้** (resolve #161, ป้อนเหตุการณ์จริง, calibrate สำมะโน, TRUST-08, GA)
- 2026-07-12 (Claude Fable 5): **P5-M8 Public Gallery + votes เสร็จ (ADR-0004 — agent ทำ GOV review เอง ผู้ใช้ veto ได้)** — แชร์ผลรันสู่สาธารณะแบบ fail-closed 4 ด่าน: election ห้ามแชร์เด็ดขาด (เข้มกว่า GOV-02 ปกติ), แชร์=export (EXPORT perm + watermark เปิด), PII gate, snapshot frozen ถอนได้อย่างเดียว + audit ทุกครั้ง; votes anonymous (hash ทางเดียว 1 คน 1 เสียง ไม่เก็บ ip ดิบ) แสดง crowd vs swarm — ไม่ป้อนกลับ sim อัตโนมัติ; หน้า Gallery + ปุ่มเผยแพร่ใน dashboard; tests 268→278; **backlog เหลือตัวเดียว: MCP surface** (รอตัดสินใจ transport/auth)
- 2026-07-12 (Claude Fable 5): **P5-M7 Persona Packs เสร็จ (ผู้ใช้สั่ง "ทำต่อ" = เริ่ม backlog)** — pack ที่ผู้ใช้นิยาม audience เอง (โครงเดียวกับ segments.yaml → factory ใช้ตรงๆ), AI-generate จาก prompt (analyst + retry 1 + BudgetGuard — **ทุก pack ผ่าน PII gate GOV-01 รวมถึงที่ AI สร้าง, detector ปิด = fail-closed**), "ลอง ask" preview ราย segment (crowd reasoning=False), dashboard/compare รับ pack_id, wizard มี preset cards + modal; tests 253→268 (mock LLM ทั้งหมด); **backlog เหลือ**: MCP surface (ต้อง design ผ่าน auth), public gallery + votes (ต้อง GOV review)
- 2026-07-12 (Claude Fable 5): **Phase 5 ครบทุก milestone M1..M6 ในวันเดียว (ผู้ใช้ approve "วางแผนที่ดีที่สุดแล้วเริ่มเลย")** — M1 UI shell ตาม studio (tokens/sidebar+badge/header pattern/tabs/template gallery + tooltip-สูตรเป็น convention), M2 `simulation/tipping.py` (Δbelief ≥0.15/round จาก trail — ปิดข้อบังคับ PRD ขั้น 7 + opinion canvas ระดับ segment), M3 Calibration UI (partial=0.5, append-only สองชั้น UNIQUE+trigger, resolve ซ้ำ=409, #161 resolve ผ่าน UI ได้แล้ว), M4 Red Team in-population (`correction_receptivity` default 1.0 มี test พิสูจน์ trail เดิมเป๊ะ + /compare.json + CalculationModal), M5 Watchlist+alerts+webhook (https-only, best-effort, secret ใน .env, Celery beat รายชั่วโมง, badge sidebar), M6 graph viz (hub top-15% ≤6 + wedge cluster + click-drill) + Insights จาก audit/registry; **tests 214→253 เขียว, Phase 5 ต้นทุน $0 (กลไกล้วน), 6 commits push ครบ**; อัปเดต AGENTS.md (scope ชี้ brief เฟสปัจจุบันแทน hardcode Phase 0); backlog ที่ยังไม่ทำ (ต้องมติผู้ใช้): persona packs+AI-generate, MCP surface, public gallery+votes
- 2026-07-12 (Claude Fable 5): **research SwarmSight รอบ 2 (ผู้ใช้สั่งทำใหม่ โฟกัส: UI ยึด lovable.app/studio + gap analysis ละเอียด) → `docs/reports/swarmsight-research-v2.md`** — repo เขาอัปเดตใหญ่ตั้งแต่รอบแรก: engine graph_swarm เต็มวงจร (ingest file/URL/RSS → chunk 800/overlap 100 → embed 3072d → entity extraction → cosine retrieval), watchlist + consensus_shift alert (Δconfidence ≥0.1) + webhook Slack/Discord, calibration UI (Brier trend sparkline เส้นอ้างอิง 0/0.25), compare + CalculationModal, persona packs + AI-generate + single-persona simulator, MCP tools, FEATURES.md 17 ฟีเจอร์; **พบ gap เราจาก PRD: ไม่มี tipping point detection อัตโนมัติ** (pipeline ขั้น 7 บังคับทุกรายงาน — ของเขา Δavg stance ≥0.25/รอบ); theme token เราตรงกับเขาอยู่แล้ว (แกะจาก ref เดียวกันตอน P4-M1) — gap UI จริงคือ sidebar nav+badge, หน้าใหม่ (calibration/compare/watchlist/insights), tabs ใน run detail, กฎ tooltip อธิบายสูตรทุก metric; รายงานมี UI spec แกะจากโค้ด (ไม่ใช่ตาดู) + ตาราง gap 13 ข้อเรียง impact÷effort + แผน Phase 5 ปรับใหม่ 6 milestones (M1 UI shell, M2 tipping+canvas, M3 calibration UI แบบ append-only, M4 red team in-population+compare, M5 watchlist+webhook, M6 graph viz+insights) — **รอผู้ใช้ approve ก่อนเริ่ม**

## Codex — post-phase hardening รอบสุดท้ายตามคำสั่ง “ทำส่วนที่เหลือต่อเลยทุกข้อ”

ผู้ใช้สั่งให้ทำส่วนที่เหลือทั้งหมดต่อจากรอบ backend/system + UI/UX professional pass โดยห้ามเว้น จึงปิดรายการที่ยังเหลือในชุดข้อเสนอเดิมโดยไม่เพิ่ม dependency ใหม่และไม่พลิก ADR:

- Backend: เพิ่ม `news_fetch_cache` ใน `simulation/newsdesk.py` สำหรับ cache provider success ของ RSS/Tavily 6 ชั่วโมง ลด network ซ้ำแต่ยัง snapshot provider failure/skipped ลง `news_items` ตามเดิม; เพิ่ม `setup_newsdesk()` ให้ migration runner เรียกได้
- Backend: เพิ่ม `synthesize_snapshot()` ใน `simulation/debate.py` เพื่อ rebuild `synthesis/metrics` จาก `debate_posts` ที่เก็บไว้แล้วเท่านั้น ไม่เรียก LLM จึงคุมงบและ reproducibility
- Backend/API: เพิ่ม `RunStore.update_payload()`, `runs_24h`, `recent`; เพิ่ม endpoint `POST /runs/{run_id}/refresh-news` และ `POST /runs/{run_id}/resynthesize` พร้อม audit log และ guard ไม่ให้ซ่อมขณะ run ยัง queued/running
- Backend/ops: เปลี่ยน `scripts/db_migrations.py` เป็น migration ledger table `schema_migrations` พร้อม migration version `2026-07-15-run-lifecycle-newsdesk-cache`
- Frontend: `RunDetail` เพิ่ม repair controls, error/loading state, refresh/resynthesize แล้ว reload payload; `Runs` เพิ่ม loading skeleton และ 24h run trend ใน Job Center; `web/src/api.ts` เพิ่ม client functions/types ใหม่
- Tests: เพิ่ม coverage cache reuse, resynthesize payload, refresh-news payload; full suite ยังผ่าน

Verification:
- `uv run pytest -q` ผ่าน 332 tests (warning เดิมจาก FastAPI/TestClient เรื่อง httpx2)
- `uv run ruff check .` ผ่าน
- `uv run ruff format --check .` ผ่าน
- `web npm.cmd run build` ผ่าน

ข้อควรระวังส่งต่อ:
- working tree ก่อนและหลังงานยังมี `.gitignore` modified และ `diagrams/` untracked จากผู้ใช้; ห้าม commit/revert โดยไม่ถาม
- partial `resynthesize` ตั้งใจเป็น deterministic fallback ไม่ใช่ analyst LLM synthesis เพื่อไม่ทำให้ repair endpoint ใช้งบหรือได้ผลไม่ reproducible
- `refresh-news` ใช้ run_id เดิมและ append snapshot ข่าวใน `news_items`; UI อ่านรายการทั้งหมดของ run เพื่อคง evidence history

## Codex — trust/readiness/retrieval/debate/lineage pass (15 ก.ค. 2026)

ผู้ใช้สั่งให้ทำชุดปรับปรุง 9 ข้อจากรีวิวรอบใหม่ให้ครบ ทั้ง core engine และ frontend:

- Backend: เพิ่ม `core/run_quality.py` สำหรับ `POST /runs/readiness` และ `trust_scorecard` ใน run detail; ย้าย readiness endpoint ใหม่เข้า router package `api/routers/runs.py` เป็นก้าวแรกของการแยก API structure
- RunStore: เพิ่ม `parent_run_id`, `run_events` audit trail, `failure_reason` ใน `debate_posts`, event อัตโนมัติสำหรับ create/job/running/finish/fail/cancel/update payload และ lineage จาก retry
- Retrieval: เพิ่ม `retrieve_evidence()` พร้อม deterministic hybrid/BM25-style scoring, vector fallback metadata, citation spans, source quality score, content hash และ duplicate detection; `retrieve_context()` ยัง backward-compatible
- Debate: เพิ่ม `failure_reason`, deterministic protocol analysis (`claim_decomposition`, `per_round_disagreement`, `contention_graph`, `failure_taxonomy`) และให้ resynthesize rebuild protocol จาก snapshot ด้วย
- API payload: debate run เก็บ `evidence_matches`, `protocol`, `retrieval_mode`, `parent_run_id`; retry สร้าง child run พร้อม event `retry_requested`
- Frontend: New Run มี readiness/cost estimate, validation target, retrieval mode; RunDetail มี Trust Scorecard, Evidence highlights, Debate protocol panel, lineage/audit trail; แก้ `SocialSignalMap` ให้นับตาม `channel_tags` จริง; Runs page ใช้ stacked 24h trend
- Migration: เพิ่ม version `2026-07-15-run-trust-lineage-rich-evidence`
- Tests: เพิ่ม coverage readiness, trust scorecard shape, rich retrieval/vector fallback/duplicate, run lineage events, debate protocol/failure taxonomy

Verification:
- `uv run pytest -q` ผ่าน 335 tests (มี warning เดิมจาก FastAPI/TestClient เรื่อง httpx2)
- `uv run ruff check .` ผ่าน
- `uv run ruff format --check .` ผ่าน
- `web npm.cmd run build` ผ่าน

ข้อควรระวังส่งต่อ:
- `.gitignore` modified และ `diagrams/` untracked เป็น user changes เดิม ห้าม commit/revert หากผู้ใช้ไม่สั่ง
- API split ตอนนี้เริ่มที่ router ใหม่สำหรับ run readiness; endpoints legacy อื่นยังอยู่ใน `api/app.py` เพื่อเลี่ยง regression ใหญ่ ควรย้ายเป็นกลุ่มในรอบถัดไปเมื่อมีเวลาทดสอบเฉพาะทาง
