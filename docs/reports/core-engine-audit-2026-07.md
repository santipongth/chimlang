# Core Engine Audit & Calibration — Fabric / Debate / Red Team (18 ก.ค. 2026)

ตามคำสั่งผู้ใช้: ตรวจสอบ+calibrate เครื่องมือ Fabric, Debate และ Red Team ในวงดีเบต,
research เทียบภายนอก และยกระดับ algorithm — เงื่อนไข: **ไม่รัน LLM จริง** (Fabric รันจริงได้
เพราะเป็นกลไก $0), ส่งมอบรวดเดียว ดู ADR-0022 สำหรับมติการเปลี่ยนกลไก

## 1. ผล audit (ก่อนแก้)

### Fabric (`simulation/engine.py`, `simulation/channels.py`)

| ประเด็น | สถานะก่อนแก้ | ความเสี่ยง |
|---|---|---|
| RNG เส้นเดียวทั้งระบบ | inject ข้อความที่สองเปลี่ยนลำดับ draw ของข้อความแรก | คู่เทียบ A/B (SIM-04 fork, compare, red team) ปน RNG noise — **harness จับได้จริง: delta คำชี้แจงพลิกเป็นบวก +0.04** |
| One-shot exposure | ตัดสินเชื่อครั้งเดียวตลอดชีพ ไม่มี re-exposure | complex contagion (กลไกแพร่หลักของโลกจริง) หายทั้งชั้น |
| เครือข่าย offline_wom | เพื่อนบ้าน = agent_id ติดกันหลัง sort (line graph) | artifact — เพื่อนบ้านเกาะ segment เดียวกันเป็นสายยาว |
| ค่าคงที่กลไก | 1.8 / 0.1 / 2 / 0.4 / 0.5 hardcode กระจาย ไม่มีที่มา | calibrate ไม่ได้จากจุดเดียว; channels.py ระบุเองว่า "ยังไม่ calibrate กับข้อมูลสำรวจจริง" |

### Debate (`simulation/debate.py`)

| ประเด็น | สถานะก่อนแก้ | ความเสี่ยง |
|---|---|---|
| Feed sampling | สุ่ม uniform ≤6 โพสต์ ทุกคนเห็นทุกคนเท่ากัน | ขัด selective exposure/media diet ที่เป็นจุด novel ของระบบ |
| Voice | ทุก agent โพสต์ทุกรอบ | ไม่มี silent majority ในดีเบต (ขัด TRUST-07) |
| Conformity | ไม่วัดเลย | งานวิจัยชี้วงดีเบต LLM เสี่ยง "ฉันทามติปลอม" สูง — ระบบมองไม่เห็น |
| Red Team | ต่างจากคนอื่นแค่จุดยืนตั้งต้น −0.6/−0.3 + ประโยคบทบาท 1 ประโยค | = "soft framing" ซึ่งงานวิจัยพบว่าไม่ต่างจาก baseline อย่างมีนัยสำคัญ |

## 2. งานวิจัยภายนอกที่ใช้ยกระดับ

- Sycophancy/premature consensus ในวงดีเบต LLM: [Peacemaker or Troublemaker (arXiv:2509.23055)](https://arxiv.org/html/2509.23055v1), [Too Polite to Disagree (arXiv:2604.02668)](https://arxiv.org/html/2604.02668), [The Cost of Consensus (arXiv:2605.00914)](https://arxiv.org/pdf/2605.00914) — persona ขั้วตรงข้ามยัง converge >0.88
- แยก "คล้อยตาม" ออกจาก "ถูกโน้มน้าว": [Not All Flips Are Conformity (arXiv:2606.00820)](https://arxiv.org/pdf/2606.00820)
- Identity bias และการรักษาความเห็นต่าง: [Identity Bias via Anonymization (arXiv:2510.07517)](https://arxiv.org/pdf/2510.07517), [Preserving Disagreement (arXiv:2604.26561)](https://arxiv.org/pdf/2604.26561)
- Devil's advocate ได้ผลจริง / soft framing ไม่ได้ผล: [LLM-Powered Devil's Advocate (IUI'24)](https://dl.acm.org/doi/10.1145/3640543.3645199), [Only the Devil's Advocate Works (OpenReview)](https://openreview.net/forum?id=mxBmj5LYU2)
- การ validate simulation: [Integrating LLM in Agent-Based Social Simulation (arXiv:2507.19364)](https://arxiv.org/pdf/2507.19364), [Robustness Audits (arXiv:2605.18890)](https://arxiv.org/pdf/2605.18890), OpinioNet (opinion inertia + external events ชนะ Friedkin-Johnsen/HK/Deffuant บน trajectory จริง)
- Common random numbers เป็นเทคนิคมาตรฐานของ counterfactual simulation (variance reduction ของคู่เทียบ)

## 3. สิ่งที่แก้ (ADR-0022)

**Fabric:**
1. **Common random numbers**: ทุก draw (exposure/belief/share/mutation/preseed/broadcast) เปลี่ยนเป็น
   hashed uniform ต่อ (seed, เหตุการณ์, msg, agent, ...) — ตัวแปรที่ไม่เกี่ยวกับ intervention ได้ draw
   เดิมทุก variant → delta ของคู่เทียบเป็นผลเชิงสาเหตุจริง
2. **Re-exposure (complex contagion แบบ conservative)**: ผู้ที่ได้ยินแล้วยังไม่เชื่อ ถูกโน้มน้าวซ้ำได้
   โอกาสลดครึ่งต่อครั้ง สูงสุด 3 ครั้ง/ข้อความ (`RECONSIDER_MAX=3`, `RECONSIDER_DECAY=0.5`)
3. **เครือข่าย offline_wom**: ring สุ่ม seeded (ผสมข้าม segment) แทนลำดับ agent_id
4. **ค่าคงที่กลไกรวมจุดเดียว** พร้อมป้าย "สังเคราะห์ รอ calibrate": `VIRALITY_BOOST`,
   `ALGO_TREND_THRESHOLD`, `NEIGHBOR_SATURATION` (channels.py), `SAY_DO_CLOSED_BOOST`,
   `KRENG_JAI_PUBLIC_SUPPRESS`, `KRENG_JAI_CORRECTION_SUPPRESS` (engine.py)

**Debate:**
5. **Selective-exposure feed**: weighted sampling ตาม overlap ของ channel_mix (+ฐาน 0.25 กัน echo
   chamber สมบูรณ์) แทน uniform
6. **Voice layer (TRUST-07)**: draw ตาม voice_activity ว่าโพสต์ "แสดงออก" หรือ "เงียบ" — โพสต์เงียบ
   มีจุดยืน (นับใน population) แต่ไม่เข้าฟีดใคร; metrics ใหม่ `voice_share`,
   `voice_population_stance_gap` (say-do gap ระดับวง)
7. **Conformity instrumentation** (ทุก run, retroactive จากโพสต์ที่เก็บ): `per_round_dispersion`,
   `convergence_rate`, `majority_alignment`, `stance_flips` (แยก conforming_without_evidence /
   evidenced_or_argued) และ `consensus_warning` เมื่อวงหุบเข้าฉันทามติเร็ว+แคบผิดปกติ
8. **Red Team = devil's advocate เต็มรูป**: contrarian ระบุ+โจมตีข้อสรุปเสียงข้างมาก ห้ามคล้อยตาม
   ห้าม concede และจุดยืนถูก cap ไม่เป็นบวกเชิงกลไก; auditor ไล่ตรวจ claim ที่ไม่มีหลักฐาน; ฟีดของ
   red team = โพสต์ที่ align กับเสียงข้างมากที่สุด (มีเป้าโจมตีชัด); metrics `red_team_pressure`
   (red_posts / replies / counterclaims / engagement_rate) — GOV-05 คงเดิม

## 4. ผล calibration จริง (Fabric, $0 — `scripts/calibrate_fabric.py`, ดิบ: `.tmp/fabric-calibration.json`)

Scenario ตาม ADR-0003 (rumor preseed 10%, correction broadcast 20% ที่รอบ 8, 30 รอบ, 5 seeds):

| n | penetration | belief (base→corr) | **correction delta** | mutation | reexposed/heard |
|---|---|---|---|---|---|
| 100 | 0.592 | 0.490 → 0.394 | **−0.096** | 0.022 | 0.155 |
| 1000 | 0.663 | 0.517 → 0.418 | **−0.099** | 0.021 | 0.116 |

- **Delta ถูกทิศ (คำชี้แจงลดผู้เชื่อ) และ scale-invariant** (−0.096 vs −0.099) — ก่อนแก้ CRN
  harness วัดได้ +0.04 ที่ n=100 ซึ่งเป็นไปไม่ได้เชิงสาเหตุ (RNG noise)
- FAB-01 latency invariant ผ่าน: isolated closed group ช้ากว่า public feed ทุก seed
  (23+ รอบ หรือไม่ถึง 50% ใน 30 รอบ vs 5–7 รอบ)
- Re-exposure มีบทบาทจริง ~12–16% ของ exposure events

**Sensitivity (perturb ±20%, เรียงตาม |Δ correction delta|)** — ลำดับความสำคัญของการ calibrate
กับข้อมูลสำรวจจริงเมื่อได้ข้อมูล (FAB-05):
1. `public_feed.trust` (แรงสุด: +20% → Δ −0.06)
2. `public_feed.base_rate` / `VIRALITY_BOOST`
3. `line_closed_group.base_rate`
4. `public_feed.correction_factor`, `ALGO_TREND_THRESHOLD`
(ตัวที่เหลือรวม cultural priors มีผล < 0.01 ต่อ headline ที่ ±20%)

## 5. Verification

- Fabric/engine tests เดิมผ่านครบ (test_simulation, test_tipping, test_redteam_compare,
  test_warroom, test_p2m6, test_p1m3) — **ไม่มีการแก้เกณฑ์ test ใดๆ**
- Debate tests 22 ตัว (FakeAdapter) รวมใหม่ 3 ตัว: devil's advocate (prompt/cap/pressure),
  voice layer, conformity flip decomposition
- Ruff + live Fabric smoke ผ่าน API บน Compose: `fabric-20260718-052559-126759-490a550a` complete $0

## 6. ข้อจำกัด (ตรงไปตรงมา)

- **Debate ยังไม่ validate กับ LLM จริงในรอบนี้** (มติผู้ใช้: ไม่รัน LLM) — metrics ใหม่ทั้งหมดจะ
  ปรากฏใน payload ของทุก run ที่ผู้ใช้รันเอง; conformity/red-team pressure ของ model จริงต้องอ่าน
  จาก run จริงเท่านั้น
- `voice_share`/`voice_population_stance_gap` แม่นเฉพาะ payload ของ run ใหม่ (คอลัมน์ DB ของ
  posts ไม่มี expressed — snapshot rebuild จะเห็นเป็น 1.0)
- ตัวเลข channel params ยังเป็นค่าสังเคราะห์ — sensitivity ranking ข้างบนคือลำดับที่ควรหาข้อมูล
  จริงมา calibrate ก่อน (public_feed.trust สำคัญสุด)
- `majority_alignment` ใช้ค่าเฉลี่ยรอบก่อนเป็น proxy ของเสียงข้างมากที่ agent เห็น (ฟีดจริงเป็น
  subset) — เป็น proxy ที่ documented ไม่ใช่ค่าตรง
