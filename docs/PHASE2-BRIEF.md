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

### P2-M5 — Living Memory + Conversational Querying (SIM-05/08) ✅ (6 ก.ค. 2026)
- [x] `simulation/memory.py` (WorldMemory, PostgreSQL ตาม D4): kind = real_event/sim_result/user_note, workspace isolation, `latest_belief()` → run ถัดไป preseed จากสถานะที่โลกจำได้, `reset_world()` + audit บังคับ — **ทุกข้อความผ่าน PII detector ก่อนบันทึก** (กฎเหล็กข้อ 1); คอลัมน์ embedding จองไว้ ยังไม่เปิดใช้ (semantic search = งานตอน scale จริง)
- [x] Demo ต่อเนื่องจริง: run 1 จบ 20% → run 2 อ่านความจำ เริ่มที่ 20% → จบ 40%
- [x] `simulation/ask.py` (SIM-08): analyst เห็นเฉพาะ trail ที่กรองแล้ว, คำตอบต้อง cite [เลข] เหตุการณ์จริง — อ้าง index มั่วถูกตัด, ไม่มี citation = ติดธง "อย่าใช้ตัดสินใจ" (fail-closed); demo ตอบพร้อมหลักฐาน 4 เหตุการณ์ตรวจสอบได้
- [x] Unit tests +9 (รวม 168 เขียว)

### P2-M6 — Influence Graph + Impact Waterfall + Media/Rumor (SIM-09/10, FAB-03/04) ✅ (6 ก.ค. 2026)
- [x] SIM-09 (`simulation/influence.py`): influence matrix จาก trail — **ระดับ segment เท่านั้น** (เครดิตเฉลี่ยให้กลุ่มของผู้แชร์ขณะนั้น ไม่มี edge รายบุคคล), hub segments + cluster pairs; test บังคับว่า output ไม่มี agent id (กฎเหล็กข้อ 7); engine เพิ่ม log "seeded" (ผู้แชร์คนแรกเคยหายจาก trail)
- [x] SIM-10 (`graphlayer/waterfall.py`): Impact Waterfall 2-3 hop จาก Neo4j — ผลจริง: จาก "กทม." เจอ 30 entities ทางอ้อมพร้อมเส้นทางเต็ม (ระวังซ้ำบทเรียน M2: shortestPath ใช้ min length ≥2 ไม่ได้)
- [x] FAB-03 (`simulation/media.py`): สำนักข่าวจำลอง 3 stance (amplify/filter/neutral) — prompt ห้ามบิดข้อเท็จจริง + ย้ำใช้ในโลกจำลองเท่านั้น
- [x] FAB-04: `rumor_mutation_rate` ใน engine (0-1 ปรับได้) — ข่าวลือเพี้ยนเฉพาะ closed group, mark ต่อ agent + log trail + `mutation_share()` metric, deterministic
- [x] Unit tests +11 (รวม 179 เขียว)

---

## สรุปปิด Phase 2 (6 ก.ค. 2026) — milestones ครบ P2-M1..M6

| Exit criteria (เชิงเทคนิค) | ผล |
|---|---|
| (1) REH-01 ตอบโต้ ≤ 10 วิ + scorecard | **ผ่าน ✅** — latency จริงสูงสุด 2.8 วิ (หลังแก้ hidden reasoning) |
| (2) REH-03 ≥ 3 ตา + decision tree | **ผ่าน ✅** — บังคับที่โค้ด + ทางเลือกที่ไม่ได้เดินทุกตา |
| (3) War room + divergence alarm ยิงเมื่อ inject ความเบี่ยง | **ผ่าน ✅** — 95% หลุดซอง [40,80] → alarm; noise 2% ไม่ยิง |
| (4) SIG metadata ครบ + OOS harness + GOV-02 ปิด signal | **ผ่าน ✅** — 403 ที่ endpoint + harness ปฏิเสธตัวอย่างเล็ก |
| (5) Living memory ข้าม run + reset | **ผ่าน ✅** — demo 20%→(จำ)→40% + SIM-08 cite trail จริง |
| (6) governance ครบทุก feature + tests เขียว | **ผ่าน ✅** — 179 tests; ทุก run มี audit+prediction+watermark |

tests 179 เขียว | ต้นทุนสะสมทั้งโปรเจกต์ ~$0.58 | ยังใต้ cap 10 agents ตลอด
**หมายเหตุ calibration**: เกณฑ์ PRD "ดีกว่า baseline ≥ 15%" วัดได้เมื่อ predictions ทยอยครบกำหนด (คิวแรก 8 ก.ค. จาก war room, ชุดใหญ่ 4 ส.ค.) — resolve ด้วย `scripts/resolve_predictions.py` แล้ว rebuild benchmark page
**งานที่ defer**: TRUST-08 hybrid panel (รอผู้ใช้ sourcing คนจริง) | **ถัดไป: Phase 3 (Citizen) หรือขยาย scale — รอผู้ใช้สั่ง**

## กติกาที่สืบทอด (ดู AGENTS.md)

fail-closed ทุกด่าน · LLM ผ่าน adapter+BudgetGuard เท่านั้น · วัดซื่อสัตย์ · ทุก run เขียน prediction ≥1 + audit ·
ทุก export ผ่าน watermark · GOV-02/05 บังคับโค้ด · อัปเดต STATE.md ทุก session · push GitHub ทุก commit
