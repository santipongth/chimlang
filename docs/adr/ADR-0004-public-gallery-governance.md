# ADR-0004 — Governance ของ Public Gallery (P5-M8)

- วันที่: 12 ก.ค. 2026 | สถานะ: ใช้งาน (ผู้ใช้สั่ง "ทำต่อ" กับ backlog — การตัดสินใจ GOV ด้านล่างเป็นของ agent, **ผู้ใช้ veto/ปรับได้**)
- บริบท: SwarmSight มี public gallery + agree/disagree votes (wisdom of crowd vs swarm) ซึ่งตรงกับ CIT-02 (Public Simulation Portal) ของ PRD — แต่การเผยแพร่ผลจำลองสู่สาธารณะคือจุดเสี่ยงสูงสุดที่จะถูกอ้างเป็น "โพลจริง" (ความเสี่ยงหลักใน PRD ข้อ 10)

## การตัดสินใจ (fail-closed ทุกข้อ)

1. **Election scenario ห้ามแชร์เด็ดขาด** — เข้มกว่า GOV-02 ปกติ (ที่ยอมให้ aggregate + ป้าย 3 ชนิด): บนหน้าสาธารณะไม่มีผู้ควบคุมบริบทการอ่าน จึงตัดความเสี่ยงทั้งใบ ผู้ใช้ที่ต้องการแชร์ผลการเมืองต้องมาขอปลดล็อกเป็นกรณีไป
2. **แชร์ = export** — ต้องสิทธิ์ `EXPORT` (operator/admin — analyst แชร์ไม่ได้ ตรงกับกติกา P4-M4) และ `WATERMARK_ENABLED=true` เท่านั้น; payload ฝัง watermark dict (label + labels 3 ชนิด + เวลาแชร์) และหน้าเว็บสาธารณะแสดง banner ถาวร
3. **หัวข้อผ่าน PII detector ก่อนแชร์** — detector ปิด = ปฏิเสธการแชร์ (แบบเดียวกับ ingest)
4. **Snapshot frozen** — payload ถ่ายสำเนา ณ เวลาแชร์ (NFR-07) ไม่มี code path แก้ไข มีแต่ "ถอนแชร์" (active=false — record คงอยู่เพื่อ audit) และทุกการแชร์/ถอน append audit log (GOV-04)
5. **Votes ไม่เก็บตัวตน** — dedup ด้วย `sha256(salt|ip|ua)` ทางเดียว ไม่เก็บ IP/UA ดิบ (PDPA, NFR-04); 1 hash = 1 เสียง/รายการ (โหวตซ้ำ = เปลี่ยนเสียง); แสดงเฉพาะยอดรวม agree/disagree (aggregate เท่านั้น)
6. **อ่าน + โหวตเป็นสาธารณะ** (ไม่ต้อง API key) — precedent เดียวกับ citizen endpoints (persona P4 ของ PRD) + rate limit กันสแปม

## ทางเลือกที่ไม่เอา

- แชร์ผล election แบบ aggregate + ป้าย (ตาม GOV-02 ปกติ) — ปฏิเสธ: ประเมินแล้วความเสี่ยง "ถูกตัดต่อ/อ้างเป็นโพล" บนพื้นที่สาธารณะสูงเกินคุณค่า
- เก็บ vote ผูก user account — ปฏิเสธ: บังคับ login ขัดเจตนา Citizen Mode และสร้างข้อมูลส่วนบุคคลโดยไม่จำเป็น
- ให้แก้ payload หลังแชร์ — ปฏิเสธ: ขัด NFR-07 และเปิดช่องตัวเลขสาธารณะถูกเปลี่ยนเงียบๆ

## ผลกระทบ

- ตาราง `gallery_shares` / `gallery_votes` เป็น operational (unshare/เปลี่ยนเสียงได้) — ไม่ใช่ governance record จึงไม่ติด append-only trigger แต่การแชร์/ถอนทุกครั้งลง audit log
- Crowd score (votes) แสดงคู่ swarm confidence เพื่อการเรียนรู้ — ไม่ป้อนกลับเข้า simulation อัตโนมัติ (ต่างจาก CIT-03 ที่มี k-anonymity ≥20 คุม) จนกว่าจะมีมติผู้ใช้
