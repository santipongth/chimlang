# ADR-0023 — ถอด vector retrieval, reflection, กล่องรับทราบ/เป้าหมายตรวจสอบ และ banner

สถานะ: Accepted
วันที่: 18 ก.ค. 2026
มติ: ผู้ใช้สั่งลบ 6 รายการพร้อมโค้ด/ฐานข้อมูลที่เกี่ยวข้องเพื่อ clean production

## มติ

1. **ข้อความ engine ภายนอก (MiroFish)** — ลบออกจาก wizard/i18n/comment; registry
   `simulation/engines.py` ยังเป็นจุดลงทะเบียน engine ตามเดิม
2. **Vector/RRF retrieval ถอดทั้งเส้นทาง** — `retrieve_evidence` เหลือ Thai BM25 + lexical
   deterministic; ลบ `index_run_embeddings`/`_vector_scores`, embedding adapter
   (`LLMAdapter.embed`/`EmbeddingResult`), ค่า `llm_model_embedding`/`llm_embedding_dimension`
   ใน config/appsettings/userconfig/Settings UI, ตัวเลือก Retrieval + ข้อความ RRF ใน wizard
   และ `retrieval_mode` ใน RunBody/manifest; migration
   `2026-07-18-remove-vector-retrieval-v1` ลบตาราง `run_chunk_embeddings` (ตรวจแล้ว 0 แถว —
   embedding ไม่เคยถูกตั้งค่า ระบบใช้ BM25 ตลอด)
3. **Run-local reflection ถอดทั้งฟีเจอร์** (คือกลไก opt-in ให้ analyst สรุปไตร่ตรองระหว่างรอบ
   ≤2 ครั้ง ป้อนกลับเข้า prompt — เพิ่ม cost/ความซับซ้อนโดยไม่เคย validate ประโยชน์จริง):
   ลบ `simulation/reflection.py`, wiring ใน debate/API/estimate/benchmark, toggle 🪞 ใน wizard
4. **กล่องรับทราบ synthetic population ถูกถอดจาก UI ทั้ง wizard และ Experiments** —
   run สร้างได้ทันที (auto-freeze PopulationSetV1 พร้อม manifest hash ตามเดิม);
   การสร้าง PopulationSet ตรงผ่าน API ยังต้องระบุ `acknowledged_synthetic` ตาม contract เดิม
5. **กล่อง "เป้าหมายการตรวจสอบ" (claim/measurement/due days) ถูกถอดจาก wizard** —
   prediction/finding อัตโนมัติยังถูกสร้างทุก run ตามกฎเหล็กข้อ 3; ป้อน claim เองยังทำได้ผ่าน API
6. **Banner "AI simulation — not a real poll" ในหน้า Gallery + field `disclaimer` ใน
   /gallery.json ถูกลบ** — **watermark ของ export (PDF/HTML per GOV-03 กฎเหล็กข้อ 4) และ
   labels `simulation_estimate/not_field_poll/aggregate_only` ใน watermark metadata คงเดิม
   ไม่แตะ** เพราะเป็นข้อบังคับ governance ไม่ใช่ UI text

## ผลกระทบ

- supersede ส่วน retrieval/reflection ของ P8-M5 (ADR ที่เกี่ยวข้อง) และ acknowledgement gate
  ของ ADR-0018 (เฉพาะชั้น UI/RunBody — PopulationSetV1 immutability คงเดิม)
- run เก่าที่มี `retrieval_mode`/`reflection` ใน config อ่านได้ตามเดิม (read path ไม่ strict)
- benchmark harness P8 ตัด reflection_smoke ออก; รายงานเดิมเป็นหลักฐานประวัติ
