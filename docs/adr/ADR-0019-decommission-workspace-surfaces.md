# ADR-0019 — ถอด Project/Evidence, Validation Lab, Rehearsal และ Usability surfaces

สถานะ: Accepted
วันที่: 18 ก.ค. 2026
มติ: ผู้ใช้สั่งโดยตรงให้ลบเมนู โค้ด ไฟล์ และข้อมูลฐานข้อมูลที่เกี่ยวข้อง

## บริบท

หลัง Phase 9 ระบบมี workspace เฉพาะทางสี่ส่วนที่เพิ่มภาระ navigation, API, migration และการดูแล
โดยผู้ใช้ตัดสินใจให้ผลิตภัณฑ์กลับมาโฟกัสที่ workflow หลัก PopulationSet → Run → Result → Export
จึงต้องถอดของเดิมจริง ไม่ใช่ซ่อนเฉพาะเมนู เพราะ endpoint และตารางที่ไม่มีผู้ใช้ยังเพิ่ม attack surface
และทำให้ production smoke ซับซ้อนโดยไม่จำเป็น

## มติ

1. ถอด React routes/menu/page และ API client ของ Projects & Evidence, Validation Lab,
   Press-room Rehearsal และ Usability study; deep link เดิมต้องเข้า 404
2. ถอด FastAPI routers, stores, rehearsal engine/CLI, validation runners และ tests ที่รองรับ surface เหล่านี้
3. `RunBody` ไม่รับ `project_id` หรือ `evidence_set_id`; Debate ยังรับ governed direct sources ตาม
   PII/SSRF contract เดิม และ production smoke ใช้ direct source + immutable PopulationSetV1
4. migration ใหม่ลบ project/evidence, validation และ rehearsal operational tables รวม 14 ตาราง
   และถอด project linkage จาก PopulationSet ใหม่
5. คง `run_manifests`, snapshots ใน run เดิม, `prediction_registry`, `simulation_findings`, audit log,
   synthesis revisions และ provider/budget ledger ไว้ เพราะเป็น immutable governance/financial evidence
   ไม่ใช่ operational workspace ที่ผู้ใช้สั่งล้าง
6. historical migration versions ยังอยู่ใน ledger แต่เป็น no-op บนฐานข้อมูลใหม่ เพื่อให้ fresh install
   เดิน migration ได้โดยไม่ต้องเก็บโมดูลที่ decommission แล้ว

## ผลกระทบ

- ADR-0015 ถูก supersede ทั้งส่วน Project/Evidence/Validation/Rehearsal; ADR-0016 ถูก supersede เฉพาะ
  validation/usability surfaces และ runners ส่วน TH/EN + WCAG gate ยังมีผล
- รายงานเก่าใน `docs/reports/` คงไว้เป็นหลักฐานประวัติและไม่ใช่ฟีเจอร์ที่รันได้
- Calibration, per-run validation, evidence lineage ของ run, governed direct sources, PopulationSetV1,
  experiments และ trust/audit records ยังทำงานต่อ เพราะไม่ใช่สี่ workspace ที่สั่งถอด
- การกู้ข้อมูล operational tables ที่ migration ลบต้องอาศัย backup ภายนอก; migration ไม่สร้างตารางกลับ
