# PHASE 4 BRIEF — Production Readiness (ชิมลาง)

เริ่ม 6 ก.ค. 2026 (ผู้ใช้ approve แผน) — เป้าหมาย: จาก dev-complete (Phase 0-3 ครบ) → ระบบใช้งานจริงได้
ไม่ใช่เฟสของ PRD Release Plan (ซึ่งจบแล้ว) แต่เป็นงาน hardening ตาม NFR + Tech Decisions ที่ค้าง

## Milestones (ผู้ใช้ approve ลำดับแล้ว)

### P4-M1 — React Web UI (D8) ✅ (6 ก.ค. 2026)
- [x] Scaffold `web/` manual: Vite 6 + React 18 + TS + Tailwind v4 — build 173KB (gzip 55KB)
- [x] **Theme + layout ตามเว็บ/ภาพอ้างอิงของผู้ใช้**: 2 คอลัมน์ (sidebar ซ้าย + เนื้อหาขวา กึ่งกลาง), พื้นสว่างโทนเย็น + primary เขียวมรกต (แกะ oklch จาก CSS จริงของเว็บอ้างอิง), หัวข้อ serif, การ์ดมุมโค้ง, ปุ่ม/step wizard สไตล์เดียวกับภาพ
- [x] **TH/EN สลับได้ทุกหน้า** (i18n เบา + localStorage, NFR-09) — toggle ที่ sidebar
- [x] 5 หน้า: **Landing** (hero+features), **รันใหม่** (wizard 3 ขั้น: คำถาม+ตัวอย่าง chips+โดเมน → engine/agents → review&run), **Executive Dashboard** (brief+fragility badge+headline range+comparison bars+population share), **Citizen** (Impact Twin+feedback), **การจัดการรัน** (`/runs.json` ใหม่: รันล่าสุดจาก audit + คิว prediction รอ resolve)
- [x] Watermark banner ถาวรทุกหน้า | election scenario โชว์ 403 จาก GOV-02 ตรงๆ
- [x] Dev: Vite proxy → :8000 | Prod: FastAPI เสิร์ฟ `web/dist` ที่ **`/app`** (ชิ้นเดียว) — `make api` แล้วเปิด http://localhost:8000/app/
- [x] Backend เพิ่ม: `GET /runs.json`, `agents` param ที่ dashboard, `GovernanceStore.recent_runs()` | tests +5 (รวม 196 เขียว)
- หมายเหตุ: `web/dist` + `node_modules` ไม่เข้า git — CI ยังไม่ build frontend (คิว P4-M6 ถ้าต้องการ)

### P4-M2 — PDF Export + Watermark ✅ (6 ก.ค. 2026)
- [x] `export_report()` จุดเดียวเดิมรองรับ `.pdf` (governance/pdf.py + fpdf2): watermark visible หัว/ท้าย**ทุกหน้า** + machine-readable ใน PDF metadata (อ่านกลับด้วย pypdf ใน test); ปิด flag = ปฏิเสธ + ไม่มีไฟล์หลุด
- [x] ฟอนต์ไทย Sarabun (OFL, ฝังใน assets/fonts/) + text shaping (uharfbuzz) — สระ/วรรณยุกต์ถูกตำแหน่ง
- [x] `GET /dashboard.pdf`: Executive Brief เป็น PDF — GOV-02 คุมครบ (individual=403, election aggregate ติดป้าย 3 ชนิด**ใน PDF จริง** ตรวจด้วย extract_text)
- [x] tests +4 (รวม 200 เขียว)

### P4-M3 — Queue จริง (Celery + Redis ตาม D7) + หลาย run พร้อมกัน (NFR-03)
- [ ] simulation run เป็น async task + สถานะ/ผลผ่าน API

### P4-M4 — Auth + RBAC บังคับที่ API (GOV-06 เชื่อมจริง) + workspace isolation

### P4-M5 — Deployment: docker production + ตัดสินใจ cloud/region (D9 ค้าง, ผูก PDPA/NFR-04 — ต้องถามผู้ใช้)

### P4-M6 — เก็บตก NFR: UI ไทย/อังกฤษ (NFR-09), security review, availability

## กติกาที่สืบทอด

governance ทุกด่านคงเดิม (watermark/audit/registry/election/PII) · cap 1,000 agents/run ·
BudgetGuard ทุก run · อัปเดต STATE.md ทุก session · push GitHub ทุก commit
