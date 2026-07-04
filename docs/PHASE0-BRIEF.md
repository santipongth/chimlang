# PHASE 0 BRIEF — ชิมลาง (CHIMLANG)

ขอบเขตงานเฟสแรก (เดือน 0–3) อ้างอิง PRD v1.1 หัวข้อ 11 — ไฟล์นี้คือ backlog ที่ Claude Code ต้องอัปเดต checklist ตามความคืบหน้า

## เป้าหมายและ Exit Criteria

Requirements ใน scope: SIM-01..04, SIM-07, FAB-01/02/05, GOV-01/03/04 + รายงานพื้นฐาน
Exit criteria: (1) hindcast ภายในผ่าน ≥ 3 ใน 5 เหตุการณ์ (2) ต้นทุน Standard run ≤ $80 (3) กฎ governance ทั้ง 3 ข้อทำงานจริงพร้อม test

**ลำดับความสำคัญพิเศษ: ทำ M1 (PoC Hindcast Data Cutoff) ก่อน M2–M5** — ถ้า M1 พิสูจน์ไม่ได้ สถาปัตยกรรม Trust Layer ต้องออกแบบใหม่ อย่าเพิ่งลงแรงกับส่วนอื่น

## Milestones

### M0 — Scaffold (สัปดาห์ 1)
- [ ] โครง repo ตาม CLAUDE.md + docker-compose (postgres, neo4j, redis)
- [ ] LLM adapter layer (OpenAI-compatible, tiered models จาก D5) + cost estimator + budget cap
- [ ] CI: lint + test + `make` targets ครบตามที่ประกาศใน CLAUDE.md

### M1 — PoC: Hindcast Data Cutoff (สัปดาห์ 2–4) ⚠️ Gate ของทั้งโครงการ
- [ ] เลือกเหตุการณ์อดีต 1 เหตุการณ์จาก data/samples/hindcast/ (มีข้อมูลก่อนเหตุการณ์ + ผลจริง)
- [ ] Retrieval filter: block เอกสาร/ข้อมูลที่ timestamp หลังวัน cutoff ทุก layer
- [ ] Prompt-level filter: system prompt กำกับ agent ไม่ให้ใช้ความรู้หลัง cutoff จาก training data
- [ ] **Adversarial leak test**: ชุดคำถามล่อ ≥ 30 ข้อที่พยายามให้ agent เผยความรู้หลัง cutoff แล้ววัด leak rate — เกณฑ์ผ่าน: ≤ 2% (ตาม AC ของ TRUST-03)
- [ ] รายงานผล PoC: ผ่าน/ไม่ผ่าน + ข้อเสนอ (เช่น ต้องใช้ model cutoff เก่า หรือ fine-tune) — **หยุดรอการตัดสินใจจากผู้ใช้ก่อนไป M2**

### M2 — Ingestion & Knowledge Graph (SIM-01)
- [ ] Ingest ข่าว/เอกสารจาก data/samples/corpus/ → entity & relationship extraction → Neo4j
- [ ] PII detector ใน pipeline นำเข้า พร้อม block + แจ้งเตือน (GOV-01) + test cases ภาษาไทย (ชื่อคน เบอร์ เลขบัตร)
- [ ] Query API: ถามความสัมพันธ์ทางอ้อมระหว่าง entity ได้

### M3 — Agent Runtime + Thai Social Fabric v1 (SIM-02/03, FAB-01/02/05)
- [ ] Persona factory: สร้าง agent 100–1,000 ตัวจาก segment config (น้ำหนักอ้างอิง data/samples/population/)
- [ ] ช่องทาง 4 แบบ: closed group (LINE-like), public feed, algorithmic feed, offline word-of-mouth — แต่ละแบบมีพารามิเตอร์การแพร่ต่างกัน
- [ ] Cultural priors เป็นพารามิเตอร์ของ agent: เกรงใจ / say-do gap / การประชด
- [ ] Benchmark ตาม AC ของ FAB-01: rumor แพร่ใน closed group ช้ากว่า public feed และ correction เข้า closed group ช้ากว่า

### M4 — Injectable Events + รายงานพื้นฐาน (SIM-04)
- [ ] Inject event กลาง run → fork 2 branches seed เดียวกัน → รายงาน delta พร้อมช่วงความเชื่อมั่น (AC ของ SIM-04)
- [ ] รายงาน markdown/HTML: สรุปรายกลุ่ม + ตัวอย่าง reasoning trail + voice share vs population share

### M5 — Governance Hooks (GOV-03/04)
- [ ] Watermark module สำหรับทุก export (visible + machine-readable: run id, วันที่, ป้าย "AI simulation — not a real poll")
- [ ] Audit log แบบ append-only: ผู้สั่ง run, config hash, ผู้ export
- [ ] Prediction Registry ขั้นต่ำ: ทุก run เขียน prediction record (claim, ทิศทาง, confidence, วิธีวัด, วันครบกำหนด) — DB trigger กัน UPDATE/DELETE

## ข้อมูลที่ผู้ใช้ต้องเตรียมใน data/samples/ (ก่อนเริ่ม M1–M3)

- `corpus/` — ข่าว/บทความ/เอกสารนโยบายภาษาไทย 10–20 ไฟล์ (.txt หรือ .md ระบุวันที่ในชื่อไฟล์ เช่น `2026-05-12-หัวข้อ.md`)
- `hindcast/` — เหตุการณ์อดีต 1–2 ชุด แต่ละชุดมีโฟลเดอร์ `before/` (ข้อมูลก่อนวัน cutoff), ไฟล์ `outcome.md` (ผลจริง) และ `meta.yaml` (วัน cutoff, วิธีวัดผล)
- `population/` — สัดส่วน segment อย่างง่าย 1 ไฟล์ (yaml/csv): ชื่อกลุ่ม, สัดส่วน, ช่องทางสื่อหลัก, ลักษณะเด่น

---

# Prompt ชุดแรกสำหรับ Claude Code (copy-paste ได้เลย)

## Prompt 1 — วางแผนทั้งเฟส (รันใน Plan Mode: กด Shift+Tab ก่อน)

```
อ่าน @docs/PRD-SANAM.md @docs/TECH-DECISIONS.md และ @docs/PHASE0-BRIEF.md อย่างละเอียด

จากนั้น:
1. สร้าง implementation plan ของ Phase 0 ตาม milestones M0–M5 แตกเป็น action items ที่มี [ ] checkbox โดยแต่ละ milestone ต้องมี action item สำหรับ unit tests ด้วย
2. ระบุจุดที่ TECH-DECISIONS ยังไม่ถูกติ๊กหรือขัดแย้งกับ PRD แล้วถามฉันก่อน
3. ระบุความเสี่ยงทางเทคนิค 5 อันดับแรกของแผน พร้อมวิธีลดความเสี่ยง
4. ยังไม่ต้องเขียนโค้ด — แสดงแผนให้ฉัน approve ก่อน
```

## Prompt 2 — เริ่ม M0 (หลัง approve แผน)

```
เริ่ม M0 ตามแผนที่ approve แล้ว: scaffold โครง repo ตาม CLAUDE.md, ตั้ง docker-compose,
สร้าง LLM adapter layer พร้อม cost estimator และ budget cap จาก env
เขียน test ให้ adapter และ cost guard แล้วรัน make test ให้ผ่านก่อนสรุปงาน
```

## Prompt 3 — PoC Hindcast (งานชี้ชะตา)

```
เริ่ม M1 PoC Hindcast Data Cutoff ตาม @docs/PHASE0-BRIEF.md
ใช้เหตุการณ์ใน data/samples/hindcast/ ชุดแรก
เป้าหมาย: พิสูจน์ว่า retrieval filter + prompt filter กันความรู้หลัง cutoff ได้ leak rate ≤ 2%
สร้าง adversarial leak test อย่างน้อย 30 ข้อ (ภาษาไทย) แล้วรายงานผลเป็นตาราง
ห้ามเปิด external retrieval ใดๆ ระหว่างโหมดนี้ (กฎเหล็กข้อ 2 ใน CLAUDE.md)
ถ้าผลไม่ผ่านเกณฑ์ ให้วิเคราะห์สาเหตุและเสนอทางเลือก อย่าเพิ่งแก้เกณฑ์หรือไปต่อ M2
```
