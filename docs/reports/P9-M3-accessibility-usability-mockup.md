# P9-M3 — TH/EN, WCAG 2.2 AA และ usability mockup

วันที่: 17 ก.ค. 2026
สถานะ: engineering audit ผ่าน; human usability claim ยัง blocked

## TH/EN และ locale

- dictionary contract ตรวจทุก key ว่ามี TH/EN ไม่ว่าง และตรวจ static t("key") ทุก route/component
- route-level pages ทุกหน้าต่อ language context; html lang เปลี่ยนตาม locale
- number/currency/date formatter ใช้ th-TH/en-US ใน Experiments, Insights, New Run, Settings และ Calibration
- แก้ข้อความตกหล่นใน Experiments, provider health, Settings และปุ่ม Close
- สลับภาษาระหว่างเปิด mobile drawer ได้โดย drawer ไม่ปิดเอง และ focus restore ยังถูกต้อง

## WCAG automated + interaction audit

- axe-core รัน WCAG 2 A/AA, 2.1 A/AA และ 2.2 AA บน 13 top-level routes ทั้ง desktop/mobile
- primary foreground/background ปรับ contrast หลัง axe พบ ratio เดิมประมาณ 2.5:1
- skip-to-content เป็น keyboard-first control; route focus/aria-live, drawer focus trap/restore และ 404/deep links
- focus-visible หนา 3px, reduced-motion, overflow-wrap, table reflow และ viewport 320×720 ไม่มี horizontal overflow
- interactive target ที่เห็นใน main content ไม่มีด้านใดต่ำกว่า 24 CSS px ตาม WCAG 2.2 minimum target
- automated axe ไม่พบ violation ใน state ที่ stub API ว่าง และ functional E2E เดิมครอบ populated states

ข้อจำกัด: automated audit ไม่รับรอง conformance ทั้งหมดด้วยตัวเอง ยังต้องมี screen-reader/high-contrast/
zoom และผู้ใช้พิการจริงในรอบ pilot

## Mockup ทดสอบผู้ใช้จริง

route #/usability มี participant runner P01–P05, consent gate, timer, complete/blocked, critical errors,
ease 1–5, note category, moderator success criterion, local persistence และ anonymized JSON export.
งานหลักห้าข้อคือ Project, Evidence freeze, start/cancel run, Validation claim readiness และ stored export.

ระบบไม่เก็บ free-text หรือ PII และไม่สร้างผลแทนผู้เข้าร่วม claim_ready เป็น true ได้เมื่อ consent ครบห้าคน
และงานจริง 25/25 ถูกบันทึกเท่านั้น ขณะส่งมอบยังเป็น 0/25 จึงห้ามอ้าง completion ≥80% หรือ pilot success

## Verification

| gate | ผล |
|---|---|
| backend | 419 tests ผ่าน |
| Ruff/migration | ผ่าน; schema current/no-op |
| frontend unit | 4 files / 8 tests ผ่าน |
| accessibility E2E | 13 routes + interaction/mockup desktop/mobile ผ่าน |
| full E2E | 26 tests desktop/mobile |
| production build | initial index 93.14 kB; usability lazy 12.30 kB |
| bundle gate | +13.6% จาก Phase 8 baseline ~82 kB; ต่ำกว่า +15% |
| production dependency audit | 0 vulnerabilities |
