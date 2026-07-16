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

## P8-M5 — Core Engine/Retrieval (ค้าง)

- [ ] typed debate moves + lineage + deterministic verifier/analyst judge
- [ ] bounded run-local reflection benchmark
- [ ] embedding adapter ใต้ `core/llm/` + BudgetGuard + pgvector HNSW/BM25/RRF จริง
- [ ] Thai retrieval/evidence/subgroup/social-desirability/future calibration benchmarks
- [ ] OpenTelemetry/Prometheus/provider health dashboards

## เกณฑ์ตรวจชุดที่ปิดแล้ว

- runtime path ไม่มี DDL; migration version mismatch ทำให้ startup fail-closed
- 20 concurrent run + read ผ่านโดยไม่มี deadlock/run-id collision; pool default 32 ปรับได้ด้วย `DB_POOL_MAX_SIZE`
- SSE ใช้ event id replay; Redis เป็น wake-up optimization ไม่ใช่ system of record
- SimulationFinding ไม่เข้า Calibration; legacy ไม่กระทบ Brier หลัก
- mechanical revision ไม่ทับ analyst synthesis
- validation ตรวจงบรวม 3 seeds ก่อน enqueue และ child มี `parent_run_id`
- verification ล่าสุด: 369 tests, ruff check/format, web production build, frontend Vitest/Playwright desktop+mobile, Compose build/up ผ่าน
