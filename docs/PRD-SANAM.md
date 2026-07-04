# Product Requirements Document (PRD)

## SANAM — สนามซ้อมอนาคตของสังคมไทย
### AI Social Simulation Platform (Multi-Agent Scenario Rehearsal)

| | |
|---|---|
| **เวอร์ชันเอกสาร** | 1.1 (Draft for review) |
| **วันที่** | 4 กรกฎาคม 2026 |
| **สถานะ** | Draft — รอ stakeholder review |
| **ชื่อผลิตภัณฑ์ (ชั่วคราว)** | SANAM (Simulation & Analysis of Multi-Agent behavior) |
| **เอกสารอ้างอิง** | บทวิเคราะห์ MiroFish / CivicSense (mirofiash.docx), เอกสารเทคนิคเชิงยุทธศาสตร์ MiroFish (workflow 7 ขั้นตอน), MiroFish OSS repo, CAMEL-AI OASIS framework |

---

## 1. ภาพรวมผลิตภัณฑ์ (Product Overview)

### 1.1 Vision Statement

เปลี่ยนบทบาทของ AI จาก "เครื่องมือทำนายผลลัพธ์" (Forecasting) เป็น "สนามซ้อมอนาคต" (Scenario Rehearsal) ที่ผู้บริหาร นักธุรกิจ และประชาชนใช้สำรวจปฏิกิริยาของสังคมใน Digital Sandbox ก่อนสถานการณ์จริงจะเกิดขึ้น — โดยเป็นระบบจำลองสังคมระบบแรกที่ **พิสูจน์ความแม่นของตัวเองได้** และ **จำลองสังคมไทยได้จริง**

### 1.2 Problem Statement

การตัดสินใจเรื่องใหญ่ (นโยบายสาธารณะ, แคมเปญการตลาด, การสื่อสารภาวะวิกฤต, กลยุทธ์ธุรกิจ) มักพังเพราะผู้ตัดสินใจมองจากมุมเดียว ไม่ใช่เพราะขาดข้อมูล เครื่องมือที่มีอยู่ในตลาดแก้ปัญหานี้ได้บางส่วนแต่มีช่องว่างสำคัญ:

1. **พิสูจน์ตัวเองไม่ได้** — ระบบอย่าง MiroFish สร้างเรื่องเล่าที่ดูน่าเชื่อถือ แต่ไม่มีกลไกวัดย้อนหลังว่าแม่นจริงแค่ไหน (Backtest Illusion, Hallucinated Causality)
2. **Synthetic Consensus** — ผลจำลองรอบเดียวอาจสะท้อน bias ของ prompt/model มากกว่าสังคมจริง โดยผู้ใช้ไม่มีทางรู้
3. **จำลองสังคมผิดประเทศ** — engine ปัจจุบันจำลอง Twitter/Reddit ทั้งที่ข้อมูลข่าวสารในไทยไหลผ่าน LINE กลุ่มปิด, Facebook Group และปากต่อปาก ซึ่งมีพลวัตการแพร่ต่างกันสิ้นเชิง
4. **จำลองเฉพาะคนเสียงดัง** — การจำลอง social media มองข้าม silent majority ที่ไม่โพสต์แต่เป็นผู้ลงคะแนน/ซื้อ/ตัดสินใจจริง
5. **เป็นเครื่องมือของผู้มีอำนาจฝ่ายเดียว** — ยังไม่มีผลิตภัณฑ์ใดกลับด้านให้ประชาชนใช้ดูผลกระทบต่อตัวเอง

ผลสืบเนื่องในระดับองค์กรของการมองจากมุมเดียวคือ **Echo Chamber และ Confirmation Bias ของผู้บริหาร** — ทีมที่คิดเหมือนกันยืนยันความเชื่อเดิมของกันและกันโดยไม่มีเสียงต้านที่เป็นระบบ การจำลองด้วย Heterogeneous Agents (กลุ่มตัวอย่างสังเคราะห์ที่แตกต่างกันสูงตามโครงสร้าง stakeholder จริง) จึงเป็นกลไกลดอคติเชิงโครงสร้างนี้โดยตรง

### 1.3 Positioning เทียบคู่แข่ง

| มิติ | MiroFish (OSS) | CivicSense | Market research ดั้งเดิม | **SANAM** |
|---|---|---|---|---|
| จำลอง multi-agent society | ✅ | ✅ (แคบกว่า) | ❌ | ✅ |
| วัดความแม่นย้อนหลังอัตโนมัติ | ❌ | ❌ | ❌ | ✅ **Calibration Engine** |
| ทดสอบกับเหตุการณ์อดีตก่อนใช้ | ❌ | ❌ | ❌ | ✅ **Hindcast Mode** |
| บริบทสังคมไทย (LINE, วัฒนธรรม) | ❌ | บางส่วน | ✅ (แพง/ช้า) | ✅ **Thai Social Fabric** |
| ซ้อมโต้ตอบสด (rehearsal) | ❌ | ❌ | ❌ | ✅ **Active Rehearsal** |
| โหมดสำหรับประชาชน | ❌ | ❌ | ❌ | ✅ **Citizen Mode** |
| ธรรมาภิบาลบังคับใช้เชิงเทคนิค | ❌ | ป้ายกำกับ | n/a | ✅ **Governance Layer** |
| ต้นทุนต่อการศึกษา 1 ครั้ง | $8–15 | ต่ำ | $50K–$5M | เป้าหมาย < $50 |

### 1.4 หลักการออกแบบ (Design Principles)

1. **Honesty over impressiveness** — ระบบต้องบอกได้เสมอว่าตัวเองไม่แม่นตรงไหน ผลลัพธ์ทุกชิ้นมาพร้อมช่วงความไม่แน่นอน ไม่มีตัวเลขเดี่ยวลอยๆ
2. **Directional, not predictive** — ผลลัพธ์เชิงปริมาณใช้บอก "ทิศทางและโครงสร้างของปฏิกิริยา" ไม่ใช่คำทำนายที่รับประกัน
3. **Rehearse, don't decide** — ระบบช่วยซ้อม ไม่ตัดสินใจแทน และไม่แนะนำการหาเสียง/การลงทุนโดยตรง
4. **Provenance everywhere** — ทุก persona, ทุกตัวเลข, ทุกข้อสรุป ตรวจสอบย้อนกลับถึงแหล่งข้อมูลได้
5. **Governance by architecture** — ข้อจำกัดด้านจริยธรรมบังคับใช้ในระดับโค้ด ไม่ใช่แค่ policy บนกระดาษ

---

## 2. เป้าหมายและตัวชี้วัดความสำเร็จ (Goals & Success Metrics)

### 2.1 Business Goals

| Goal | ตัวชี้วัด | เป้าหมาย 12 เดือนแรก |
|---|---|---|
| พิสูจน์ความน่าเชื่อถือ | จำนวน hindcast benchmark ที่ผ่านเกณฑ์และเผยแพร่สาธารณะ | ≥ 10 เหตุการณ์ |
| Adoption ฝั่งองค์กร | องค์กรที่ใช้จริง (paid pilot) | ≥ 15 องค์กร |
| Adoption ฝั่งประชาชน | ผู้ใช้ Personal Impact Twin (Phase 3) | ≥ 50,000 sessions |
| ต้นทุน | ต้นทุน compute ต่อ simulation มาตรฐาน (1,000 agents, 30 rounds) | ≤ $50 |
| ความเร็ว | เวลาจาก brief → รายงานฉบับแรก | ≤ 4 ชั่วโมง |

### 2.2 Product Quality Metrics (North Star)

| Metric | นิยาม | เกณฑ์ |
|---|---|---|
| **Calibration Score** | Brier score ของคำทำนายทิศทางที่ครบกำหนดวัดผล เทียบ baseline (naive forecast) | ดีกว่า baseline ≥ 15% ภายใน 12 เดือน |
| **Fragility Coverage** | สัดส่วนรายงานที่รันแบบ multi-universe และแสดง fragility index | 100% ของรายงาน P0 |
| **Provenance Coverage** | สัดส่วน persona ที่มี provenance card ครบ | 100% |
| **Divergence Detection Recall** | War room ตรวจจับได้เมื่อโลกจริงเบี่ยงจากทุก scenario | ≥ 70% ใน backtest |

### 2.3 Non-Goals (สิ่งที่ผลิตภัณฑ์นี้ *ไม่ทำ* โดยเจตนา)

- ไม่ทำนายผลเลือกตั้งเพื่อเผยแพร่แทนโพลจริง
- ไม่ให้สัญญาณซื้อ/ขายหลักทรัพย์โดยตรง (ให้ได้เพียง feature เชิงปริมาณผ่าน Sim-to-Signal API ที่ผู้ใช้ต้องทดสอบเอง)
- ไม่ทำ microtargeting รายบุคคล ไม่ ingest ข้อมูลส่วนบุคคล/รายชื่อผู้มีสิทธิ์เลือกตั้ง/CRM
- ไม่สร้างคอนเทนต์เพื่อชักจูง (persuasion content generation) — ระบบจำลอง *ปฏิกิริยา* ต่อสาร ไม่ใช่เครื่องผลิตสาร

---

## 3. กลุ่มผู้ใช้และ Persona

| Persona | บทบาท | Job-to-be-done หลัก | Priority |
|---|---|---|---|
| **P1 — ผู้บริหารภาครัฐ / ผู้กำหนดนโยบาย** | อธิบดี, ผู้ว่าฯ, ทีมนโยบาย | ซ้อมปฏิกิริยาประชาชนต่อนโยบายก่อนประกาศ, เตรียมประชาพิจารณ์, บริหารวิกฤต | P0 |
| **P2 — ผู้บริหารธุรกิจ / นักการตลาด / PR** | CMO, Head of Comms, Founder | ทดสอบแคมเปญ/ราคา/แถลงการณ์ก่อนปล่อยจริง, ซ้อมแถลงข่าว, จำลองดราม่า | P0 |
| **P3 — นักวิเคราะห์ / นักวิจัย / Quant** | Strategy analyst, นักวิจัยสังคม, quant researcher | แปลงผลจำลองเป็น feature เชิงปริมาณ, ศึกษาพลวัตความเห็น, ตรวจสอบระเบียบวิธี | P1 |
| **P4 — ประชาชนทั่วไป** | ผู้มีสิทธิ์เลือกตั้ง, ครัวเรือน | เข้าใจว่านโยบายหนึ่งกระทบ "ครัวเรือนแบบฉัน" อย่างไร, เห็นเสียงของกลุ่มอื่น | P2 (Phase 3) |
| **P5 — ผู้ดูแลระบบ / Compliance officer** | Admin องค์กร, DPO | ควบคุมสิทธิ์, ตรวจ audit log, บังคับ election mode | P0 |

---

## 4. ขอบเขต (Scope)

### 4.1 In Scope (v1.0 → v3.0)

- Simulation core แบบ multi-agent พร้อม persistent memory (Living Society Memory)
- Thai Social Fabric: จำลองช่องทาง LINE closed group, Facebook Group, TikTok feed, ปากต่อปาก, สื่อกระแสหลัก
- Trust Layer: Calibration Engine, Hindcast Mode, Fragility Index, Persona Provenance, Silent Majority Layer
- Active Rehearsal: Press Conference Rehearsal, Red Team Swarm, Game Mode, Live War Room
- Citizen Mode: Personal Impact Twin, Public Simulation Portal
- Sim-to-Signal API + out-of-sample testing harness
- Governance Layer: election mode, watermarking, audit log, export controls
- Executive Dashboard & Decision Support: Executive Brief, Risk Heatmap, Scenario Comparison (What-if), Reasoning Behind Numbers
- รายงาน: web dashboard, PDF export พร้อม watermark

### 4.2 Out of Scope

- Mobile native app (Phase 4+, v1 เป็น responsive web)
- การจำลองภาษา/สังคมนอกประเทศไทย (สถาปัตยกรรมรองรับแต่ไม่ ship)
- Real-money trading integration, order execution
- Social listening แบบ real-time ingestion จาก platform จริงในระดับรายบุคคล (ใช้เฉพาะข้อมูล aggregate/สาธารณะ)
- การสร้าง synthetic content เพื่อเผยแพร่จริง

---

## 5. Functional Requirements

> รูปแบบ: `[รหัส] ชื่อ requirement — Priority (P0 = MVP must-have, P1 = สำคัญ, P2 = อนาคต)` พร้อม Acceptance Criteria (AC) สำหรับข้อสำคัญ

### Module A — Simulation Core & Living Society Memory

| ID | Requirement | Priority |
|---|---|---|
| SIM-01 | ผู้ใช้สร้าง "โลกจำลอง" จากข้อมูลตั้งต้น (ข่าว, เอกสารนโยบาย, รายงาน, URL, ไฟล์) ระบบสกัด entity/relationship เป็น knowledge graph อัตโนมัติ (GraphRAG) | P0 |
| SIM-02 | ระบบสร้าง agent population 100–5,000 ตัว แต่ละตัวมี persona, belief, goal, memory และความสัมพันธ์เชิงเครือข่าย โดยสัดส่วน segment อ้างอิงข้อมูลประชากรจริง (สำมะโน/สำรวจ) | P0 |
| SIM-03 | รัน simulation แบบหลาย round (เริ่มต้น 30 rounds) โดย agent อ่านข้อมูล, โพสต์, ตอบโต้, เปลี่ยนความเชื่อ และส่งอิทธิพลต่อกันผ่าน social fabric (Module B) | P0 |
| SIM-04 | **Injectable Events** — ผู้ใช้ inject เหตุการณ์ใหม่กลาง simulation ได้ (ข่าวแทรก, คำแถลง, มาตรการ) และเปรียบเทียบ branch ก่อน/หลัง inject | P0 |
| SIM-05 | **Living Society Memory** — โลกจำลองของ workspace หนึ่งคงสถานะข้าม simulation: เหตุการณ์จริงที่ผู้ใช้ป้อนและผลการจำลองก่อนหน้าซึมเข้า memory ของ agent (ผ่าน memory store เช่น Zep-compatible) พร้อมตัวเลือก "reset world" | P1 |
| SIM-06 | **Fidelity Dial** — ผู้ใช้เลือกระดับความละเอียด (Quick: 100 agents/10 rounds, Standard: 1,000/30, Deep: 5,000/50) ระบบแสดงประมาณการต้นทุนและ marginal accuracy ก่อนรัน | P1 |
| SIM-07 | LLM-agnostic: รองรับทุก model ที่ compatible กับ OpenAI API; config ต่อ workspace | P0 |
| SIM-08 | ถามต่อจากโลกจำลอง (conversational querying): "ทำไมกลุ่ม X พลิกความเห็นใน round 12" โดยคำตอบอ้างอิง reasoning trail จริงของ agent | P1 |
| SIM-09 | **Influence Graph & Cluster Analysis** — วิเคราะห์และแสดงผลเครือข่ายอิทธิพลของ agent: ระบุ Hub Nodes (ผู้นำความคิดจำลอง) และ Cluster Map (การเกาะกลุ่มของชุมชนจำลอง) เพื่อดูว่า narrative ไหลผ่านใครและกลุ่มใดจับตัวกัน — จำกัดผลที่ระดับ segment ในโลกจำลองเท่านั้น ห้าม map ไปยังบุคคลจริง (บังคับโดย GOV-01/02) | P1 |
| SIM-10 | **Indirect Impact Tracing (Impact Waterfall)** — ใช้ knowledge graph ไล่ความสัมพันธ์ทางอ้อม: ผลกระทบลำดับที่ 2–3 ไปยัง stakeholder ที่ไม่คาดคิด (เช่น นโยบายภาษีคริปโตกระทบกลุ่มอาชีพอื่นผ่านโหนดเศรษฐกิจที่เชื่อมโยงกัน) และแสดงเป็น Impact Waterfall ในรายงาน | P1 |
| SIM-11 | **Agent Tool Calling / Real-time Context Injection** — agent ดึงข้อมูลภายนอก (ข่าว เอกสาร รายงาน) ผ่าน GraphRAG ระหว่างรัน เพื่อป้องกันการจำลองที่ล้าสมัย — ต้องถูกปิดอัตโนมัติใน Hindcast Mode เพื่อรักษา data cutoff (TRUST-03) | P1 |

**AC หลัก (SIM-04):** เมื่อ inject event ที่ round N ระบบต้อง fork เป็น 2 branch (มี/ไม่มี event) โดยใช้ seed เดียวกันจนถึง round N และรายงาน delta ของ sentiment/adoption ระหว่าง branch พร้อมช่วงความเชื่อมั่น

**หมายเหตุ pipeline:** SIM-01..03 ดำเนินตามขั้นตอนเชิงยุทธศาสตร์ 7 ขั้น: (1) Ingestion & Knowledge Retrieval (2) Entity & Relationship Mapping (3) Knowledge Graph Construction (4) Synthetic Agent Generation (5) Multi-Agent Social Interaction (6) Emergent Pattern Analysis (7) Strategic Synthesis — โดยขั้นที่ 7 ต้องระบุ **Tipping Points** (จุดเปลี่ยนของ narrative) เป็น output บังคับของทุกรายงาน

### Module B — Thai Social Fabric Layer

| ID | Requirement | Priority |
|---|---|---|
| FAB-01 | จำลองช่องทางอย่างน้อย 4 แบบที่มีพลวัตต่างกัน: (a) closed group แบบ LINE — แพร่ช้าแต่ trust สูง ตรวจสอบยาก, (b) public feed แบบ Facebook/X — แพร่เร็ว มี virality, (c) algorithm-driven feed แบบ TikTok — แพร่แบบ non-network, (d) offline word-of-mouth — จำกัดเชิงภูมิศาสตร์/ชุมชน | P0 |
| FAB-02 | **Cultural Priors** — พฤติกรรมเฉพาะบริบทไทยเป็น parameter ของ agent: เกรงใจ (เห็นต่างแต่ไม่แสดงออกต่อสาธารณะ), การสื่อสารผ่านมีม/ประชด, ความไวประเด็นอ่อนไหว, ช่องว่างระหว่างสิ่งที่พูดกับสิ่งที่ทำ (say-do gap) | P0 |
| FAB-03 | สื่อกระแสหลักจำลอง (สำนักข่าว agent) ที่ขยาย/กรอง narrative ตาม editorial stance ที่กำหนดได้ | P1 |
| FAB-04 | Rumor dynamics: ข้อมูลผิดเพี้ยนได้ระหว่างส่งต่อใน closed group (mutation rate ปรับได้) | P1 |
| FAB-05 | ผู้ใช้ปรับ mix ของช่องทางตาม segment ได้ (เช่น ผู้สูงอายุหนัก LINE, Gen Z หนัก TikTok) โดยมีค่า default จากข้อมูลสำรวจการใช้สื่อของไทย | P0 |

**AC หลัก (FAB-01):** ใน benchmark การแพร่ข่าวลือ ช่องทาง closed group ต้องแสดง latency การแพร่สูงกว่า public feed อย่างมีนัยสำคัญ และ correction (ข่าวแก้) ต้องแพร่เข้า closed group ได้ช้ากว่า — สอดคล้องกับงานวิจัยการแพร่ข้อมูลจริง

### Module C — Trust Layer (หัวใจของผลิตภัณฑ์)

| ID | Requirement | Priority |
|---|---|---|
| TRUST-01 | **Prediction Registry** — ทุก simulation ต้องบันทึกคำทำนายที่ตรวจสอบได้อย่างน้อย 1 รายการ: {claim, ทิศทาง, confidence, วิธีวัด, วันครบกำหนด} แก้ไขย้อนหลังไม่ได้ (append-only) | P0 |
| TRUST-02 | **Calibration Engine** — เมื่อครบกำหนด ระบบดึงผลจริง (จากแหล่งที่ผู้ใช้กำหนด/API สาธารณะ) คำนวณ Brier score และ resolution อัตโนมัติ สะสมเป็น Calibration Dashboard รายโดเมน (การตลาด/นโยบาย/กระแสสังคม) | P0 |
| TRUST-03 | **Hindcast Mode** — รัน simulation กับเหตุการณ์อดีตโดยระบบบังคับ data cutoff (block ข้อมูลหลังวันเหตุการณ์ในทุก layer รวมถึง knowledge ของ LLM ผ่าน adversarial prompt filter + retrieval filter) แล้วเทียบผลกับความจริง; ship พร้อม benchmark เหตุการณ์ไทย ≥ 5 ชุด | P0 |
| TRUST-04 | **Parallel Universe Runs + Fragility Index** — ทุกการรันระดับ Standard ขึ้นไป รัน ≥ 5 universes โดย perturb สมมติฐาน (persona weight ±10%, seed, ลำดับข้อมูล) รายงาน Fragility Index 0–100 (สัดส่วน universe ที่ข้อสรุปหลักพลิก) | P0 |
| TRUST-05 | Fragility Index > 40 → ระบบ downgrade confidence label อัตโนมัติและแสดงคำเตือนเด่นชัดในรายงาน; > 70 → block การ export ตัวเลขเดี่ยวโดยไม่มีช่วง | P0 |
| TRUST-06 | **Persona Provenance Card** — persona ทุกตัว/ทุก segment มีบัตรแสดง: แหล่งข้อมูลที่ใช้สร้าง (พร้อม citation), วันที่ข้อมูล, วิธี weighting, bias warning ที่ทราบ, ระดับความครอบคลุม | P0 |
| TRUST-07 | **Silent Majority Layer** — population แยก "ผู้แสดงออก" (โพสต์/คอมเมนต์) กับ "ผู้สังเกตการณ์" (อ่านอย่างเดียวแต่มีความเห็นและพฤติกรรม) ทุกรายงานแสดง voice share และ population share แยกกันเสมอ | P0 |
| TRUST-08 | **Hybrid Ground-Truth Panel** — เชื่อมแบบสอบถามคนจริงกลุ่มเล็ก (20–50 คน/segment) เพื่อ validate คำตอบของ agent segment เดียวกัน ระบบคำนวณ agreement rate และใช้ปรับ persona อัตโนมัติ (with human approval) | P1 |
| TRUST-09 | Uncertainty UI: ทุกตัวเลขในรายงานมาพร้อมช่วง (interval) และหมวด "อะไรจะทำให้ข้อสรุปนี้เปลี่ยน" (key assumptions) | P0 |

**AC หลัก (TRUST-03):** ผู้ประเมินอิสระสุ่มตรวจ hindcast run แล้วต้องไม่พบการรั่วของข้อมูลหลัง cutoff ใน reasoning trail ของ agent เกิน 2% ของ sample; ผล hindcast ทุกชุดเผยแพร่ใน public benchmark page ทั้งกรณีผ่านและไม่ผ่าน

### Module D — Active Rehearsal

| ID | Requirement | Priority |
|---|---|---|
| REH-01 | **Press Conference Rehearsal** — โหมดสด: ผู้บริหารพิมพ์/พูดคำตอบ, นักข่าว/ชาวเน็ต agent ตอบโต้แบบเรียลไทม์ (latency ≤ 10 วิ/คำถาม), จบ session ได้ scorecard: ประเด็นที่ดับไฟ, ประเด็นที่ราดน้ำมัน, ประโยคเสี่ยงถูกตัดไปทำดราม่า | P1 |
| REH-02 | **Red Team Swarm** — ฝูง agent ปฏิปักษ์ (troll, IO, คู่แข่ง, สื่อสายจับผิด, นักกฎหมาย) มีเป้าหมายเดียว: หาจุดที่ทำให้แผน/สาร/นโยบายพัง ส่งออกเป็น "Attack Surface Report" จัดลำดับตามความเป็นไปได้ × ความเสียหาย | P0 |
| REH-03 | **Game Mode** — จำลองแบบเกมหลายตากับ strategic actor (คู่แข่ง, ฝ่ายค้าน): เราเดิน → ฝ่ายตรงข้ามเดินตอบ → ตลาด/สังคม react ≥ 3 ตา พร้อม decision tree สรุป | P1 |
| REH-04 | **Live War Room** — ช่วงวิกฤต: ป้อนข้อมูลจริงต่อเนื่อง (RSS, ข้อมูล aggregate สาธารณะ), ระบบ sync โลกจำลองกับความจริงและ simulate ล่วงหน้า 48 ชม. ทุก ≤ 60 นาที | P1 |
| REH-05 | **Divergence Alarm** — เมื่อโลกจริงเบี่ยงออกนอกทุก scenario ที่จำลองไว้ (วัดด้วย divergence metric ที่กำหนดไว้ล่วงหน้า) ระบบแจ้งเตือนทันที = สัญญาณว่ามีตัวแปรที่ยังไม่ถูก model | P1 |

### Module E — Citizen Mode (Phase 3)

| ID | Requirement | Priority |
|---|---|---|
| CIT-01 | **Personal Impact Twin** — ประชาชนกรอกบริบท ≤ 10 ฟิลด์ (ช่วงรายได้, ภูมิภาค, การเดินทาง, โครงสร้างครอบครัว, อาชีพแบบกว้าง) ระบบ match เข้า segment แล้วแสดง: ผลกระทบจำลองของนโยบายต่อครัวเรือนแบบเดียวกัน + เสียงจำลองของกลุ่ม + ระดับความไม่แน่นอน — เก็บข้อมูลแบบ session-only ไม่สร้าง profile ถาวรเว้นแต่ opt-in | P2 |
| CIT-02 | **Public Simulation Portal** — หน่วยงานเผยแพร่ผลซ้อมนโยบายฉบับประชาชน (ภาษาง่าย + provenance + ข้อจำกัด) ก่อนประชาพิจารณ์ | P2 |
| CIT-03 | **Feedback Loop** — ความเห็นจริงจากประชาชนบน portal ถูก aggregate (k-anonymity, k ≥ 20) แล้ว inject กลับเข้า simulation รอบถัดไป พร้อมแสดงต่อสาธารณะว่าเสียงจริงเปลี่ยนผลจำลองอย่างไร | P2 |
| CIT-04 | ทุกหน้าของ Citizen Mode ต้องมี disclaimer ถาวรว่าเป็นผลจำลอง ไม่ใช่โพลจริง และไม่ใช่คำสัญญาของรัฐ | P2 |

### Module F — Sim-to-Signal API

| ID | Requirement | Priority |
|---|---|---|
| SIG-01 | Export feature เชิงปริมาณพร้อมช่วงความเชื่อมั่นผ่าน REST API: Narrative Momentum, Narrative Dispersion, Consensus Fragility, Sentiment Divergence (voice vs population), Contrarian Pressure, Bullish/Bearish Shift, Adoption Elasticity, Event Interpretation Gap | P1 |
| SIG-02 | **Out-of-Sample Harness ในตัว** — ผู้ใช้ upload ข้อมูลผลจริง (time series) ระบบทดสอบว่า feature เพิ่ม predictive power จริงไหม (IC, hit rate เทียบ baseline) พร้อม train/test split enforcement — ตอบโจทย์ Backtest Illusion โดยตรง | P1 |
| SIG-03 | ทุก API response ฝัง metadata: run id, fragility index, calibration score ของโดเมนนั้น, provenance hash | P1 |
| SIG-04 | Rate limit + ห้ามใช้เป็น real-time trading signal ใน ToS; response มี disclaimer field เชิงโครงสร้าง | P1 |

### Module G — Governance & Ethics Layer

| ID | Requirement | Priority |
|---|---|---|
| GOV-01 | **ห้าม ingest ข้อมูลส่วนบุคคล** — pipeline นำเข้าข้อมูลมี PII detector; ตรวจพบรายชื่อบุคคล/เบอร์/อีเมล/รหัสบัตร → block และแจ้งผู้ใช้ (allow-list เฉพาะบุคคลสาธารณะในบริบทข่าว) | P0 |
| GOV-02 | **Election Mode** — เมื่อ scenario ถูกจัดประเภทเป็นการเลือกตั้ง/การเมือง (auto-classify + manual flag): ปิด export ระดับต่ำกว่า segment, ปิด Game Mode เชิงหาเสียง, ผลลัพธ์ทุกชิ้นติดป้าย `simulation_estimate / not_field_poll / aggregate_only`, ปิดการใช้ Sim-to-Signal | P0 |
| GOV-03 | **Watermarking** — PDF/ภาพ/ตาราง export ทุกชิ้นฝัง watermark ทั้ง visible และ machine-readable (run id + วันที่ + ป้าย "AI simulation — not a real poll") เพื่อกันการแอบอ้างเป็นโพลจริง | P0 |
| GOV-04 | **Immutable Audit Log** — บันทึกทุก run: ผู้สั่ง, ข้อมูลตั้งต้น (hash), config, ผู้ export; เก็บ ≥ 2 ปี; DPO/admin ตรวจได้ | P0 |
| GOV-05 | ห้ามระบบ generate คอนเทนต์ชักจูงสำเร็จรูป (ad copy, สคริปต์หาเสียง) จากผลจำลอง — ให้ได้เพียง insight ว่ากลุ่มใดกังวลเรื่องใด | P0 |
| GOV-06 | Role-based access control: แยกสิทธิ์ create / run / export / admin; Election Mode ปลดล็อกได้เฉพาะ org ที่ผ่าน verification | P0 |

### Module H — Executive Dashboard & Decision Support

| ID | Requirement | Priority |
|---|---|---|
| DASH-01 | **Executive Brief** — บทสรุปอัตโนมัติไม่เกิน 3 บรรทัด ระบุโอกาสและความเสี่ยงสูงสุดที่ค้นพบจากการจำลอง พร้อมลิงก์เจาะลึกถึงหลักฐาน | P0 |
| DASH-02 | **Risk Heatmap** — แผนที่ความเสี่ยงเชิงภาพ (ความเป็นไปได้ × ความรุนแรง) รายกลุ่ม stakeholder เช่น โอกาสเกิด panic selling ในผู้ถือหุ้นรายย่อย หรือโอกาสเกิด PR crisis ในคนรุ่นใหม่ | P0 |
| DASH-03 | **Scenario Comparison (What-if)** — ตารางเปรียบเทียบผลลัพธ์ระหว่างทางเลือก (เช่น นโยบายแบบ A เทียบแบบ B) รายกลุ่มเป้าหมาย ทำงานร่วมกับ Injectable Events (SIM-04) | P0 |
| DASH-04 | **Reasoning Behind Numbers (Synthetic Voices)** — แสดงตัวอย่างเสียงสะท้อนจำลองรายกลุ่มพร้อมเหตุผลเบื้องหลังตัวเลข เชื่อมกับ drill-down (NFR-08) และแสดง voice share / population share กำกับ (TRUST-07) | P0 |

**AC หลัก (DASH-01):** Executive Brief ทุกฉบับต้องแสดง Fragility Index และ confidence label กำกับเสมอ และห้ามแสดงตัวเลขเดี่ยวโดยไม่มีช่วงความไม่แน่นอน (สอดคล้อง TRUST-05/09)

---

## 6. Non-Functional Requirements

| ID | หมวด | Requirement |
|---|---|---|
| NFR-01 | Performance | Standard run (1,000 agents × 30 rounds × 5 universes) เสร็จภายใน ≤ 2 ชม.; Quick run ≤ 15 นาที; Rehearsal mode ตอบโต้ ≤ 10 วินาที/turn |
| NFR-02 | Cost | ต้นทุน compute ต่อ Standard run ≤ $50 (รวม multi-universe); ระบบแสดง cost estimate ก่อนรันทุกครั้ง |
| NFR-03 | Scalability | รองรับ ≥ 50 simulation พร้อมกัน; agent สูงสุด 5,000 ตัว/run (สถาปัตยกรรมขยายถึง 50,000 ใน Phase 4) |
| NFR-04 | Privacy / กฎหมาย | สอดคล้อง PDPA เต็มรูปแบบ; ข้อมูล Citizen Mode เป็น session-only by default; ไม่มี PII ใน training/memory store; data residency ในไทยหรือ region ที่ลูกค้ากำหนด |
| NFR-05 | Security | Encryption at rest + in transit; workspace isolation ระดับ tenant; SSO/SAML สำหรับ enterprise; penetration test ก่อน GA |
| NFR-06 | Availability | 99.5% สำหรับ dashboard; War Room mode 99.9% ช่วง active incident |
| NFR-07 | Reproducibility | ทุก run reproduce ได้จาก run id (seed, config, data snapshot ถูก freeze) — จำเป็นต่อ audit และงานวิจัย |
| NFR-08 | Explainability | ทุกตัวเลข aggregate drill-down ถึง reasoning trail ระดับ agent ได้ภายใน 3 คลิก |
| NFR-09 | Localization | UI ไทย/อังกฤษ; agent reasoning ภาษาไทยเป็นหลัก; รายงาน export ได้ 2 ภาษา |
| NFR-10 | Model governance | เปลี่ยน LLM backend ได้โดยไม่กระทบ Prediction Registry เดิม; ทุก run ระบุ model version ที่ใช้ |

---

## 7. User Stories หลัก (ตัวอย่าง)

**US-1 (P1, ภาครัฐ):** ในฐานะทีมนโยบายของ กทม. ฉันต้องการจำลองปฏิกิริยาของประชาชน 6 กลุ่มต่อมาตรการเก็บค่าธรรมเนียมรถติด ก่อนเปิดประชาพิจารณ์ เพื่อรู้ว่ากลุ่มใดต่อต้านด้วยเหตุผลอะไร และคำถามยากที่สุดที่จะเจอคืออะไร
*เกี่ยวข้อง: SIM-01..04, FAB-01/02/05, TRUST-04/07/09, REH-02, GOV-01..04*

**US-2 (P2, ธุรกิจ):** ในฐานะ CMO ฉันต้องการทดสอบว่าการขึ้นราคาสินค้า 15% พร้อมข้อความสื่อสาร 3 แบบ จะให้ปฏิกิริยาต่างกันอย่างไรในลูกค้า 4 segment และคู่แข่งน่าจะตอบโต้อย่างไร
*เกี่ยวข้อง: SIM-04/06, REH-03, TRUST-04/05, SIG-01*

**US-3 (P2, PR วิกฤต):** ในฐานะ Head of Comms ระหว่างดราม่ากำลังลุกลาม ฉันต้องการ war room ที่จำลอง 48 ชม. ข้างหน้าทุกชั่วโมง ซ้อมแถลงกับนักข่าวจำลองก่อนแถลงจริง และได้รับแจ้งเตือนถ้าสถานการณ์จริงหลุดจากทุก scenario
*เกี่ยวข้อง: REH-01/04/05, TRUST-01/02*

**US-4 (P3, Quant/นักวิจัย):** ในฐานะนักวิเคราะห์ ฉันต้องการดึง Narrative Momentum และ Consensus Fragility ผ่าน API แล้วทดสอบ out-of-sample กับข้อมูลจริงของฉัน เพื่อพิสูจน์ว่ามันเพิ่ม predictive power จริงก่อนใช้งาน
*เกี่ยวข้อง: SIG-01..04, NFR-07*

**US-5 (P4, ประชาชน):** ในฐานะผู้เช่าบ้านในเขตรอบนอก ฉันต้องการกรอกบริบทครัวเรือน 8 ข้อ แล้วเห็นว่านโยบายขนส่งใหม่กระทบค่าใช้จ่ายและเวลาเดินทางของ "คนแบบฉัน" อย่างไร พร้อมรู้ว่าผลนี้แม่นแค่ไหน
*เกี่ยวข้อง: CIT-01/04, TRUST-06/09*

---

## 8. สถาปัตยกรรมเชิงเทคนิค (Overview)

```
┌──────────────────────────────────────────────────────────┐
│  Presentation: Executive Dashboard · Rehearsal UI ·      │
│  Citizen Portal · PDF Export (watermarked)               │
├──────────────────────────────────────────────────────────┤
│  Sim-to-Signal API  │  Governance Gateway (RBAC,         │
│  (REST + harness)   │  election mode, PII filter, audit) │
├──────────────────────────────────────────────────────────┤
│  Trust Layer: Prediction Registry (append-only) ·        │
│  Calibration Engine · Hindcast Runner (data cutoff) ·    │
│  Multi-Universe Orchestrator · Provenance Store          │
├──────────────────────────────────────────────────────────┤
│  Simulation Core: Agent Runtime (OASIS-compatible) ·     │
│  Persona Factory · Living Memory (Zep-compatible) ·      │
│  Injectable Event Bus · Emergent Pattern Analyzer ·      │
│  Red Team / Game Mode Engine                             │
├──────────────────────────────────────────────────────────┤
│  Thai Social Fabric: channel simulators (closed group /  │
│  public feed / algo feed / offline) · cultural priors ·  │
│  rumor mutation engine                                   │
├──────────────────────────────────────────────────────────┤
│  Data Layer: GraphRAG knowledge graph · Thai population  │
│  priors (census/survey) · public data connectors (RSS,   │
│  open data) · run snapshot store (reproducibility)       │
├──────────────────────────────────────────────────────────┤
│  LLM Abstraction: OpenAI-compatible adapter              │
│  (Qwen / GPT / Claude / local) + model version pinning   │
└──────────────────────────────────────────────────────────┘
```

หมายเหตุการ build vs reuse: Agent runtime และ social simulation ต่อยอดจาก open source (CAMEL-AI OASIS / MiroFish architecture) ได้ — differentiation อยู่ที่ Trust Layer, Thai Social Fabric, Rehearsal และ Governance ซึ่งต้องพัฒนาเอง

---

## 9. ข้อมูลที่ต้องใช้ (Data Requirements)

| ชุดข้อมูล | ใช้ทำอะไร | แหล่ง | ความถี่อัปเดต |
|---|---|---|---|
| โครงสร้างประชากร/เศรษฐกิจสังคมไทย | น้ำหนัก persona segment | สำมะโน สสช., สำรวจภาวะเศรษฐกิจครัวเรือน | รายปี |
| พฤติกรรมการใช้สื่อรายกลุ่มอายุ/ภูมิภาค | ค่า default ของ channel mix (FAB-05) | สำรวจสาธารณะ, รายงาน digital landscape | รายปี |
| คลังเหตุการณ์อดีตสำหรับ hindcast | benchmark TRUST-03 | ข่าวสาธารณะ + ผลจริง (โพลจริง, ยอดขาย, ผลเลือกตั้งที่ประกาศแล้ว) | สะสมต่อเนื่อง |
| ข้อมูลสาธารณะ real-time (aggregate) | War Room sync และ Real-time Context Injection (SIM-11) | RSS feed ≥ 24 แหล่ง (ข่าวธุรกิจ/เทคโนโลยี), open data, trend API (aggregate เท่านั้น) | รายชั่วโมง |
| แบบสอบถาม hybrid panel | validate persona (TRUST-08) | panel ที่ระบบจัดหา (consent-based) | รายไตรมาส |

ข้อห้ามเด็ดขาด: รายชื่อผู้มีสิทธิ์เลือกตั้ง, CRM, private social data, ข้อมูลรายบุคคลทุกรูปแบบ (GOV-01)

---

## 10. ความเสี่ยงและการรับมือ (Risk Register)

| ความเสี่ยง (จากบทวิเคราะห์ต้นทาง) | ผลกระทบ | การรับมือใน spec นี้ |
|---|---|---|
| Synthetic Consensus — agent เห็นตรงกันเพราะ bias ไม่ใช่เพราะสังคมคิดแบบนั้น | ผู้ใช้มั่นใจผิดจุด ตัดสินใจพลาด | TRUST-04/05 (multi-universe + fragility auto-downgrade), TRUST-08 (คนจริง validate) |
| Backtest Illusion — narrative ดูดีแต่ไม่มี predictive power | นำไปใช้เชิง quant แล้วเสียหาย | SIG-02 (out-of-sample harness บังคับ), TRUST-01/02 (registry + scoring) |
| Hallucinated Causality — อธิบายย้อนหลังเก่งแต่ทำนายไม่ได้ | เข้าใจผิดว่าระบบแม่น | TRUST-03 (hindcast แบบ data cutoff เข้มงวด), เผยแพร่ผลทั้งผ่าน/ไม่ผ่าน |
| Reflexivity — บริบทเปลี่ยน ผลลัพธ์เปลี่ยน | ผลจำลองใช้ไม่ได้ข้าม regime | SIM-05 (living memory ตามโลกจริง), REH-05 (divergence alarm), regime metadata ในทุก run |
| Output ดูฉลาดเกินจริง / black box | ตรวจสอบไม่ได้ว่าผิดตรงไหน | NFR-08 (drill-down 3 คลิก), TRUST-06 (provenance), NFR-07 (reproducibility) |
| ถูกนำไปใช้ทางการเมืองผิดวัตถุประสงค์ | ความเสียหายต่อสังคม/แบรนด์/กฎหมาย | GOV-02..06 (election mode, watermark, audit, verification) |
| LLM cost ผันผวน | ต้นทุนเกินเป้า | SIM-06/07 (fidelity dial + model-agnostic, ใช้ model ราคาถูกสำหรับ agent ทั่วไป, model แพงเฉพาะ analyst agent) |
| ประชาชนตีความผลจำลองเป็นคำสัญญาของรัฐ | ความขัดแย้งสาธารณะ | CIT-04 (disclaimer ถาวร), ภาษารายงานฉบับประชาชนผ่าน readability review |
| Influence graph ถูกนำไปใช้ระบุตัวบุคคลจริงเพื่อ targeting | ละเมิดความเป็นส่วนตัว ขัดวัตถุประสงค์ผลิตภัณฑ์ | SIM-09 จำกัดผลที่ระดับ segment ในโลกจำลอง, GOV-01 (PII block), GOV-02 (election mode) |

---

## 11. แผนการปล่อย (Release Plan)

| Phase | ระยะเวลา | ขอบเขต | Exit Criteria |
|---|---|---|---|
| **Phase 0 — Foundation** | เดือน 0–3 | SIM-01..04/07, FAB-01/02/05, GOV-01/03/04, รายงานพื้นฐาน | Hindcast ภายในผ่าน ≥ 3/5 เหตุการณ์; ต้นทุน Standard run ≤ $80 |
| **Phase 1 — Trust MVP (GA แรก)** | เดือน 3–6 | TRUST-01..07/09, SIM-06, REH-02, DASH-01..04, GOV-02/05/06 | ลูกค้า pilot 5 ราย; fragility coverage 100%; public benchmark page เปิด |
| **Phase 2 — Rehearsal & Signal** | เดือน 6–12 | REH-01/03/04/05, SIG-01..04, SIM-05/08/09/10/11, TRUST-08, FAB-03/04 | Calibration ดีกว่า baseline ≥ 15%; war room ใช้จริงใน incident ≥ 3 ครั้ง |
| **Phase 3 — Citizen** | เดือน 12–18 | CIT-01..04, portal ร่วมกับหน่วยงานนำร่อง 1–2 แห่ง | 50,000 sessions; ไม่มี privacy incident; media literacy audit ผ่าน |

---

## 12. คำถามที่ยังเปิดอยู่ (Open Questions)

1. **Hindcast data cutoff กับ LLM knowledge** — LLM รู้ผลเหตุการณ์อดีตจาก training data การ block ด้วย prompt/retrieval filter เพียงพอไหม หรือต้องใช้ model ที่ cutoff ก่อนเหตุการณ์ / fine-tune แบบ knowledge-scoped? ต้อง prototype ใน Phase 0
2. **เกณฑ์ verification สำหรับ Election Mode** — ใครมีสิทธิ์ใช้ scenario การเมือง: เฉพาะหน่วยงานรัฐ? สื่อ? นักวิจัย? ต้องการ legal + ethics review
3. **Hybrid panel sourcing** — สร้าง panel เอง หรือ partner กับบริษัทวิจัยตลาด (trade-off: ต้นทุน vs ความเป็นกลาง)
4. **Business model** — SaaS per-seat, pay-per-run, หรือ enterprise license + Citizen Mode ฟรีแบบ subsidized? กระทบการออกแบบ metering ใน NFR-02
5. **Open source strategy** — เปิด simulation core (ตาม MiroFish) แล้วปิดเฉพาะ Trust Layer + Thai Fabric เพื่อสร้าง community หรือปิดทั้งหมด?
6. **ความรับผิดทางกฎหมาย** — ถ้าองค์กรตัดสินใจตามผลจำลองแล้วเสียหาย ขอบเขตความรับผิดของแพลตฟอร์มอยู่ตรงไหน (ต้องสะท้อนใน ToS และ disclaimer เชิงโครงสร้าง)

---

## 13. อภิธานศัพท์ (Glossary)

| คำ | ความหมาย |
|---|---|
| Scenario Rehearsal | การซ้อมสถานการณ์ในโลกจำลองก่อนตัดสินใจจริง (ต่างจาก forecasting ที่มุ่งทายผลลัพธ์เดียว) |
| Fragility Index | ตัวชี้วัด 0–100 ว่าข้อสรุปหลักพลิกง่ายแค่ไหนเมื่อสมมติฐานถูกเขย่าเล็กน้อย |
| Hindcast | การรันจำลองย้อนหลังกับเหตุการณ์ที่รู้ผลแล้ว โดยตัดข้อมูลหลังวันเหตุการณ์ออก เพื่อวัดความแม่น |
| Calibration Score | คะแนนสะสมว่าความมั่นใจของระบบสอดคล้องกับความถูกต้องจริงแค่ไหน (วัดด้วย Brier score) |
| Voice share vs Population share | สัดส่วน "เสียงที่ปรากฏ" บนช่องทางสื่อสาร เทียบกับสัดส่วน "คนจริง" ในประชากร ซึ่งมักไม่เท่ากัน |
| Say-do gap | ช่องว่างระหว่างสิ่งที่คนพูด (โดยเฉพาะต่อสาธารณะ) กับสิ่งที่ทำจริง |
| Injectable Event | เหตุการณ์ที่ผู้ใช้แทรกกลาง simulation เพื่อทดสอบ what-if แบบ A/B |
| Hub Node | โหนดในเครือข่ายจำลองที่มีอิทธิพลสูง (ผู้นำความคิดจำลอง) ซึ่ง agent จำนวนมากได้รับอิทธิพลจากโหนดนี้ |
| Tipping Point | จุดเปลี่ยนที่ narrative หรือพฤติกรรมหมู่ในโลกจำลองพลิกทิศทางอย่างมีนัยสำคัญ |
| Emergent Behavior | พฤติกรรมหมู่ที่เกิดจากปฏิสัมพันธ์ของ agent จำนวนมาก ซึ่งคาดเดาไม่ได้จากตรรกะของ agent ตัวเดียว |

---

## 14. ประวัติการแก้ไขเอกสาร (Revision History)

| เวอร์ชัน | วันที่ | รายละเอียดการเปลี่ยนแปลง |
|---|---|---|
| 1.0 | 4 ก.ค. 2026 | ฉบับร่างแรก: โครงสร้าง PRD 13 หัวข้อ, requirements 40 ข้อใน 7 modules |
| 1.1 | 4 ก.ค. 2026 | เพิ่ม Module H (Executive Dashboard, DASH-01..04), SIM-09 Influence Graph & Cluster Analysis, SIM-10 Indirect Impact Tracing, SIM-11 Real-time Context Injection (ปิดอัตโนมัติใน Hindcast), เพิ่มดัชนี Bullish/Bearish Shift ใน SIG-01, หมายเหตุ pipeline 7 ขั้นตอนพร้อม Tipping Points, ปรับ Problem Statement (Echo Chamber / Confirmation Bias), ระบุ RSS ≥ 24 แหล่งในตารางข้อมูล, เพิ่มความเสี่ยงการใช้ influence graph ผิดวัตถุประสงค์, ปรับ Release Plan Phase 1–2 และเพิ่มอภิธานศัพท์ 3 คำ |

---

*เอกสารนี้เป็น draft สำหรับ review — requirement ทั้งหมดควรถูกตรวจทานโดยทีมกฎหมาย (PDPA, กฎหมายเลือกตั้ง), ทีม ethics และ technical lead ก่อน commit เข้า roadmap*
