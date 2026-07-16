# ADR-0013 — Active business policy baseline

สถานะ: **Accepted — มติผู้ใช้ 16 ก.ค. 2026**

วันที่: 16 ก.ค. 2026

## บริบท

Chimlang มี cost metering, RBAC/Election Mode และ run-local reflection อยู่แล้ว แต่ยังไม่มีมติสำหรับ
commercial pricing, การเผยแพร่ source code, ผู้มีสิทธิ์ใช้ scenario การเลือกตั้งในวงกว้าง หรือการสร้าง
long-term semantic memory หากปล่อยให้สถานะเหล่านี้เป็นเพียงคำถามเปิด แต่ UI/runtime ไม่มี baseline
ที่อ่านได้ จะเสี่ยงให้ผู้ดูแลตีความต่างกันและเปิดความสามารถที่ยังไม่ผ่าน governance โดยไม่ตั้งใจ

มตินี้กำหนด **ค่าเริ่มต้นที่มีผลทันทีและปลอดภัย** เท่านั้น ไม่ได้เลือกรูปแบบธุรกิจหรือให้คำวินิจฉัยทางกฎหมาย

## มติ

1. **Pricing/metering:** เก็บจำนวน call, token, USD, reservation ต่อ run/เดือนเพื่อควบคุมงบเท่านั้น
   (`cost_observability_only_no_billing`) ห้ามออกใบแจ้งหนี้ ตัดสิทธิ์ หรือเปลี่ยน access ตาม commercial plan
   จนกว่าจะเลือก per-seat/per-run/enterprise contract และข้อกำหนดทางกฎหมาย
2. **Source strategy:** repository และ source distribution คงเป็น private
   (`private_repository_no_redistribution`) จนกว่าจะเลือก license, ขอบเขต public/private และตรวจ license
   ของ dependency/asset ครบ
3. **Election Mode:** ใช้ได้เฉพาะ verified admin และผลลัพธ์ aggregate-only
   (`verified_admin_only_aggregate_output`) การขยายสิทธิ์ต้องผ่าน human legal + ethics review ที่ระบุ
   องค์กร/ผู้ใช้ที่มีสิทธิ์และ workflow ตรวจสอบ
4. **Semantic memory:** ปิด long-term/autonomous memory และคงเฉพาะ bounded run-local reflection
   (`run_local_reflection_only`) การเปิดต้องมี pre-registered paired benchmark อย่างน้อย 30 คู่,
   quality gain อย่างน้อย 10%, cost/token overhead ไม่เกิน 20%, ไม่พบ cross-workspace leakage
   และได้รับ human approval

baseline ถูก expose แบบ read-only ที่ `GET /product-policy.json` และหน้า Settings เพื่อให้ operator เห็น
สถานะ, เหตุผล และ change gate จาก contract เดียวกัน ห้ามมี endpoint แก้ policy แบบ ad hoc

## เหตุผล

- แยก “วัดต้นทุน” ออกจาก “เรียกเก็บเงิน” ทำให้ BudgetGuard ทำงานต่อได้โดยไม่สร้าง commercial behavior
- private-by-default ป้องกันการให้สิทธิ์ source โดยปริยายก่อน license review
- Election Mode มีผลกระทบสูง จึงต้อง fail-closed และใช้ RBAC/verification เดิม
- semantic memory เพิ่ม privacy, drift และ cost surface; ต้องพิสูจน์ incremental benefit ก่อนเก็บข้อมูลข้าม run

## ผลตามมา

- การเปลี่ยน commercial model, source license, Election eligibility หรือ semantic-memory gate ต้องเขียน ADR ใหม่
  และขอมติผู้ใช้
- public GA ยังถูก block ตาม ADR-0012 จนกว่า TLS/OIDC/RLS/pen-test จะพร้อม
- `core/product_policy.py` เป็น machine-readable active baseline; เอกสาร future work เก็บตัวเลือกที่ยังต้องตัดสินใจ
- policy endpoint ไม่มี secret และ authenticated ตาม contract API ปัจจุบัน

## การทดสอบ

- unit test ยืนยันว่า billing/public repository/semantic memory ไม่ถูกเปิดโดยปริยาย
- API test ยืนยัน endpoint อ่าน baseline ได้และ Election default เป็น verified-admin aggregate-only
- frontend build แสดง policy ใน Settings โดยไม่สร้าง mutation control
