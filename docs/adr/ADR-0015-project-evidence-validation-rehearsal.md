# ADR-0015: Frozen case workflow, measurable validation และ event-sourced rehearsal

- สถานะ: Superseded โดย ADR-0019 (18 ก.ค. 2026)

## บริบท

หลัง P9-M1 ปิด trusted-run foundation แล้ว pilot ยังขาดหน่วยงานหลักสามส่วน: case workspace ที่ผูก
brief/evidence/run/decision เข้าด้วยกัน, validation registry ที่แยกผลวัดจริงออกจาก claim และ UI ของ
Press-room Rehearsal เดิม การเก็บ source กระจัดกระจายใน request, การแก้ข้อมูลเดิมทับ และการ preflight
งบโดยไม่ reserve จะทำให้ audit/replay และ monthly cap ไม่น่าเชื่อถือ

## การตัดสินใจ

1. Project เป็น case workspace ที่เดินหน้าเป็นลำดับ `Brief → Evidence → Population → Assumptions →
   Run → Compare → Decision → Resolution`; ทุกการแก้สร้าง `project_revisions` ใหม่และห้ามข้าม stage
   มากกว่าหนึ่งขั้น
2. Evidence แยก item กับ append-only version รองรับ PDF/DOCX/TXT/CSV, URL และ RSS:
   - direct content ที่ detector พบ PII ถูก block ก่อน persistence
   - URL/RSS ผ่าน `SafeOutboundFetcher` แล้ว redact-and-verify ก่อน persistence
   - duplicate อ้าง `duplicate_of`; health/status/hash/PII counts เป็น provenance ที่ไม่เก็บค่าดิบ
3. `EvidenceSetV1` เป็น append-only manifest ของ version ที่เลือกพร้อม canonical SHA-256; run รับ
   `evidence_set_id`, ตรวจ hash แล้ว materialize content เข้า `RunSpecV1` ก่อน enqueue เพื่อให้การแก้
   evidence ภายหลังไม่เปลี่ยน input ของ run เดิม
4. Validation datasets/reports และ prediction-owner events เป็น append-only; human-panel import ต้องมี
   consent basis และ outcome จากผู้นำเข้า ห้ามระบบสร้าง outcome แทนมนุษย์
5. MIRACL claim เป็น `measured` ได้เฉพาะ pinned revision, corpus 542,166 passages, dev 733 queries,
   raw-result hash และ `benchmark_complete=true`; ผลผิด/ไม่ครบใช้ append-only invalidation event
   ไม่แก้หรือลบประวัติ
6. Rehearsal session ใช้ event log สำหรับ question/answer/decision/pause/resume/scorecard และ CAS
   สำหรับสถานะ ขณะสร้างต้อง reserve ค่าใช้จ่ายรวมแบบ transactional, adapter bind session ID เพื่อ
   ลง monthly ledger ทุก call และคืน reservation ที่เหลือหลัง finish; next/answer/finish ใช้ tokenized
   PostgreSQL operation lease ที่หมดอายุได้เพื่อกัน provider call ซ้ำข้าม process
7. Project, Validation Lab และ Rehearsal เป็น lazy HashRouter routes; Run Detail ใช้ status shell กับ
   Result/Evidence/Uncertainty/Validation/Audit โดย route เดิมยัง compatible

## ผลกระทบ

- เพิ่มตาราง project/evidence/validation/rehearsal และ migration ledger สามรายการ โดยข้อมูล trust
  สำคัญเป็น append-only
- EvidenceSet ใช้ได้กับ Debate เท่านั้นในรุ่นนี้; Fabric ไม่รับ text evidence จึง fail closed
- model robustness ยังเป็น opt-in หลัง aggregate cost preflight; ไม่มี default multi-model sweep
- human-panel accuracy และ usability ≥5 คนยังอ้างไม่ได้จนมี consented/raw result จริง
- ไม่เพิ่ม Concordia หรือ simulation engine ใหม่ และ cap 1,000 agents, `$5/run`, `$50/month` คงเดิม
