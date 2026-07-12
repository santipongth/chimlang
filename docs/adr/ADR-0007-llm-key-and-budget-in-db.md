# ADR-0007 — LLM API key + ราคา + งบ ตั้งได้จากหน้าเว็บ (พลิก ADR-0006 บางส่วน)

- วันที่: 12 ก.ค. 2569 | สถานะ: ใช้งาน (**ผู้ใช้สั่งชัด**: "ใส่และกำหนด LLM_API_KEY ที่หน้า setting แทน รวมทั้งราคาโมเดล ตัด .env ออก ... ตั้งค่าทุกอย่างที่หน้านี้")
- บริบท: ADR-0006 กำหนดว่า API key อยู่ `.env` เท่านั้น (ไม่รับจาก UI) — ผู้ใช้ต้องการตั้งทุกอย่างจากหน้าเว็บ รวม key

## การตัดสินใจ (ผู้ใช้เลือกผ่าน AskUserQuestion)

1. **API key เก็บใน DB แบบเข้ารหัส** (`core/secretbox.py` — Fernet/AES) — **กุญแจหลัก (master key)
   ยังอยู่ `.env` จุดเดียว** (`CHIMLANG_SECRET_KEY`) ดังนั้น DB dump/backup รั่วก็ถอด key ไม่ได้
   ถ้าไม่มี master key → เก็บ/อ่าน key ไม่ได้ (fail-closed ไม่ fallback plaintext)
2. **ไม่โชว์ key เต็ม/ไม่ส่งกลับ**: response แสดงแค่ masked (`sk-or-…aB3z`) + สถานะ (db/env/none);
   ciphertext (`llm_api_key_enc`) ถูกกรองออกจากทุก response; endpoint ตั้ง key แยก
   (`PUT /settings/llm-key`, ADMIN เท่านั้น) ไม่ปนกับ PUT settings ปกติ
3. **ราคาโมเดลตั้งจาก UI** — แก้ราคามาตรฐาน (จาก `pricing.yaml`) หรือเพิ่มโมเดลใหม่;
   fail-closed เดิมคง: โมเดลไม่มีราคา = รันไม่ได้ (BudgetGuard ต้องรู้ราคา)
4. **งบ 2 ระดับตั้งจาก UI**: ต่อรัน (ทับ `RUN_BUDGET_USD_CAP`) + **รวมต่อเดือน** (ใหม่ —
   `core/llm/budget.py`: track LLM spend สะสม, เกิน = block ก่อนรัน)
5. **`.env` ตัดไม่หมด (bootstrap paradox)**: รหัส DB/Neo4j/Redis + master key + API_KEYS ของ auth
   ยังต้องอยู่ `.env` เพราะระบบต้องต่อ DB *ก่อน* จะอ่าน settings จาก DB ได้ — แจ้งผู้ใช้แล้ว

## ทางเลือกที่ไม่เอา

- เก็บ key plaintext ใน DB — ผู้ใช้เลือก "เข้ารหัส" เอง (DB รั่วไม่พอถอด)
- ย้ายรหัส DB มา UI ด้วย — เป็นไปไม่ได้เชิงเทคนิค (ไก่กับไข่)

## ผลกระทบต่อกฎเหล็ก

กฎเดิม "Secrets อยู่ `.env` เท่านั้น" (CLAUDE.md/AGENTS.md) ถูกผ่อนเป็น: **secret ที่ bootstrap
(รหัส DB/master key/auth keys) อยู่ `.env`; LLM API key ตั้งจาก UI ได้แต่ต้องเข้ารหัสด้วย
master key จาก `.env` และห้ามโชว์/log เต็ม** — อัปเดตข้อความในสองไฟล์แล้ว

## วิธีเปิดใช้

1. `.env`: ตั้ง `CHIMLANG_SECRET_KEY` (สร้าง: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`)
2. หน้า Settings → 🔑 API key → วาง key → บันทึก (เก็บเข้ารหัส)
