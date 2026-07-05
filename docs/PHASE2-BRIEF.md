# PHASE 2 BRIEF — Rehearsal & Signal (ชิมลาง)

เริ่ม 6 ก.ค. 2026 (มติผู้ใช้ — approve แผนแล้ว) — scope ตาม PRD Release Plan Phase 2:
REH-01/03/04/05, SIG-01..04, SIM-05/08/09/10/11, FAB-03/04 | **TRUST-08 defer** (ต้องใช้ panel คนจริง — รอผู้ใช้ sourcing, เตรียม interface รองรับ)
**ข้อจำกัดคงเดิม: ทุก run ≤ 10 agents + งบ $50/เดือน** (ผู้ใช้จะขยาย scale เองเมื่อระบบเสร็จครบทุกเฟส)

## Exit criteria (เชิงเทคนิค dev-scale — criteria เชิงธุรกิจของ PRD เช่น "war room ใช้จริง ≥3 incident" เป็นเรื่องผู้ใช้)

1. REH-01: interactive rehearsal ตอบโต้ ≤ 10 วิ/คำถาม + scorecard ทุก session (วัด latency จริงในรายงาน)
2. REH-03: เกม ≥ 3 ตา + decision tree ในรายงาน
3. REH-04/05: วงจร sync → simulate 48 ชม. → divergence metric ทำงาน + alarm ยิงเมื่อ inject ความเบี่ยงทดสอบ
4. SIG-01..04: ทุก response มี metadata บังคับ (run id, fragility, calibration, provenance hash) + out-of-sample harness วัด IC/hit rate เทียบ baseline + GOV-02 ปิด signal ใน election scenario (test ครอบ)
5. SIM-05: world state คงข้าม run + reset ได้ | SIM-08: คำตอบอ้าง reasoning trail จริง
6. ทุก feature ครบวงจร governance เดิม (audit + prediction ≥1 + watermark) + tests เขียวทั้งหมด + calibration ดีกว่า baseline วัดได้เมื่อ prediction ชุดแรกครบกำหนด (4 ส.ค. 2026)

## Milestones

### P2-M1 — Press Conference Rehearsal สด (REH-01) ✅ (6 ก.ค. 2026)
- [x] `simulation/rehearsal.py`: นักข่าว 3 สาย (การเมือง/เศรษฐกิจ/สืบสวน) ถามต่อเนื่องจาก transcript, ชาวเน็ต react ผ่าน voice layer — ผู้เข้าร่วม 3+4=7 ≤ cap 10 (raise ถ้าเกิน)
- [x] CLI (`scripts/run_rehearsal.py`): โหมดสด + `--answers` scripted mode — **latency วัดจริงสูงสุด 2.8 วิ/คำถาม (เป้า ≤ 10 ✅)** หลังแก้ hidden reasoning
- [x] Scorecard analyst (temp 0 + JSON + retry 1): demo จริงจับคำตอบเสี่ยงที่ฝังไว้ได้ครบ — "คนเดือดร้อนจริงมีไม่มาก" ถูกจัดอันดับราดน้ำมัน #1 + ยกเป็นประโยคเสี่ยงถูกตัดทำดราม่า
- [x] GOV-05 ใน prompt + test: วิจารณ์ได้ ห้ามร่างคำแถลงใหม่/สคริปต์ให้
- [x] ครบวงจร governance: audit + prediction (ประเด็นราดน้ำมัน top, due 30 วัน, โดเมนนโยบาย) + watermark export
- [x] Unit tests +9 (รวม 132 เขียว) — รวม test adapter param `reasoning`
- **บทเรียนสำคัญ**: crowd model (qwen3.5-flash) เผา ~1,200 hidden thinking tokens/call (14.5 วิ) กับงานที่ตอบ 1 ประโยค — เพิ่ม `reasoning=False` ใน adapter สำหรับ path interactive (rehearsal/voice) → 0.5 วิ + ถูกลง 10 เท่า; งานคิดลึก (judge/hindcast/benchmark) คง default เดิมเพื่อไม่กระทบคุณภาพตาม ADR-0001

### P2-M2 — Game Mode (REH-03) ✅ (6 ก.ค. 2026)
- [x] `simulation/game.py`: เราเดิน → strategic actor (analyst tier, GOV-05 ใน prompt) เดินตอบ → สังคม react ผ่าน **engine กลไก deterministic** (ข้อความสองฝั่งแข่งกันแพร่ วัดสัดส่วนผู้เชื่อ) — ≥ 3 ตาบังคับที่ `decision_tree()`
- [x] Decision tree: เส้นทางจริง + ทางเลือกที่ไม่ได้เดินต่อตา (analyst temp 0 + fail-closed เก็บข้อมูลเกมแม้ parse พัง) | CLI สด + `--moves` scripted
- [x] ครบวงจร governance + demo จริง ($0.001): ฝ่ายค้านตอบโต้เชิงชั้น (เอกสารวิชาการ/คำถามเชิงกระบวนการ), ความเชื่อฝั่งเราไต่ 20%→40%→60% ตามการเดิน 3 ตา
- [x] Unit tests +6 (รวม 138 เขียว)

### P2-M3 — Live War Room + Divergence Alarm (REH-04/05 + SIM-11) ✅ (6 ก.ค. 2026)
- [x] `simulation/warroom.py`: feed aggregate (yaml, ค่า 0-1 เท่านั้น) → `FabricSimulation.preseed()` sync โลกจำลองตรงค่าจริง → forecast 48 ชม. (12 rounds × 5 seeds = envelope) — กลไกล้วน $0, deterministic
- [x] Divergence: ค่าจริงหลุด envelope เกิน tolerance 0.02 → 🚨 alarm ("มีตัวแปรที่ยังไม่ถูก model") — demo จริง: t+36 กระโดด 95% หลุดซอง [40%,80%] alarm ยิง, t+12 (หลุด 2% = noise) ไม่ยิง
- [x] SIM-11 gate จริง: `load_feed()` เรียก `ensure_external_retrieval_allowed(ctx)` — hindcast_mode = raise (test ครอบ); note ใน feed ผ่าน PII detector, พบ = block ทั้ง feed (GOV-01)
- [x] Governance ครบ + prediction แบบ resolve ได้จริงใน 2 วัน (belief share จะอยู่ในช่วง envelope) — อาหารชั้นดีของ Calibration Engine
- [x] Unit tests +8 (รวม 146 เขียว)

### P2-M4 — Sim-to-Signal API + Out-of-Sample Harness (SIG-01..04) ✅ (6 ก.ค. 2026)
- [x] `trust/signal.py`: 6 features จากกลไกจริง per-seed + CI95 (momentum/dispersion/sentiment divergence/contrarian/adoption/consensus fragility) — deterministic ต่อ seed
- [x] SIG-03/04: metadata บังคับทุก response (run id/fragility/calibration note/provenance hash/model version) + disclaimer เชิงโครงสร้าง + rate limiter (429) ที่ `/signal.json`
- [x] GOV-02 ที่ endpoint จริง: subject เลือกตั้ง → `guard_sim_to_signal()` → **403** (test ครอบ)
- [x] `trust/signal_harness.py` (SIG-02): train/test split ตามเวลาเท่านั้น (กัน look-ahead), Spearman IC + hit rate เทียบ baseline (ทายข้างมากจาก train), **test set < 5 จุด = ปฏิเสธการสรุป** (fail-closed) — endpoint `/signal/oos-test.json`
- [x] Unit tests +13 (รวม 159 เขียว) — รวม harness จับ feature มั่วไม่ให้ผ่าน baseline

### P2-M5 — Living Memory + Conversational Querying (SIM-05/08)
- [ ] World state ต่อ workspace ใน pgvector + "reset world" | ผลรันก่อนหน้า/เหตุการณ์จริงซึมเข้า memory
- [ ] ถามต่อจากโลกจำลอง — คำตอบอ้าง reasoning trail จริง (NFR-08)

### P2-M6 — Influence Graph + Impact Waterfall + Media/Rumor (SIM-09/10, FAB-03/04)
- [ ] Hub nodes + cluster map **ระดับ segment เท่านั้น** (กฎเหล็กข้อ 7) | Impact Waterfall ต่อยอด `query_indirect`
- [ ] สำนักข่าว agent (editorial stance) + rumor mutation rate ใน closed group

## กติกาที่สืบทอด (ดู AGENTS.md)

fail-closed ทุกด่าน · LLM ผ่าน adapter+BudgetGuard เท่านั้น · วัดซื่อสัตย์ · ทุก run เขียน prediction ≥1 + audit ·
ทุก export ผ่าน watermark · GOV-02/05 บังคับโค้ด · อัปเดต STATE.md ทุก session · push GitHub ทุก commit
