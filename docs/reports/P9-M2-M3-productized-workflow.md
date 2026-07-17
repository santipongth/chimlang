# P9-M2/M3 — Projectized trust workflow delivery

วันที่: 17 ก.ค. 2026
มติ: ผู้ใช้อนุมัติให้เดินต่อจาก M1; engineering surfaces ส่งมอบแล้วและหยุดที่ external/user gates

## สิ่งที่ส่งมอบ

- Project workflow + append-only revisions และ deep links
- Evidence Library สำหรับ PDF/DOCX/TXT/CSV/URL/RSS, PII preview/gate, version/dedup/health และ
  immutable `EvidenceSetV1`; Debate run อ้าง frozen set hash/materialized snapshot
- Validation Lab รวม Experiments, raw failure/claim readiness, Resolution Inbox, owner,
  Brier/ECE/reliability/CI และ consent-based human-panel import contract
- MIRACL Thai full governed benchmark พร้อม pinned revisions/raw hashes/append-only report
- Press-room Rehearsal แบบ event-sourced: turn-by-turn, reactions, pause/resume, decision log,
  transcript/scorecard และ transactional aggregate budget reservation + actual monthly ledger
- Run Detail shell: Result, Evidence, Uncertainty, Validation, Audit; Project/Validation/Rehearsal
  routes เป็น lazy chunks และ mobile navigation เข้าถึงด้วย keyboard

## Migration

- `2026-07-17-project-evidence-v1`
- `2026-07-17-validation-lab-v1`
- `2026-07-17-rehearsal-sessions-v1`
- `2026-07-17-rehearsal-leases-v1`

Migration runner รอบสุดท้ายรายงาน `database schema is already current` ตาราง trust registry ใช้
append-only trigger; project session row แก้ได้เฉพาะ operational state/revision pointer ตาม contract

## Verification

| gate | ผล |
|---|---|
| backend | 419/419 tests ผ่าน |
| lint/format | Ruff 181 files ผ่าน |
| migrations | no-op/current |
| API contract | OpenAPI regenerate ผ่าน; endpoint ใหม่มี named response/error models |
| frontend unit | Vitest 4 files / 8 tests ผ่าน |
| frontend E2E | Playwright 26/26 desktop+mobile ผ่าน |
| production build | index 93.14 kB; usability 12.30 kB lazy |
| visualization | charts 466.67 kB, graph 443.72 kB ยัง lazy |
| dependency audit | npm production audit 0 vulnerabilities |
| MIRACL | 542,166 passages / 733 queries; report `P9-M2-miracl-th.md` |

Initial index 85.81 kB เพิ่มประมาณ 4.6% จาก Phase 8 baseline ~82 kB และต่ำกว่าเพดาน +15%; ระหว่าง
พัฒนาพบ 98.02 kB เพราะ shell import feature API จึงแยก `api-shell.ts` ก่อนปิด gate

## Gate ปิดเพิ่มตามมติผู้ใช้

1. multi-model robustness รันจริง 3 โมเดล/6 เคส/18 calls, cost 0.002412 USD,
   agreement 0.888889; ดู P9-M2-model-robustness.md
2. TH/EN contract + WCAG 2.2 AA automated audit ทั้ง 13 routes desktop/mobile ผ่าน;
   ดู P9-M3-accessibility-usability-mockup.md

## Gate ที่ยังไม่ผ่านและห้ามอ้าง

1. Thai usability ≥5 คน: mockup/protocol พร้อม แต่ยังไม่มี participant/raw result
2. human-panel accuracy/pilot success: import contract พร้อม แต่ไม่มี consented outcomes จึง claim blocked

ด้วยเหตุนี้ brief ติ๊กเฉพาะ engineering/model gates ที่มีหลักฐานจริง ส่วน usability/human panel ยัง blocked
