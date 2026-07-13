# ADR-0009: ขอบเขตจำนวนกลุ่ม persona (2-12) + ที่มาของ cultural priors + calibrate channel_mix

- สถานะ: Accepted (13 ก.ค. 2026 — ผู้ใช้ถามที่มาของ cap 2-8 และ traits แล้วอนุมัติทั้ง 3 ข้อหลัง research)
- บริบท: cap 2-8 segments เดิม (P5-M7) เป็น design choice ที่ไม่มีเอกสารอธิบาย (ไม่มี comment/ADR
  และเลข 8 hardcode ซ้ำใน React modal แยกจาก Python), cultural priors มีแต่ requirement (FAB-02)
  ไม่มี citation, channel_mix ใน segments.yaml ยังไม่ calibrate กับข้อมูลจริง (FAB-05 ค้าง),
  และพบ `sensitivity_awareness` เป็น prior ตัวที่ 4 ใน YAML ที่ไม่มีอะไรในระบบอ่าน

## 1. ทำไมต้องเป็น "กลุ่ม" (segment-based) ไม่ใช่ persona รายบุคคล

- แนวทาง "silicon sampling": โปรไฟล์ระดับกลุ่มประชากร → ปั๊ม agent รายตัว + jitter priors ±0.1
  (persona.py) — มาตรฐานของงาน LLM survey simulation
- ทางเลือก persona รายบุคคลจริง (Stanford generative agents, แม่น ~85% ต่อบุคคล) ต้องใช้บทสัมภาษณ์
  ~2 ชม./คนจริง — เราไม่มี corpus แบบนั้น และขัด GOV-01 (ห้าม ingest ข้อมูลรายบุคคล) โดยตรง
- โครงสร้างกลุ่มสอดคล้อง governance ของเราโดย construction: GOV-02 aggregate-only,
  SIM-09 จำกัดผลระดับ segment

## 2. ขอบเขต 2-12 กลุ่ม (เดิม 2-8)

| ขอบ | ค่า | เหตุผล |
|---|---|---|
| ล่าง | 2 | 1 กลุ่ม = ไม่มีโครงสร้างประชากรให้จำลอง (ไม่เปลี่ยน) |
| บน | 12 | floor เชิงสถิติ: ผลรายกลุ่มต้องมี n≥30 (rule of thumb CLT) — ที่ cap 1,000 agents/run, 12 กลุ่มเท่าๆ กัน ≈ 83 ตัว/กลุ่ม ยังปลอดภัย; เกินนั้นกลุ่มเล็ก (share ~0.05) เสี่ยงต่ำกว่า 30 |

- practice การทำ segmentation ตลาด: 3-7 กลุ่มคือช่วงที่ actionable (Decision Analyst
  "How Many Segments Are Optimal?", Sawtooth Software segmentation best practices) —
  12 คือเพดานเผื่องานวิจัยเชิงลึก ไม่ใช่ค่าแนะนำ
- **Single source of truth**: `MIN/MAX_SEGMENTS` อยู่ `simulation/persona_packs.py` ที่เดียว,
  ส่งให้ UI ผ่าน `GET /personas/pool.json` field `limits` (UI มี fallback const แต่ค่าตาม backend)
- **Guard สถิติใน UI**: กลุ่มที่ `share × agents < 30` แสดงคำเตือน "ผลรายกลุ่มไม่น่าเชื่อถือ"
  ทั้งใน pack editor และ pool panel ของ wizard (เตือน ไม่ block — ผู้ใช้รันเล็กเพื่อทดลองได้)

## 3. ที่มาของ cultural priors (FAB-02) — concept มีฐานวิชาการ, ตัวเลขยังสังเคราะห์

| prior | ฐานวิชาการ | ผลใน engine |
|---|---|---|
| `kreng_jai` เกรงใจ | concept ไทยที่ศึกษาจริงจัง: Klausner (นักมานุษยวิทยา — "ยากที่สุดที่ต่างชาติจะเข้าใจ"), discourse analysis พบ 26 ความหมาย, งานศึกษาองค์กรไทย (Thai subsidiary practice adoption) | กดการแสดงออกสาธารณะ (×(1−0.5·kj)) + ลดการเชื่อข่าวแก้ในกลุ่มปิดเพราะเกรงใจผู้ส่งเดิม (engine.py:197, 210-215) |
| `say_do_gap` พูด-ทำ | social desirability bias ซึ่งวิจัยยืนยันว่าแรงกว่าใน collectivist cultures (Frontiers in Psychology 2022; PSM cross-national study) — เหตุผลเชิงโครงสร้างที่โพลพลาด | เพิ่มการส่งต่อในกลุ่มปิด (+0.4·sdg) — พูดในที่ลับต่างจากที่แจ้ง |
| `sarcasm_meme` มีม/ประชด | การแสดงออกทางการเมืองไทยออนไลน์ใช้มีม/ประชดจริงภายใต้ข้อจำกัดการพูดตรง (Rest of World 2020; งานวิจัย Thai youth TikTok activism under censorship 2025) | prompt-only — กำหนดน้ำเสียง agent ใน voice layer ไม่อยู่ในสมการแพร่ |
| `voice_activity` | TRUST-07 Silent Majority (แยกผู้แสดงออก/ผู้สังเกตการณ์) | gate หลักว่า agent โพสต์หรือเงียบ (share_prob พื้นฐาน) |

- **ตัวเลข default ต่อกลุ่มและสัมประสิทธิ์ใน engine (0.5, 0.4) ยัง hand-tuned** — สิ่งที่พิสูจน์แล้ว
  คือ*ทิศทาง* (FAB-01 sign test: กลุ่มปิดแพร่ช้ากว่า/correction เข้ายาก ตรงวรรณกรรม) ไม่ใช่*ขนาด*
  — ห้ามอ้างว่าค่าเหล่านี้วัดจากประชากรจริงจนกว่าจะมี hybrid panel (TRUST-08)

## 4. ลบ `sensitivity_awareness` ออกจาก segments.yaml

dead key: persona.py อ่านเฉพาะ 3 priors, ไม่อยู่ใน `PRIOR_KEYS`, UI ไม่แสดง, แต่รั่วเข้า pack
ผ่านการทำสำเนาสำมะโน (pool.json ส่ง cultural_priors ทั้งก้อน) = ข้อมูลที่ผู้ใช้มองไม่เห็นและแก้ไม่ได้
ขัดหลัก TRUST-06 → ลบทิ้ง; จะเพิ่มกลับต้องมี engine mechanism จริง + ADR ใหม่

## 5. calibrate channel_mix (FAB-05 บางส่วน)

Mapping สถิติแพลตฟอร์ม → 4 ช่องทางนามธรรม (บันทึกตรงๆ ว่าเป็น judgment mapping ไม่ใช่สำรวจ media diet ตรง):

| ช่องทาง | แพลตฟอร์มที่นับ | สถิติยึด |
|---|---|---|
| line_closed_group | กลุ่ม LINE + กลุ่ม Facebook ปิด/หมู่บ้าน (พลวัตกลุ่มปิดเหมือนกัน) | LINE 78.2% ของประชากร (DataReportal Digital 2025 Thailand) |
| public_feed | Facebook feed สาธารณะ, X | FB ยัง reach อันดับต้นทุกวัย (DataReportal 2025) |
| algo_feed | TikTok, Shorts, Reels | TikTok 44.4M = 57.8%; Gen Z 76% vs Boomers ~49%, IG Gen Z 87% (YouGov Thailand) |
| offline_wom | ปากต่อปาก | residual ตามระดับ digital inclusion ของกลุ่ม |

ค่าใหม่ทั้ง 7 กลุ่มอยู่ใน `data/samples/population/segments.yaml` (v0.2-draft) — จุดเปลี่ยนหลัก:
young_urban algo 0.45→0.53, elderly algo 0.10→0.14 (Boomers ใช้ TikTok ~49% มากกว่าที่ร่างเดิมให้),
gig algo 0.30→0.37 (mobile-first) | share และ cultural_priors **ไม่แตะ** (ยังรอสำมะโน สสช. จริง)

## ผลกระทบ

- pack เก่าที่บันทึกไว้ (≤8 กลุ่ม) valid เหมือนเดิม — ไม่มี migration
- `GET /personas/pool.json` เพิ่ม field `limits` (backward-compatible)
- trail ของ run ก่อน/หลัง ADR นี้เทียบกันราย seed ไม่ได้ (channel_mix เปลี่ยน RNG path) —
  determinism ต่อ config เดิมยังครบ (NFR-07 freeze ที่ snapshot)
- ทบทวนตัวเลขอีกครั้งเมื่อได้สำมะโน สสช. / สำรวจ media diet จริงจากผู้ใช้ (งานค้างใน STATE.md)
