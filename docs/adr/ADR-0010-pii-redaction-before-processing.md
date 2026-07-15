# ADR-0010 — Redact PII ก่อน cache และประมวลผล

- วันที่: 15 ก.ค. 2569
- สถานะ: **ใช้งาน — ผู้ใช้ยืนยัน 15 ก.ค. 2569**
- ขอบเขต: เนื้อหาจากเว็บ, RSS และ News Desk เท่านั้น

## บริบท

GOV-01 ปัจจุบัน block เอกสารหรือข่าวทั้งชิ้นเมื่อพบ PII และไม่ส่งเนื้อหาให้ LLM แต่การ block
ทั้งหน้าอาจทิ้งข้อมูลสาธารณะที่ยังใช้ประโยชน์ได้ ผู้ใช้เสนอให้ลบหรือปิดบัง PII แล้วนำส่วนที่เหลือ
ไปประมวลผลต่อ

พบช่องว่างใน implementation ปัจจุบันด้วย: fetch cache ถูกเขียนก่อน PII gate ทำให้ raw payload
อาจอยู่ใน cache แม้ snapshot ปลายทางถูก block แล้ว ช่องว่างนี้ต้องปิดไม่ว่าจะรับข้อเสนอ redaction
หรือคงนโยบาย block เดิม

## การตัดสินใจ

1. ใช้ **redact → re-scan → process** สำหรับ body/title ของ external URL, RSS และ News Desk:
   - phone → `[PHONE_REDACTED]`
   - email → `[EMAIL_REDACTED]`
   - เลขบัตรประชาชนที่ checksum ผ่าน → `[THAI_ID_REDACTED]`
   - ชื่อบุคคลที่ไม่อยู่ public-figure allowlist → placeholder เฉพาะเอกสาร เช่น `[PERSON_1]`
2. ห้าม raw PII ผ่าน persistence boundary: ต้อง redact ใน memory ก่อนเขียน fetch cache, chunks,
   news snapshot, payload, audit metadata หรือส่งเข้า LLM
3. หลัง redact ต้องสแกนซ้ำด้วย detector เดิม ถ้ายังพบ PII, redactor ทำงานผิดพลาด หรือ detector
   ถูกปิด ให้ block ทั้งชิ้นตาม fail-closed เดิม
4. provenance เก็บเฉพาะชนิดและจำนวนที่ลบ เช่น `phone: 2`; ห้ามเก็บค่าเดิมหรือ hash ของค่าเดิม
5. สถานะชิ้นข้อมูลเป็น `redacted` และ retrieval ใช้งานได้เหมือน `ready`; UI ต้องแสดงว่ามีการลบ
   PII ก่อนใช้ ห้ามทำให้ผู้ใช้เข้าใจว่าเป็นต้นฉบับครบถ้วน
6. public-figure allowlist เดิมยังใช้ได้ ชื่อที่ allowlist ไม่ถูก redact ในบริบทข่าว
7. URL ที่ตัว URL เองมี PII ให้ block เพราะการแก้ URL เปลี่ยน resource และการเก็บ URL ดิบผิดข้อ 2
8. subject, persona pack, memory, citizen feedback, gallery และข้อมูลที่ผู้ใช้กรอกโดยตรงยัง block
   ตาม GOV-01 เดิมใน ADR นี้ เพื่อลด blast radius; ถ้าจะเปิด redaction ให้เส้นทางเหล่านี้ต้องมีมติแยก
9. เมื่อนำไปใช้จริง ต้อง purge cache เก่าที่มี PII และเพิ่ม migration/validation ป้องกัน raw PII
   อยู่ใน `external_fetch_cache` และ `news_fetch_cache`

## เหตุผล

- รักษาประโยชน์ของข่าวหรือเอกสารที่มี identifier เพียงเล็กน้อยโดยไม่ส่ง identifier เข้าโมเดล
- ยัง fail-closed ที่ทุก failure mode และตรวจผลหลัง redaction ไม่ใช่เชื่อการ replace รอบเดียว
- typed placeholders รักษาโครงประโยคได้ดีกว่าลบข้อความทิ้งทั้งหมด และ document-local person labels
  ช่วยรักษาความสัมพันธ์ภายในเอกสารโดยไม่สร้าง identifier ข้ามเอกสาร
- จำกัดเฉพาะ external evidence ก่อน เพราะเป็นเส้นทางที่ผู้ใช้ถามและมี provenance/snapshot รองรับแล้ว

## ทางเลือก

- **Block ทั้งชิ้นต่อไป:** ปลอดภัยที่สุดแต่สูญเสีย evidence มาก โดยเฉพาะข่าวที่มีเบอร์ติดต่อหรือชื่อ
- **ลบข้อความที่ match แล้วใช้ต่อโดยไม่สแกนซ้ำ:** ปฏิเสธ เพราะ regex overlap/context อาจเหลือ PII
- **เก็บ raw แล้ว redact ตอนส่ง LLM:** ปฏิเสธ เพราะขัด data minimization และ raw PII อยู่ในฐานข้อมูล
- **Pseudonym ข้ามเอกสารด้วย hash:** ปฏิเสธ เพราะ hash ของ identifier ยังเสี่ยง re-identification

## ผลกระทบและ implementation

- `governance/pii.py`: `redact_and_verify()` ใช้ typed placeholders และ document-local person ids;
  รายงานเฉพาะ counts ไม่มี raw values
- `simulation/sources.py`: URL/RSS redact ก่อน external cache/chunks; direct text/label และ PII URL block
- `simulation/newsdesk.py`: provider payload ถูก normalize+redact ก่อน cache/snapshot; `redacted` เข้า media diet ได้
- `news_items`, `run_sources`, `external_fetch_cache` เก็บ `pii_redactions` เป็น JSON counts
- Evidence UI แสดงสถานะ `redacted` และจำนวนที่ลบตามชนิด
- migration `2026-07-15-pii-redaction-before-processing` purge unsafe cache และ migration
  `2026-07-15-scrub-legacy-pii-error-metadata` ลบ raw values จาก legacy error fields
- อัปเดต ADR-0008, `AGENTS.md` และ `CLAUDE.md` ให้ external evidence ใช้ redact-and-verify
  โดย failure ทุกชนิดยัง block
