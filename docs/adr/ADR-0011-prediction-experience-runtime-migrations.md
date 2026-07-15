# ADR-0011: Prediction Experience contract และ schema lifecycle แบบ migration-only

- สถานะ: Accepted (15 ก.ค. 2026 — ผู้ใช้ส่งแผนยกระดับและสั่งให้ implement)

## บริบท

ระบบเดิมเรียก `setup()` ที่มี DDL จาก request/worker และสร้าง prediction heuristic ให้ทุก run
แม้สิ่งที่วัดเป็นเพียงความคงทิศเมื่อจำลองซ้ำ ไม่ใช่เหตุการณ์โลกจริง ทั้งสองอย่างลด trust:
DDL ทำให้เกิด AccessExclusiveLock/deadlock ส่วน heuristic ทำให้ Calibration ปน simulation finding

## การตัดสินใจ

1. DDL รันได้จาก `scripts/db_migrations.py` เท่านั้น ภายใต้ PostgreSQL advisory lock เดียว
   API/worker ตรวจ migration ledger แบบ read-only ตอน startup และใช้ connection pool แยกต่อ process
2. ทุก run ต้องมีอย่างน้อยหนึ่ง `SimulationFinding` **หรือ** `Prediction` แทนข้อบังคับเดิมที่
   ทุก run ต้องสร้าง prediction
3. `Prediction` ใหม่รองรับ `forecast_type=binary`, ต้องมี claim, probability, measurement,
   due date และ provenance โลกจริง; prediction เก่าอ่านเป็น `source_kind=legacy` โดยไม่แก้แถวเดิม
4. Calibration หลักไม่นับ legacy/test-generated records; เปิดดู legacy ได้ด้วย filter แยก
5. Resolution ใหม่เป็น binary เท่านั้น และต้องมี `observed_at`, evidence URL/name, note;
   partial เดิมยังอ่านได้แต่สร้างเพิ่มไม่ได้
6. analyst/mechanical synthesis เป็น revision append-only; mechanical recomputation ห้าม overwrite
   analyst synthesis เดิม
7. Structured output ใช้ JSON Schema strict เมื่อ provider/model capability รองรับ; fallback parser
   ต้องติด `parser_mode` ชัดเจน

## ผลกระทบ

- เปลี่ยน governance rule TRUST-01 ใน `CLAUDE.md`; registry, finding, resolution และ
  synthesis revision ยัง append-only ที่ DB trigger
- Operational `sim_runs` ลบได้ แต่ synthesis revisions คงอยู่เพื่อ audit
- API เก่า `/runs/{id}/resynthesize` ยังเป็น deprecated alias ของ mechanical recomputation ชั่วคราว
- งาน visualization/vector retrieval/typed debate moves อยู่ใน Phase 8 milestones ถัดไป ไม่ถูกอ้างว่าเสร็จ

## แหล่งอ้างอิง implementation

- OpenRouter Structured Outputs: `response_format.type=json_schema`, `strict=true` และ
  `provider.require_parameters=true` สำหรับ route ไป provider ที่รองรับ
  <https://openrouter.ai/docs/guides/features/structured-outputs>
