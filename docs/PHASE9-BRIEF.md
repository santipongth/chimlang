# PHASE 9 BRIEF — Pilot-ready Trust & Productized Workflow

เริ่ม 17 ก.ค. 2569 — ผู้ใช้อนุมัติ roadmap 8–12 สัปดาห์และสั่ง implement; ADR-0014 เป็น contract หลัก

## P9-M1 — Trusted Run Foundation + UX blockers (trust gate)

- [x] immutable `RunSpecV1`/`RunManifestV1`, canonical hash, snapshots และ legacy-incomplete migration
- [x] manifest/read snapshot/frozen rerun/latest rerun API พร้อมคำอธิบาย best-effort determinism
- [x] run lifecycle compare-and-set, terminal cancel และ worker cancellation checkpoints ทุก stage
- [x] `POST /runs/async` ตอบ 202 + `Idempotency-Key` conflict/reuse contract + run-centric URLs
- [x] `SafeOutboundFetcher` กลาง: DNS A/AAAA, non-global block, redirect hop validation,
  protocol/content type/size/decompression limits และ fail-closed
- [x] React Router `HashRouter`, typed route tree, 404, run/gallery/experiment deep links
- [x] mobile header/drawer, running timeline, SSE reconnect/cancel/error recovery
- [x] JSON/PDF export จาก stored snapshot สำหรับทุก engine พร้อม watermark + manifest hash
- [x] named response/error schemas สำหรับ endpoint ที่เพิ่ม/เปลี่ยน และ generated TypeScript contract
- [x] regression: backend, lint, OpenAPI/Vitest/build, Playwright desktop/mobile, migration no-op
- [x] รายงาน migration/concurrency/SSRF/UX screenshots แล้วหยุดรอมติผู้ใช้

ผล gate: ผ่านเมื่อ 17 ก.ค. 2569 — ดู `docs/reports/P9-M1-trust-foundation.md`; **หยุดรอมติ M2**

## P9-M2 — Project, Evidence และ Validation Lab (ห้ามเริ่มก่อนมติหลัง M1)

- [ ] Project/Case workflow: Brief → Evidence → Population → Assumptions → Run → Compare → Decision
- [ ] Evidence Library + immutable `EvidenceSetV1`, version/dedup/health/PII preview
- [ ] GraphRAG provenance จาก evidence set ที่ freeze และยังผ่าน BudgetGuard
- [ ] รวม Compare/Experiments เป็น Validation Lab + robustness/calibration failure drill-down
- [ ] Resolution Inbox/Forecast Calendar พร้อม owner/evidence/Brier/reliability/ECE/CI
- [ ] MIRACL Thai จริงแบบ pin revision/hash/license + raw metrics/cost/latency
- [ ] consent-based Thai human panel import contract โดยไม่ fabricate outcome

## P9-M3 — Productize capability เดิม (ห้ามเริ่มก่อน M2 ผ่าน)

- [ ] Rehearsal UI: turn-by-turn, pause/resume, operator prompt, scorecard/transcript/decision log
- [ ] checkpoint/stage control ในสถาปัตยกรรมเดิมโดยไม่เพิ่ม Concordia dependency
- [ ] Run Detail status shell + Result/Evidence/Uncertainty/Validation/Audit tabs
- [ ] TH/EN parity, locale-aware formatting และ WCAG 2.2 AA target
- [ ] usability test ผู้ใช้ไทยอย่างน้อย 5 คน; task completion ≥80%

## Acceptance gates ร่วม

- manifest hash stable; persona/source mutation ไม่เปลี่ยน snapshot; legacy label ซื่อสัตย์
- cancel/finish/fail race และ stale worker เขียนทับ terminal state ไม่ได้
- SSRF tests ครบ DNS/IPv4/IPv6/redirect/oversize/content type/decompression
- immediate `202 -> Run Detail`, mobile navigation, keyboard/focus, invalid/gallery deep link,
  SSE reconnect, cancel, export snapshot และ TH/EN parity
- initial bundle เพิ่มไม่เกิน 15% จาก Phase 8 baseline; visualization ยัง lazy-loaded
- ห้ามอ้าง MIRACL/calibration/human-panel/pilot accuracy ก่อนมี pinned raw result + report จริง
- backend 391 tests เดิม, lint, frontend tests/build/E2E และ migration no-op ต้องผ่านเสมอ

## Deferred / ไม่ทำใน Phase 9

- simulation engine ใหม่, autonomous long-term memory/outcome scraping, public-vote feedback,
  default multi-model sweep
- War Room/Game Mode/Citizen Portal UI (Phase 10 หลัง trust gate)
- public GA/TLS/OIDC/RLS (ยัง deferred ตาม ADR-0012)
- deep 5,000 agents โดยไม่มีมติผู้ใช้; cap ปัจจุบัน 1,000 agents, `$5/run`, `$50/month`
