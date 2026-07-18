# ADR-0020 — ถอดเมนู/หน้า Calibration และ read surface ที่รองรับ

สถานะ: Accepted
วันที่: 18 ก.ค. 2026
มติ: ผู้ใช้สั่งโดยตรง "ลบเมนู Calibration ออก และลบไฟล์ที่เกี่ยวข้องออกและ clean code"

## บริบท

หลัง ADR-0019 ผลิตภัณฑ์โฟกัสที่ workflow PopulationSet → Run → Result → Export; หน้า Calibration
(P5-M3) เป็น read-only dashboard + UI resolve ที่ไม่มีเมนูชี้ถึงแล้ว (เหลือแต่ deep link `#/calibration`)
และข้อมูลจริงในระบบยังเป็น prediction จาก scenario สังเคราะห์ซึ่ง resolve ไม่ได้จนกว่าจะป้อนเหตุการณ์จริง
ผู้ใช้จึงสั่งถอด surface นี้ออกจริงทั้ง page/endpoint ไม่ใช่ซ่อนเมนู

ข้อจำกัดที่ห้ามละเมิด: Prediction/Finding Registry เป็น append-only (กฎเหล็กข้อ 3 / TRUST-01) —
การถอดหน้าอ่าน ห้ามลบตาราง/record และห้ามปิดความสามารถ resolve prediction เมื่อครบกำหนด

## มติ

1. Frontend: ลบ `web/src/pages/Calibration.tsx`, route `/calibration`, API client
   (`fetchCalibration`/`resolvePrediction` + types) และ i18n keys ของหน้า; ข้อความที่เคยชี้
   "เมนู Calibration" เปลี่ยนเป็นชี้ `scripts/resolve_predictions.py`; deep link เดิมเข้า 404
2. Backend: ถอด `GET /calibration.json` และ `GovernanceStore.calibration_detail`
   (รวม weekly trend + reliability 5 bins ที่มีไว้เสิร์ฟหน้านี้เท่านั้น); MCP tool `get_calibration` ถูกถอด
3. **คงไว้ทั้งหมด**: `prediction_registry`/`prediction_resolution` (append-only ทุก trigger),
   `POST /predictions/{id}/resolve` + MCP `resolve_prediction`, `GovernanceStore.resolve_prediction`,
   `due_unresolved` (คิวใน `/runs.json`), `calibration_summary` + `trust/calibration.py`
   (Calibration Engine TRUST-02 สำหรับ public benchmark page) และ CLI `scripts/resolve_predictions.py`
4. เส้นทาง resolve ปัจจุบัน: CLI `scripts/resolve_predictions.py` หรือ REST/MCP resolve — ไม่มี UI

## ผลกระทบ

- supersede ส่วน "Calibration UI (P5-M3)" ของ Phase 5 และการอ้าง "resolve ผ่าน UI" ใน STATE เดิม;
  ADR-0011 (contract prediction/finding, legacy filter) ยังมีผลที่ชั้น store/registry
- สัญญา "legacy partial อ่านได้แต่ไม่เข้า primary calibration" ยังถูกทดสอบผ่าน `calibration_summary`
  (กรอง `source_kind='legacy'`) แทน `calibration_detail` ที่ถูกถอด
- ถ้าอนาคตต้องการ dashboard ความแม่นอีกครั้ง ให้สร้างจาก `calibration_summary`/benchmark page
  โดยเขียน ADR ใหม่ — ห้าม revive โค้ดเดิมเงียบๆ
