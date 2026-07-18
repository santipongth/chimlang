# ADR-0022 — Core Engine v2: CRN, re-exposure, selective feed, voice layer, devil's advocate

สถานะ: Accepted
วันที่: 18 ก.ค. 2026
มติ: ผู้ใช้สั่งตรวจสอบ+calibrate Fabric/Debate/Red Team และยกระดับตามงานวิจัย; อนุมัติแผน
(เงื่อนไข: ไม่รัน LLM จริง, ทำรวดเดียว, ยกระดับ Red Team เต็มรูป)

## บริบท

Audit + calibration harness ($0) พบจุดอ่อนเชิงกลไกที่กระทบความถูกต้องของผลลัพธ์:
Fabric ใช้ RNG เส้นเดียว (คู่เทียบ A/B ปน noise — harness วัด delta คำชี้แจงพลิกเป็นบวก),
one-shot exposure (ไม่มี complex contagion), เครือข่าย WOM เป็น artifact ของลำดับ id;
Debate ใช้ uniform feed, ไม่มี silent majority, ไม่วัด conformity และ Red Team เป็น
soft framing ซึ่งงานวิจัยพบว่าไม่ได้ผล (อ้างอิงครบใน docs/reports/core-engine-audit-2026-07.md)

## มติ

1. **Common random numbers**: draw ทั้งหมดใน Fabric เป็น hashed uniform ต่อ
   (seed, event, msg, agent, attempt/round) — delta ของ SIM-04 fork/compare/red team
   เป็นผลเชิงสาเหตุจริง; determinism ต่อ seed คงเดิม (pure function ของ seed)
2. **Re-exposure**: ผู้ได้ยินที่ยังไม่เชื่อพิจารณาใหม่ได้ ≤3 ครั้ง โอกาสลดครึ่งต่อครั้ง
   (`RECONSIDER_MAX`/`RECONSIDER_DECAY` ใน engine.py)
3. **offline_wom = ring สุ่ม seeded** แทนลำดับ agent_id; กลุ่ม LINE 2-partition คงเดิม
4. **ค่าคงที่กลไกทั้งหมดมีชื่อ+จุดเดียว** (channels.py/engine.py) ป้ายชัด "สังเคราะห์ รอ
   calibrate"; `scripts/calibrate_fabric.py` เป็น harness ประจำ: invariant checks + sensitivity
   ranking (ผลปัจจุบัน: `public_feed.trust` ต้อง calibrate ก่อนสุด)
5. **Debate selective-exposure feed**: weighted ตาม channel_mix overlap (ฐาน 0.25);
   **voice layer** ตาม voice_activity (โพสต์เงียบมีจุดยืนแต่ไม่เข้าฟีด);
   **conformity metrics + consensus_warning** คำนวณ deterministic จากโพสต์ทุก run
6. **Red Team = devil's advocate เต็มรูป**: prompt โจมตีข้อสรุปเสียงข้างมากอย่างเป็นระบบ,
   contrarian ถูก cap จุดยืนไม่เป็นบวก + ห้าม concession เชิงกลไก, ฟีด red team เห็นโพสต์
   ที่ align กับ majority ที่สุด, metrics `red_team_pressure`; GOV-05 ไม่เปลี่ยน
7. ห้ามแก้เกณฑ์ test/benchmark เดิมเพื่อให้ผ่าน — FAB-01/ADR-0003 invariants ต้องผ่านด้วย
   กลไกใหม่จริง (ยืนยันแล้ว: ผ่านครบ)

## ผลกระทบ

- ตัวเลข trajectory ของ run ใหม่ต่างจาก engine v1 (draw เปลี่ยนชุด) — run เก่า replay จาก
  stored snapshot ไม่กระทบ; manifest ผูก code version อยู่แล้ว
- Debate ยังไม่ validate กับ LLM จริง (มติผู้ใช้) — instrumentation พร้อมให้อ่านจาก run จริง
  ที่ผู้ใช้รันเองตามนโยบาย pilot (ADR-0021)
- `expressed` ไม่ persist ลงคอลัมน์ debate_posts (ไม่มี migration) — voice metrics แม่นเฉพาะ
  payload ของ run ใหม่; ถ้าอนาคตต้องการ ให้เพิ่มคอลัมน์พร้อม migration แยก
