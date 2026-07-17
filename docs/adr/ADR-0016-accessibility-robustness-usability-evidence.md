# ADR-0016 — Accessibility, model robustness และ usability evidence

สถานะ: Accepted เฉพาะ TH/EN + WCAG; validation/usability surfaces ถูก supersede โดย ADR-0019
วันที่: 17 ก.ค. 2026
ขอบเขต: Phase 9 M2/M3

## บริบท

Phase 9 ต้องปิดสามช่องว่างก่อน pilot: TH/EN และ WCAG 2.2 AA ทั้งแอป, การวัดความทนทานข้ามโมเดล
แบบควบคุมงบ และเครื่องมือเก็บ usability จากผู้ใช้ไทยจริงห้าคน โดยยังต้องรักษาหลัก append-only,
BudgetGuard, PII fail-closed และห้ามอ้าง accuracy/pilot success ก่อนมี ground truth จริง

## มติ

1. validation dataset kinds เพิ่ม model_robustness และ usability ผ่าน migration ledger; report ที่ complete
   เท่านั้นจึงเป็น measured และความพยายามที่ล้มเหลวต้อง invalidate แบบ append-only
2. robustness runner ใช้ prompt/persona ภาษาไทยชุดเดียว, seed/temperature คงที่, adapter เดียว,
   preflight + transactional monthly reservation และไม่เก็บ rationale ดิบ ค่าวัด agreement เป็น
   consistency ไม่ใช่ accuracy เพราะไม่มี human ground truth
3. WCAG automated gate ใช้ axe บน route หลักทั้ง desktop/mobile ร่วมกับ contract tests สำหรับ dictionary,
   static translation keys และ locale formatters; manual-risk controls มี skip-to-content, focus trap/restore,
   320px reflow, reduced motion และ target ขั้นต่ำ 24 CSS px
4. usability runner เก็บใน localStorage เฉพาะรหัส P01–P05, consent, เวลา, completion, critical-error count,
   ease score และหมวดปัญหา ไม่มีชื่อ/ข้อมูลติดต่อ/free-text ดิบ การ export ตั้ง claim_ready ได้เมื่อ
   consent ครบและงานจริง 25/25 เท่านั้น

## ผลตามมา

- Validation Lab แยก measured/blocked สำหรับ robustness ได้โดยไม่ปะปนกับ MIRACL หรือ human panel
- automated checks ลด regression แต่ไม่แทนการ audit ด้วย assistive technology และผู้ใช้พิการจริง
- mockup พร้อมดำเนินการ แต่ usability claim ยัง blocked จนมีผู้ใช้จริงอย่างน้อยห้าคนและรายงาน raw hash
- model/provider ที่ account policy ไม่อนุญาตถือเป็น execution failure ไม่ถูกคัดออกจาก audit history
