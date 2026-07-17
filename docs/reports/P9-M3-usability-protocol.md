# P9-M3 — Thai pilot usability protocol (ยังไม่รัน)

สถานะ 17 ก.ค. 2026: **protocol ready; claim blocked** — ไม่มีการสร้างผู้เข้าร่วมหรือผลลัพธ์จำลอง

## ผู้เข้าร่วมและ consent

- ผู้ใช้เป้าหมายภาษาไทยอย่างน้อย 5 คนที่มีงานวิเคราะห์นโยบาย/กลยุทธ์/วิจัย
- ขอ consent ก่อนบันทึกเวลา/ข้อผิดพลาด/คำพูด; ไม่เก็บชื่อ เบอร์ อีเมล หรือ scenario งานจริงใน repo
- ใช้รหัส `P01..P05`; note ดิบอยู่ในพื้นที่จำกัดสิทธิ์และ import เฉพาะ aggregate ที่ผ่าน PII gate

## งานทดสอบ

1. สร้าง Project จาก brief ที่กำหนด
2. เพิ่ม TXT/PDF และ URL fixture ที่ไม่มี PII แล้ว freeze `EvidenceSetV1`
3. ตั้ง population/assumptions และเริ่ม run จาก frozen evidence
4. cancel run ที่กำลังทำงาน แล้วเปิด stored snapshot ของ run ที่สำเร็จ
5. เปิด Validation Lab เปรียบเทียบ sensitivity และตรวจ raw failure
6. assign owner ให้ forecast ที่ครบกำหนดและอธิบายหลักฐานที่ต้องใช้ก่อน resolve
7. export JSON/PDF snapshot
8. สร้าง Rehearsal, ถาม/ตอบหนึ่ง turn, pause/resume, เพิ่ม decision และ finish scorecard

## ตัวชี้วัดและ gate

- task completion หลัก = ทำข้อ 1, 2, 3, 4, 5 และ 7 สำเร็จโดยไม่ให้ผู้ดำเนินการทำแทน
- เป้าหมาย aggregate completion ≥80%; รายงานทั้งจำนวนสำเร็จ/ทั้งหมด ไม่ตัด participant ที่ล้มเหลวออก
- เก็บ time-on-task, critical error, recovery, keyboard-only completion และ TH/EN label mismatch
- WCAG spot checks: focus visible/restore, status `aria-live`, keyboard drawer/tabs, 390px reflow และ target size
- ห้ามอ้าง usability/pilot success จนมีผู้เข้าร่วม ≥5, raw anonymized sheet hash และรายงานผลจริง

## Template ผลจริง

| participant | tasks completed/required | critical errors | keyboard/reflow | note category |
|---|---:|---:|---|---|
| P01 | pending | pending | pending | pending |

เมื่อรันจริงให้เพิ่ม dataset/report ใน Validation Lab ด้วย `kind=usability`, ระบุวันที่/ผู้ดำเนินการ,
hash ของ raw anonymized sheet และ deviations จาก protocol; ห้ามกรอกค่าคาดเดาลงตารางนี้
