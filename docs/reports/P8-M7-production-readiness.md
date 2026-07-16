# P8-M7 Production และ external-validation readiness

วันที่ 16 ก.ค. 2026

## สิ่งที่บังคับด้วยโค้ดแล้ว

- `python -m scripts.production_readiness --profile self-hosted --env-file .env.prod` ตรวจ auth, รูปแบบ
  API key, PII/watermark, master key และรหัส datastore โดยไม่คืนค่า secret
- `--profile public-ga` fail-closed เพิ่มเมื่อยังไม่มี HTTPS, independent pen-test, OIDC และ PostgreSQL RLS
- Settings แสดง actual spend, active reservation และวงเงินที่ยังใช้ได้

## External validation

benchmark fixture ปัจจุบันยังเป็น smoke harness ไม่ใช่ external validity. ชุดข้อมูลที่เหมาะเป็น gate ถัดไปคือ
MIRACL Thai เพราะมี corpus ไทย 542,166 passages, train queries 2,972 และ dev queries 733 พร้อม human
relevance judgments; repository ระบุ Apache-2.0 และ paper อธิบาย annotation/evaluation โดยตรง:

- https://github.com/project-miracl/miracl
- https://aclanthology.org/2023.tacl-1.63/

ไม่ commit corpus ขนาดใหญ่เข้า repo. งาน run จริงต้องดาวน์โหลดเข้า `.tmp/`, pin dataset revision/hash,
สแกน/redact PII ตาม ADR-0010, บันทึก license/source และรายงาน BM25/vector/hybrid แยกกันโดยไม่ตั้ง threshold
ย้อนหลัง. การเปิด vector benchmark ต้องตั้ง embedding model/ราคา/dimension และผ่าน BudgetGuard ก่อนเสมอ.

## Gate ที่ยังต้องมีมติ/หลักฐานภายนอก

- ADR-0012 ถูก Deferred: เมื่อกลับมาต้องเลือก TLS termination, OIDC issuer/claims และว่าจะเปิด PostgreSQL RLS
- penetration test ต้องเป็นผู้ทดสอบอิสระ; self-review หรือ automated scanner ไม่สามารถอ้างแทนได้
- future-event calibration ต้องรอ prediction โลกจริงครบกำหนดและมีหลักฐาน resolution; ห้ามสร้าง outcome จำลอง
  เพื่อเพิ่ม sample size
