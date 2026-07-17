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
| backend | 417/417 tests ผ่าน |
| lint/format | Ruff 180 files ผ่าน |
| migrations | no-op/current |
| API contract | OpenAPI regenerate ผ่าน; endpoint ใหม่มี named response/error models |
| frontend unit | Vitest 3 files / 5 tests ผ่าน |
| frontend E2E | Playwright 20/20 desktop+mobile ผ่าน |
| production build | index 85.81 kB; Project 11.41, Validation 7.14, Rehearsal 10.18 kB lazy |
| visualization | charts 466.67 kB, graph 443.72 kB ยัง lazy |
| dependency audit | npm production audit 0 vulnerabilities |
| MIRACL | 542,166 passages / 733 queries; report `P9-M2-miracl-th.md` |

Initial index 85.81 kB เพิ่มประมาณ 4.6% จาก Phase 8 baseline ~82 kB และต่ำกว่าเพดาน +15%; ระหว่าง
พัฒนาพบ 98.02 kB เพราะ shell import feature API จึงแยก `api-shell.ts` ก่อนปิด gate

## Gate ที่ยังไม่ผ่านและห้ามอ้าง

1. multi-model robustness execution: มี 2–3 model aggregate cost preflight/opt-in contract แต่ยังไม่มี
   model/sample มติผู้ใช้และไม่ควรเริ่ม provider spend เอง
2. TH/EN + WCAG 2.2 AA: route ใหม่มี bilingual/locale/mobile/keyboard E2E แต่ยังไม่ผ่าน full-string และ
   accessibility audit ทั้งแอป
3. Thai usability ≥5 คน: protocol อยู่ `P9-M3-usability-protocol.md`; ยังไม่มี participant/raw result
4. human-panel accuracy/pilot success: import contract พร้อม แต่ไม่มี consented outcomes จึง claim blocked

ด้วยเหตุนี้ brief ติ๊กเฉพาะสิ่งที่เสร็จจริง และ Phase 9 หยุดรอมติ/ข้อมูลภายนอกที่สาม gate นี้
