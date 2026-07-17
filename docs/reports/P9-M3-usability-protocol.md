# P9-M3 — Thai pilot usability protocol + in-app mockup

สถานะ 17 ก.ค. 2026: **mockup ready; claim blocked** — route #/usability พร้อม แต่ยังไม่มีผู้เข้าร่วมจริง

## ผู้เข้าร่วมและ consent

- ผู้ใช้เป้าหมายภาษาไทยอย่างน้อย 5 คนที่มีงานวิเคราะห์นโยบาย/กลยุทธ์/วิจัย
- ขอ consent ก่อนบันทึกเวลา/ข้อผิดพลาด/คำพูด; ไม่เก็บชื่อ เบอร์ อีเมล หรือ scenario งานจริงใน repo
- ใช้รหัส `P01..P05`; note ดิบอยู่ในพื้นที่จำกัดสิทธิ์และ import เฉพาะ aggregate ที่ผ่าน PII gate

## งานทดสอบ

1. สร้าง Project จาก brief ที่กำหนด
2. เพิ่มหลักฐาน ตรวจ PII แล้ว freeze EvidenceSetV1
3. เริ่ม run แล้วหา cancel control ขณะกำลังทำงาน
4. เปิด Validation Lab และแยก measured claim ออกจาก blocked claim
5. เปิด stored result แล้ว export JSON/PDF snapshot โดยไม่ rerun

Rehearsal และ Resolution Inbox เป็นงานเสริมสำหรับ session เชิงลึก ไม่รวม denominator หลัก 25 งาน

## ตัวชี้วัดและ gate

- task completion หลัก = ผู้เข้าร่วมแต่ละคนทำห้าข้อด้านบนโดยไม่ให้ผู้ดำเนินการทำแทน
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

## วิธีใช้ mockup

1. เปิด #/usability และเลือก P01–P05
2. ขอ consent ก่อนติ๊ก checkbox; ปุ่มจับเวลาจะ disabled จนยืนยัน
3. เปิด moderator mode เพื่อดูเกณฑ์สำเร็จและบันทึกเฉพาะ count/score/category
4. ให้ผู้เข้าร่วมทำงานในแท็บใหม่ กด complete หรือ blocked ตามสิ่งที่เกิดจริง
5. export anonymized JSON เมื่อจบ session; claim_ready ต้องยัง false จน consent ครบและ 25/25 งานถูกบันทึก
