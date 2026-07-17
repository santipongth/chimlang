# P9-M1 — Trusted Run Foundation และ UX blockers

วันที่ปิด gate: 17 ก.ค. 2569 | สถานะ: **ผ่านทางวิศวกรรม — หยุดรอมติผู้ใช้ก่อน M2**

## Outcome

M1 เปลี่ยนคำว่า reproducible จากการมีเพียง `seed + run_id` เป็น contract ที่ตรวจกลับได้:

- `RunSpecV1` freeze normalized request, seed และ persona population
- `RunManifestV1` freeze evidence/news/posts/result พร้อม code, prompt, adapter, engine, git,
  model, pricing และ governance versions; hash ทุก artifact ด้วย canonical JSON/SHA-256
- manifest จะ `complete=true` เฉพาะเมื่อองค์ประกอบบังคับครบและ run complete; provider ยังระบุ
  `provider-best-effort` ไม่ใช้คำว่า exact replay
- run ก่อน migration เป็น schema 0 / `legacy-incomplete`; ไม่สร้าง provenance ย้อนหลัง

API แยกความหมายเป็น “เปิด stored snapshot เดิม”, “รัน input ที่ freeze” และ “รันด้วยข้อมูลล่าสุด”;
export JSON/PDF อ่าน result จาก manifest snapshot โดยไม่เรียก simulation, LLM หรือ network.

## Migration และ concurrency

Migration `2026-07-17-run-manifests-v1` เพิ่ม:

- `sim_runs.idempotency_request_hash`
- `run_manifests` primary key ตาม `run_id`, 1 manifest ต่อ run
- append-only trigger `reject_mutation()`
- honest backfill ของ run เดิมเป็น schema 0 / incomplete เท่านั้น

รัน migration ซ้ำได้ผล `skip: database schema is already current`. Lifecycle ใช้ CAS
`queued -> running -> complete|error|canceled`; tests ยิง cancel/finish พร้อมกันยืนยันว่าชนะได้เพียง
หนึ่ง transition, late finish/fail/cancel เขียนทับ terminal ไม่ได้ และ stale worker ปิดเป็น error แล้ว
เขียน complete ภายหลังไม่ได้. Worker เช็กสถานะทุก stage และก่อน posts/result/synthesis/finalize.

`POST /runs/async` ตอบ 202 พร้อม run/status/events/manifest/snapshot URLs. `Idempotency-Key`
เดิมกับ semantic request เดิมคืน run เดิม; key เดิมกับ request ต่างตอบ 409.

## SSRF boundary

`SafeOutboundFetcher` เป็นทางผ่านเดียวของ user-controlled URL/RSS:

- อนุญาตเฉพาะ HTTP(S), ไม่มี credentials และ reject hostname/zone ที่ไม่ถูกต้อง
- resolve A/AAAA แล้ว block ทั้ง request หากมี address ใด non-global
- pin TCP connection ไป vetted IP โดยคง Host/TLS SNI เดิม ปิด DNS rebinding ระหว่าง validate/connect
- revalidate ทุก redirect hop และ block HTTPS downgrade
- allowlist content type, จำกัด redirect/compressed/decompressed bytes และ reject encoding ไม่รู้จัก

Tests ครอบ IPv4/IPv6 literal, mixed public/private DNS, global AAAA, redirect ไป loopback,
content type, declared/streamed oversize, malformed/decompression bomb และ IP pinning.

## UX และ contract

- React Router `HashRouter` ที่ `/app/` พร้อม typed route builders, 404 และ direct links ของ
  run/gallery/experiment
- New Run เปิด Run Detail ทันทีหลัง 202; ไม่มี hard timeout 240 วินาที
- mobile header/drawer มี focus entry/trap/restore, Escape, TH/EN label และ target 44px
- Run Detail มี durable-event timeline, SSE state, reconnect/cancel/error recovery และ rerun modes
- endpoints ที่เพิ่ม/เปลี่ยนมี named Pydantic success/error models และ regenerate TypeScript จาก OpenAPI

ภาพหลักฐานอยู่ใน `.tmp/` ตาม protocol:

- `p9-landing-mobile.png`, `p9-new-desktop.png` — local app จริง
- `p9-mobile-drawer-mobile.png`, `p9-running-mobile.png` — Playwright acceptance harness

## Verification ดิบ

| Gate | ผล |
|---|---|
| Backend | 407 passed (391 เดิม + 16 P9 cases) |
| Python quality | Ruff check + format-check ผ่าน 172 files |
| OpenAPI | regenerate สำเร็จ; async/manifest/rerun/snapshot contracts อยู่ใน generated TS |
| Frontend unit | Vitest 3 files / 5 tests ผ่าน |
| E2E | Playwright 14/14 desktop+mobile |
| Build | index 92.67 kB เทียบ Phase 8 ~82 kB = +13.0%, ต่ำกว่า +15% |
| Lazy chunks | router 22.57 kB; graph 443.72 kB และ charts 466.67 kB ยังแยก |
| Dependency audit | production npm audit: 0 vulnerabilities (อัปเดต Router 6.30.3 -> 6.30.4) |
| Migration | no-op เมื่อ ledger current |

## ข้อจำกัดที่ยังคงไว้ตรงๆ

- Frozen rerun ไม่รับประกัน output เท่ากัน bit-for-bit เพราะ provider determinism เป็น best-effort;
  freeze ที่เชื่อถือได้คือ stored snapshot และ manifest hash
- ยังเป็น self-hosted single-tenant trusted-network profile; TLS/OIDC/RLS ยัง deferred ตาม ADR-0012
- M1 ไม่ได้รัน MIRACL Thai, human panel หรือ pilot usability จึงไม่อ้าง retrieval accuracy,
  calibration accuracy หรือ pilot success
- Project/Evidence Library/Validation Lab เป็น M2 และยังไม่ได้เริ่ม

## Gate decision

M1 ผ่าน acceptance ทางวิศวกรรมครบ. ตาม ADR-0014 ต้องหยุดตรงนี้และรอผู้ใช้ตัดสินว่าจะอนุมัติ P9-M2,
ให้แก้ M1 เพิ่ม หรือเปลี่ยน roadmap.
