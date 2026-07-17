# PHASE 9 BRIEF — Pilot-ready Trust & Productized Workflow

เริ่ม 17 ก.ค. 2569 — ผู้ใช้อนุมัติ roadmap 8–12 สัปดาห์และสั่ง implement; ADR-0014 เป็น contract หลัก

## Product scope revision — 18 ก.ค. 2569

- [x] ตามมติผู้ใช้และ ADR-0019 ถอด Project/Evidence, Validation Lab, Press-room Rehearsal และ
  Usability study จาก production ทั้ง UI, API, runtime code และฐานข้อมูล
- [x] migration ลบ 14 operational tables; immutable run/prediction/finding/audit/financial records คงไว้
- [x] production workflow ปัจจุบันเป็น PopulationSet → Run → Result → Export และ live smoke ผ่านจริง
- [x] Executive Readout validate analyst root contract, retry ได้ 1 ครั้งภายใต้ BudgetGuard และ fail-closed;
  legacy payload ที่ไม่ครบแสดงคำเตือน+frozen rerun แทนผลว่าง
- รายการ P9-M2/M3 ด้านล่างเป็นประวัติงานที่เคยส่งมอบ ไม่ใช่ surface ที่ยังเปิดใช้งาน

## P9-M1 — Trusted Run Foundation + UX blockers (trust gate)

- [x] immutable `RunSpecV1`/`RunManifestV1`, canonical hash, snapshots และ legacy-incomplete migration
- [x] manifest/read snapshot/frozen rerun/latest rerun API พร้อมคำอธิบาย best-effort determinism
- [x] run lifecycle compare-and-set, terminal cancel และ worker cancellation checkpoints ทุก stage
- [x] `POST /runs/async` ตอบ 202 + `Idempotency-Key` conflict/reuse contract + run-centric URLs
- [x] worker readiness แบบ TTL heartbeat + fail-fast 503 ก่อน persist เพื่อไม่สร้าง queued row ที่ไม่มี worker
- [x] `SafeOutboundFetcher` กลาง: DNS A/AAAA, non-global block, redirect hop validation,
  protocol/content type/size/decompression limits และ fail-closed
- [x] React Router `HashRouter`, typed route tree, 404, run/gallery/experiment deep links
- [x] mobile header/drawer, running timeline, SSE reconnect/cancel/error recovery
- [x] JSON/PDF export จาก stored snapshot สำหรับทุก engine พร้อม watermark + manifest hash
- [x] named response/error schemas สำหรับ endpoint ที่เพิ่ม/เปลี่ยน และ generated TypeScript contract
- [x] regression: backend, lint, OpenAPI/Vitest/build, Playwright desktop/mobile, migration no-op
- [x] รายงาน migration/concurrency/SSRF/UX screenshots แล้วหยุดรอมติผู้ใช้

ผล gate: ผ่านเมื่อ 17 ก.ค. 2569 — ดู `docs/reports/P9-M1-trust-foundation.md`; ผู้ใช้อนุมัติ M2/M3 ในวันเดียวกัน

## P9-M2 — Project, Evidence และ Validation Lab (historical; decommissioned โดย ADR-0019)

- [x] Project/Case workflow: Brief → Evidence → Population → Assumptions → Run → Compare → Decision
- [x] Evidence Library + immutable `EvidenceSetV1`, version/dedup/health/PII preview
- [x] GraphRAG provenance จาก evidence set ที่ freeze และยังผ่าน BudgetGuard
- [x] รวม Compare/Experiments เป็น Validation Lab + calibration/raw-failure drill-down
- [x] Resolution Inbox/Forecast Calendar พร้อม owner/evidence/Brier/reliability/ECE/CI
- [x] MIRACL Thai จริงแบบ pin revision/hash/license + raw metrics/cost/latency
- [x] consent-based Thai human panel import contract โดยไม่ fabricate outcome
- [x] multi-model robustness 3 models/6 Thai cases/18 calls ผ่าน BudgetGuard; report measured และ failed attempts invalidate แบบ append-only

## P9-M3 — Productize capability เดิม (บางส่วน decommissioned โดย ADR-0019)

- [x] Rehearsal UI: turn-by-turn, pause/resume, operator prompt, scorecard/transcript/decision log
- [x] checkpoint/stage control ในสถาปัตยกรรมเดิมโดยไม่เพิ่ม Concordia dependency
- [x] Run Detail status shell + Result/Evidence/Uncertainty/Validation/Audit tabs
- [x] TH/EN parity และ WCAG 2.2 AA automated audit ทั้งแอป — dictionary/static key/locale + axe 13 routes desktop/mobile, focus/reflow/target tests
- [x] ปิดรายการ usability โดยยุติและถอด surface ตามมติผู้ใช้; ไม่ได้อ้างว่ามีผลทดสอบผู้ใช้จริง

## Acceptance gates ร่วม

- manifest hash stable; persona/source mutation ไม่เปลี่ยน snapshot; legacy label ซื่อสัตย์
- cancel/finish/fail race และ stale worker เขียนทับ terminal state ไม่ได้
- SSRF tests ครบ DNS/IPv4/IPv6/redirect/oversize/content type/decompression
- immediate `202 -> Run Detail`, mobile navigation, keyboard/focus, invalid/gallery deep link,
  SSE reconnect, cancel, export snapshot และ TH/EN parity
- initial bundle เพิ่มไม่เกิน 15% จาก Phase 8 baseline; visualization ยัง lazy-loaded
- ห้ามอ้าง MIRACL/calibration/human-panel/pilot accuracy ก่อนมี pinned raw result + report จริง
- backend 391 tests เดิม, lint, frontend tests/build/E2E และ migration no-op ต้องผ่านเสมอ

## Production-real runtime closure (มติผู้ใช้ 17 ก.ค. 2569)

- [x] supervised Compose startup สำหรับ API+worker+beat, auto-restart และ startup readiness gate
- [x] worker readiness ใช้ heartbeat + Celery control ping; offline เป็น degraded และ async run fail-fast
- [x] immutable PopulationSetV1; synthetic population ต้องรับทราบก่อน freeze/run และมี manifest hash
- [x] Citizen demo ถูกถอดจาก production routes และย้ายเป็น offline CLI
- [x] Debate analyst failure เป็น run error/degraded ไม่ส่ง mechanical fallback เป็น success
- [x] unmocked real-process workflow ผ่าน; ปัจจุบันปรับเป็น Population → Run → worker → Result → Export
- [x] low-cost OpenRouter Debate smoke ผ่าน BudgetGuard: actual USD 0.000411 < cap USD 0.05
- [x] CI แยก backend mocked, browser stubbed, live integration และ manual provider smoke ชัดเจน

ผล gate: ผ่านสำหรับ self-hosted trusted-network runtime — ดู ADR-0018 และ
docs/reports/P9-production-runtime-gate.md; usability ผู้ใช้จริง 5 คนยัง pending ตามเดิม

## Deferred / ไม่ทำใน Phase 9

- simulation engine ใหม่, autonomous long-term memory/outcome scraping, public-vote feedback,
  default multi-model sweep
- War Room/Game Mode/Citizen Portal UI (Phase 10 หลัง trust gate)
- public GA/TLS/OIDC/RLS (ยัง deferred ตาม ADR-0012)
- deep 5,000 agents โดยไม่มีมติผู้ใช้; cap ปัจจุบัน 1,000 agents, `$5/run`, `$50/month`
