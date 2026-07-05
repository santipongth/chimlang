# PHASE 1 BRIEF — Trust MVP (ชิมลาง)

เริ่ม 5 ก.ค. 2026 (มติผู้ใช้) — scope ตาม PRD Release Plan Phase 1: TRUST-01..07/09, SIM-06, REH-02, DASH-01..04, GOV-02/05/06
**ข้อจำกัดคงเดิมตลอดเฟส: ทุก run ≤ 10 agents** (ผู้ใช้จะขยายเองเมื่อระบบเสร็จครบทุกเฟส)

## Exit criteria (เชิงเทคนิค — ตัด criteria เชิงธุรกิจ/ลูกค้า pilot ออกเพราะเป็นเรื่องของผู้ใช้)

1. Fragility coverage 100%: ทุกรายงาน what-if/simulation มี Fragility Index + confidence label
2. Calibration pipeline ทำงานจริง: resolve prediction ที่ครบกำหนด → Brier score สะสมรายโดเมน
3. Public benchmark page (static) สร้างจากผล hindcast + calibration ได้อัตโนมัติ ทั้งผ่านและไม่ผ่าน
4. กฎ GOV-02/05/06 บังคับระดับโค้ด + test ครอบ

## Milestones

### P1-M1 — Multi-Universe + Fragility (TRUST-04/05/09) ✅ (5 ก.ค. 2026)
- [x] Multi-universe orchestrator (`trust/universe.py`): 5 universes (u0 = ฐาน, u1–4 เขย่า share ±10% ด้วย `PersonaFactory.perturb_shares()` + ชุด seed แยก) — บังคับ ≥ 5 ที่ระดับโค้ด
- [x] Fragility Index 0–100 = % universe ที่ข้อสรุปพลิกจากเสียงข้างมาก (ข้อสรุปต่อ universe มาจากทิศ delta + CI)
- [x] TRUST-05: > 40 → downgrade label + banner เตือน + **confidence ใน prediction registry ถูกคูณลดตาม fragility**; > 70 → ตัวเลขเดี่ยวถูกระงับในรายงาน (แสดงช่วงเท่านั้น) — มี test ครอบทั้งสองเกณฑ์
- [x] `run_whatif.py` รัน multiverse เสมอ + รายงานฝัง fragility (ผลจริง: 5/5 universes "ลดลง" → fragility 0/100)
- [x] Unit tests +12 (รวม 84 เขียว): fragility math, perturb deterministic/normalize, เกณฑ์ 40/70, block point estimate ในรายงาน

### P1-M2 — Calibration Engine + Registry เต็มรูป (TRUST-01/02) ✅ (5 ก.ค. 2026)
- [x] ตาราง `prediction_resolution` append-only (PG trigger + UNIQUE กัน resolve ซ้ำ/แก้ผลย้อนหลัง) + Brier = (confidence−outcome)² + คอลัมน์ domain ใน registry
- [x] คิว `due_unresolved()` + CLI `resolve_predictions.py` (resolve พร้อม audit อัตโนมัติ)
- [x] Calibration dashboard รายโดเมนเทียบ baseline 0.25 (`trust/calibration.py`)
- [x] Public benchmark page: `docs/reports/public-benchmark.md` (ผ่าน watermark) — hindcast รายเหตุการณ์ทั้งผ่าน/ไม่ผ่าน + calibration + ข้อจำกัด 4 ข้อรวม run-to-run variance ที่สังเกตจริง (4/5 → 5/5)
- [x] Unit tests +6 (รวม 90 เขียว): Brier ถูก/ผิด, append-only + no-double-resolve ที่ DB จริง, คิว due, page ต้องโชว์ข้อที่ตก

### P1-M3 — Provenance + Silent Majority + Fidelity Dial (TRUST-06/07, SIM-06) ✅ (5 ก.ค. 2026)
- [x] Persona Provenance Card (`simulation/provenance.py` + `meta.provenance` ใน segments.yaml): แหล่งข้อมูล/วันที่/weighting/bias warnings 3 ข้อ/coverage — ฝังท้ายทุกรายงาน; ไม่มี provenance ใน yaml = raise
- [x] TRUST-07 เต็ม: `RunResult.expressors()/observers()` partition ตรวจด้วย test + รายงานแสดงคู่ voice-vs-population เสมอ (ผลจริง: ผู้แสดงออก 2 vs silent majority 6 จาก 10)
- [x] SIM-06 Fidelity Dial (`simulation/fidelity.py` + `scripts/plan_run.py`): dev/quick/standard/deep ตาม PRD + cost estimate ก่อนรัน — **standard ประเมิน ~$2.49** (voice-sparse, calibrate จาก demo จริง) ต่ำกว่าเป้า $50 มาก; ทุก preset เกิน 10 agents ถูก block ที่ขั้นวางแผน (`PlanBlockedError`)
- [x] Unit tests +7 (รวม 97 เขียว)

### P1-M4 — Red Team Swarm (REH-02)
- [ ] Adversarial agents (troll/สื่อจับผิด/นักกฎหมาย/คู่แข่ง) โจมตี scenario → Attack Surface Report จัดลำดับความเป็นไปได้×ความเสียหาย
- [ ] Unit tests: บทบาทครบ, report จัดลำดับถูก, budget guard ครอบ

### P1-M5 — Governance เฟสสอง (GOV-02/05/06)
- [ ] Election mode: auto-classify + manual flag → บังคับ aggregate-only + ป้าย 3 ชนิด + ปิด Sim-to-Signal
- [ ] GOV-05: ไม่มี code path สร้างคอนเทนต์ชักจูง + test กันถดถอย
- [ ] GOV-06: RBAC ขั้นต่ำ (create/run/export/admin) ระดับ API layer
- [ ] Unit tests: classifier, ป้ายบังคับ, สิทธิ์

### P1-M6 — Executive Dashboard (DASH-01..04)
- [ ] Executive Brief ≤ 3 บรรทัด + Risk Heatmap + Scenario Comparison + Synthetic Voices (voice layer)
- [ ] รูปแบบ: HTML report + REST API (FastAPI ใน api/) — full web UI (React) เป็นงานถัดไปหลังเฟสนี้
- [ ] ทุก output ผ่าน watermark + fragility label (DASH-01 AC)
- [ ] Unit tests + integration ครบ

## กติกาที่สืบทอดจาก Phase 0 (ดู AGENTS.md)

fail-closed ทุกด่าน · LLM ผ่าน adapter+budget guard เท่านั้น · วัดซื่อสัตย์ห้ามแก้เกณฑ์เอง ·
ทุก run เขียน prediction ≥ 1 + audit · ทุก export ผ่าน watermark · อัปเดต STATE.md ทุก session
