# PHASE 8 BRIEF — Prediction Experience + Trusted Agent Runtime

เริ่ม 15 ก.ค. 2569 — ผู้ใช้ส่งแผน 3 ระยะและสั่ง implement; ADR-0011 เป็น contract หลัก

## P8-M1 — Runtime/schema reliability ✅

- [x] migration-only DDL ภายใต้ advisory lock เดียว + ledger versioned
- [x] API/worker schema check แบบ read-only + `psycopg_pool.ConnectionPool` ต่อ process
- [x] one-shot `migrate` service; production API/worker รอ migration สำเร็จ
- [x] queues `fabric`/`debate`/`maintenance`, late ack, bounded publish retry, idempotent claim
- [x] heartbeat + stale detection + explicit stale reason
- [x] SSE replay จาก `run_events.id` แล้วตาม Redis live notification
- [x] safe event envelope ไม่เก็บ prompt/secret และซ่อนข้อความที่ไม่ผ่าน PII policy

## P8-M2 — Prediction contract foundation ✅

- [x] append-only `simulation_findings`; หยุดสร้าง heuristic prediction อัตโนมัติ
- [x] prediction ใหม่ binary + source kind/provenance; legacy rows ไม่ถูกแก้
- [x] Calibration หลักตัด legacy/test; legacy filter แยก
- [x] resolution ใหม่ binary + observed time + evidence URL/name; partial เดิม read-only
- [x] POST/GET `/runs/{id}/predictions`; Run Detail แสดง result kind + CTA
- [x] Validate 3 seeds แบบเลือกใช้ + child lineage + aggregate BudgetGuard ก่อน queue
- [x] report แยก agreement/range/dispersion/overlap/failure/cost จาก analyst confidence
- [x] reliability 5 bins + confidence histogram + Brier baseline/sample size ใน API/UI

## P8-M3 — Output integrity + presentation foundation ✅

- [x] JSON Schema structured output + capability gate + flagged parser fallback
- [x] synthesis revisions append-only; recompute metrics ไม่ overwrite analyst result
- [x] Run Detail deep link `#/runs/{run_id}`
- [x] frontend typed finding/prediction/validation/revision contracts

## P8-M4 — Visualization platform ✅

- [x] TanStack Query cache/SSE reconnect client และ typed OpenAPI client
- [x] ECharts quantile/range, scenario bars, stance beeswarm/timeline, stability matrix
- [x] Cytoscape interactive contention graph + evidence lineage Sankey
- [x] keyboard/reduced-motion/responsive/table fallbacks + Vitest/Playwright

## P8-M5 — Core Engine/Retrieval ✅

- [x] typed debate moves + lineage + deterministic verifier/analyst judge
- [x] bounded run-local reflection benchmark
- [x] embedding adapter ใต้ `core/llm/` + BudgetGuard + pgvector HNSW/BM25/RRF จริง
- [x] Thai retrieval/evidence/subgroup/social-desirability/future calibration benchmarks
- [x] OpenTelemetry/Prometheus/provider health dashboards

## P8-M6 — Experiment workspace + platform completion ✅

- [x] experiment workspace สำหรับ parameter sweep, arbitrary run comparison และ sensitivity analysis
- [x] aggregate BudgetGuard ก่อน enqueue sweep; public votes ไม่ถูกป้อนกลับ engine
- [x] แยก ops/experiment endpoints เป็น routers + services โดยไม่เพิ่ม DDL ใน runtime
- [x] frontend typed discriminated run payloads แทน `Record<string, any>` ใน contract หลัก
- [x] virtualized Debate list + frontend test payload 1,000 posts และ experiment workspace e2e

## P8-M7 — Production hardening ✅ (public-GA architecture ยังรอมติ ADR-0012)

- [x] transactional monthly-budget reservation สำหรับ sweep/3-seed validation; actual spend settle และ release เมื่อจบ/ล้มเหลว
- [x] แยก endpoint กลุ่ม Settings ออกจาก `api/app.py` โดยคง API contract เดิม
- [x] ย้าย main frontend request paths ไป typed OpenAPI client และลด raw fetch ที่ซ้ำกัน
- [x] lazy-load visualization/experiment routes เพื่อลด initial bundle โดยไม่ทำให้ deep link พัง
- [x] เพิ่ม security/external-validation readiness report; ระบุ TLS/OIDC/multi-tenant gates ที่ต้องมี deployment input
- [x] regression: backend, migration, OpenAPI, Vitest/build, Playwright desktop/mobile

## P8-M8 — Engineering debt + active business policy ✅

- [x] แยก Persona/Watchlist endpoint groups ออกจาก `api/app.py` โดย contract/RBAC/governance เดิม
- [x] ย้าย raw `fetch` ใน `web/src/api.ts` ไป generated OpenAPI client ให้เหลือศูนย์
- [x] production soak runner: concurrent Fabric queue/poll/detail/event + cleanup/report (live 20/20)
- [x] ติดตั้ง `httpx2` ให้ Starlette TestClient เลิกใช้ deprecated httpx backend
- [x] formalize active defaults: cost metering/no billing, private source, verified-admin Election,
  semantic memory benchmark gate และแสดงใน Settings
- [x] regression + เปิด dev API/worker/web ให้ผู้ใช้ทดลอง

## เกณฑ์ตรวจชุดที่ปิดแล้ว

- runtime path ไม่มี DDL; migration version mismatch ทำให้ startup fail-closed
- 20 concurrent run + read ผ่านโดยไม่มี deadlock/run-id collision; pool default 32 ปรับได้ด้วย `DB_POOL_MAX_SIZE`
- SSE ใช้ event id replay; Redis เป็น wake-up optimization ไม่ใช่ system of record
- SimulationFinding ไม่เข้า Calibration; legacy ไม่กระทบ Brier หลัก
- mechanical revision ไม่ทับ analyst synthesis
- validation ตรวจงบรวม 3 seeds ก่อน enqueue และ child มี `parent_run_id`
- M5: typed move snapshot มี ID/type/parent/evidence refs; verifier replay ได้และ analyst judge ลดระดับ
  verifier finding ไม่ได้; reflection opt-in จำกัด 2 calls/2400 chars/220 output tokens และไม่มี long-term memory
- embedding model/ราคา/dimension ตั้งจาก Settings/env; ไม่ตั้งหรือ provider ใช้ไม่ได้ = BM25 fallback
  พร้อม provenance; 1536d ใช้ HNSW, dimension อื่นบอกตรงว่า exact pgvector
- telemetry เก็บเฉพาะ provider/operation/status/latency/token/cost/error taxonomy/model version
  ไม่เก็บ prompt/response/secret/PII; `/metrics` และ `/observability.json` รองรับ ops dashboard
- benchmark ดิบอยู่ `docs/reports/P8-M5-benchmarks.md`; fixture เล็กเป็น harness smoke ไม่ใช่หลักฐาน
  ความแม่นโลกจริงหรือ causal benefit ของ reflection
- M6: sweep สูงสุด 12 variants และตรวจ per-run+monthly aggregate budget ก่อน enqueue; workspace
  วิเคราะห์ snapshot ของ stored runs เท่านั้นและ `public_votes_used=false`; contention graph จำกัด 24 segment
  เพื่อไม่ให้ layout O(n²) บล็อกหน้า แต่ Debate feed เก็บครบและ virtualize 1,000 posts
- M7: sweep/validation reservation batch ใช้ transaction advisory lock ก่อน enqueue และ settle/release ตาม actual spend;
  readiness `public-ga` block เมื่อ TLS/pen-test/OIDC/RLS ไม่พร้อม; ADR-0012 ถูก Deferred จึงไม่มี
  fake multi-tenant หรือ TLS vendor choice ใน production code
- verification ล่าสุด: 387 backend tests, ruff check/format, web OpenAPI generate/Vitest/build,
  Playwright 8 tests desktop+mobile, migration no-op ผ่าน
