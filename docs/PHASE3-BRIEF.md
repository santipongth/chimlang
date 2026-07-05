# PHASE 3 BRIEF — Citizen + Scale + Quality (ชิมลาง)

เริ่ม 6 ก.ค. 2026 (คำสั่งผู้ใช้: "เริ่ม Phase 3 Citizen, ขยาย scale, และ เก็บคุณภาพ") — 3 สายงานพร้อมกัน:
scope PRD Phase 3 = CIT-01..04 | Scale = ยกเลิก cap 10 (คำสั่งขยายที่ผู้ใช้เคยสงวนไว้) | Quality = หนี้เทคนิคสะสม

## สายที่ 1 — P3-S: ขยาย Scale ✅ (6 ก.ค. 2026)

- [x] **Cap ใหม่: 1,000 agents/run** (จาก 10) — deep 5,000 ยังต้องขออนุมัติผู้ใช้ก่อน; rename `max_agents_dev` → `max_agents_per_run` ทั้ง repo; `RUN_BUDGET_USD_CAP` 1→5 (.env)
- [x] อัปเดตกติกาใน CLAUDE.md / AGENTS.md / memory — BudgetGuard ยังเป็นด่านต้นทุนจริงทุก run
- [x] Perf: `_neighbors` ใช้ index map (เดิม O(n) ต่อ call — หน่วงจริงที่ 1,000 agents)
- [x] API endpoints รับ `agents` param (default 100 = quick) แทนการใช้ cap เป็นขนาด demo
- [x] วัดจริง (`docs/reports/scale-measurement.md`): multiverse 1,000×30×5u ใช้ **5.8 วิ** (เป้า NFR-01 ≤2 ชม.); voice จริง $0.001115/call (thinking-on) / $0.000037 (off) → **Standard run เต็มรูป $25.09 / $0.82 — ผ่านทั้ง ≤$80 (exit Phase 0) และ ≤$50 (PRD) ✅** (extrapolation จากต้นทุน/call วัดจริง — prediction ใน registry รอ run เต็มยืนยัน)
- [ ] **ข้อสังเกตสำคัญที่ต้องตามต่อ**: ที่ 1,000 agents ผล what-if delta = −1.2% (fragility 20) ต่างจาก −16.5% ที่ n=10 — พลวัตการแพร่เปลี่ยนตาม scale, พารามิเตอร์ channel/กลุ่ม LINE (GROUP_SIZE=4, สะพานข้ามกลุ่ม) ต้อง re-calibrate ที่ scale จริงก่อนเชื่อผลเชิงปริมาณ

## สายที่ 2 — P3-C: Citizen Mode (CIT-01..04) ✅ โครงหลัก (6 ก.ค. 2026)

- [x] CIT-01 Personal Impact Twin (`simulation/citizen.py` + `POST /citizen/impact.json`): อินพุต **ตัวเลือกปิด 6 ฟิลด์** (ไม่มี free text = ไม่มีช่อง PII โดยโครงสร้าง), match segment ด้วยกติกาโปร่งใส, ผลเป็น**ช่วงเสมอ** จาก 8 seeds — **session-only มี test พิสูจน์ว่าไม่เขียนอะไรลง DB**
- [x] CIT-02 Portal ฉบับประชาชน (`GET /citizen/portal.html`): ภาษาง่าย + อธิบายว่าทำไมตัวเลขเป็นช่วง
- [x] CIT-03 Feedback Loop (`POST /citizen/feedback.json`): เก็บแค่ (segment, stance จากลิสต์ปิด) — **k-anonymity: aggregate ปล่อยเมื่อ n ≥ 20 เท่านั้น** (test: 19 เสียง = กัก, 20 = ปล่อย)
- [x] CIT-04 disclaimer ถาวรทุก output (ค่าคงที่เดียว, portal มีหัว+ท้าย, test ครอบ)
- [ ] คิวถัดไป: inject aggregate feedback กลับเข้า simulation รอบใหม่ (ครึ่งหลังของ CIT-03) + แสดงต่อสาธารณะว่าเสียงจริงเปลี่ยนผลจำลองอย่างไร

## สายที่ 3 — P3-Q: เก็บคุณภาพ (บางส่วน 6 ก.ค. 2026)

- [x] UTF-8 console บังคับที่ `core/config.py` จุดเดียว — ปิดหนี้ `PYTHONIOENCODING` ทุก script
- [x] REST endpoint `GET /graph/indirect.json` ห่อ `query_indirect` (หนี้ Phase 0)
- [ ] React web UI (dashboard-first ตาม D8) — งานใหญ่ แยก session
- [ ] Calibrate segments.yaml กับข้อมูลสำรวจจริง (สำมะโน สสช. / media use survey) — ต้องได้แหล่งข้อมูลจากผู้ใช้
- [ ] TRUST-08 hybrid panel — ยังรอผู้ใช้ sourcing คนจริง
- [ ] Semantic memory (pgvector embeddings) — เปิดใช้เมื่อความจำโตจน recency ไม่พอ

## กติกาที่สืบทอด

fail-closed ทุกด่าน · LLM ผ่าน adapter+BudgetGuard · ทุก run เขียน prediction ≥1 + audit ·
ทุก export ผ่าน watermark · Citizen = session-only + k-anonymity + disclaimer ถาวร ·
อัปเดต STATE.md ทุก session · push GitHub ทุก commit
