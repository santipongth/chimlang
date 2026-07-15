# ADR-0010 — Redact PII ก่อน cache และประมวลผล

- วันที่: 15 ก.ค. 2569
- สถานะ: **เสนอ — รอมติผู้ใช้ก่อน implement**
- ขอบเขต: เนื้อหาจากเว็บ, RSS และ News Desk เท่านั้น

## บริบท

GOV-01 ปัจจุบัน block เอกสารหรือข่าวทั้งชิ้นเมื่อพบ PII และไม่ส่งเนื้อหาให้ LLM แต่การ block
ทั้งหน้าอาจทิ้งข้อมูลสาธารณะที่ยังใช้ประโยชน์ได้ ผู้ใช้เสนอให้ลบหรือปิดบัง PII แล้วนำส่วนที่เหลือ
ไปประมวลผลต่อ

พบช่องว่างใน implementation ปัจจุบันด้วย: fetch cache ถูกเขียนก่อน PII gate ทำให้ raw payload
อาจอยู่ใน cache แม้ snapshot ปลายทางถูก block แล้ว ช่องว่างนี้ต้องปิดไม่ว่าจะรับข้อเสนอ redaction
หรือคงนโยบาย block เดิม

## การตัดสินใจที่เสนอ

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

## ผลกระทบเมื่ออนุมัติ

- ต้องแก้ `governance/pii.py` ให้มี redactor แบบ deterministic และรายงาน counts โดยไม่คืน raw values
- ต้องย้าย PII boundary ให้อยู่ก่อน cache ใน `simulation/sources.py` และ `simulation/newsdesk.py`
- ต้องแก้ status/schema/UI evidence ให้รองรับ `redacted` และเพิ่ม tests ว่า raw PII ไม่อยู่ใน DB/prompt
- ADR-0008 ข้อ 4 และข้อความ GOV-01 ใน `CLAUDE.md` ต้องอัปเดตจาก “พบแล้ว block เสมอ” เป็น
  “redact-and-verify สำหรับ external evidence; failure ทุกชนิด block” หลังผู้ใช้อนุมัติเท่านั้น
