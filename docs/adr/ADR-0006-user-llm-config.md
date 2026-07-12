# ADR-0006 — LLM ปรับเปลี่ยนได้จากหน้าตั้งค่า (P6)

- วันที่: 12 ก.ค. 2569 | สถานะ: ใช้งาน (ผู้ใช้สั่ง "หน้าตั้งค่าเลือก LLM provider ยอดนิยม + ปรับ/เปลี่ยน LLM เองได้")
- บริบท: เดิม LLM ตั้งได้เฉพาะใน `.env` (SIM-07: OpenAI-compatible adapter เดียว) — ผู้ใช้อยากเลือก provider และเปลี่ยน model จากหน้าเว็บ

## การตัดสินใจ

1. **เลือก provider preset ได้ 6 ตัว** (`core/llm/userconfig.py`): OpenRouter (default), OpenAI,
   Groq, Together AI, Ollama (local), และ "กำหนดเอง" — ทุกตัวเป็น OpenAI-compatible ตาม SIM-07
   จึงเสียบผ่าน adapter เดิมได้โดยไม่แตะ business logic
2. **ตั้งได้จาก UI**: provider, base URL, ชื่อ model (crowd/analyst), ราคา token ของ model ที่เพิ่มเอง
   — เก็บใน `app_settings` (operational, ไม่ใช่ secret)
3. **API key อยู่ `.env` เท่านั้น** (`LLM_API_KEY`) — **ไม่รับ key จาก UI และไม่ส่ง key กลับใน response ใดๆ**
   (กติกา secrets ของ repo: ห้าม key ใน DB/log/หน้าจอ) หน้าตั้งค่าแสดงแค่ "ตั้งค่าแล้ว/ยังไม่ตั้ง"
4. **fail-closed เดิมคงอยู่**: model ที่ไม่มีราคา (ทั้งใน `pricing.yaml` และที่ผู้ใช้กรอก) = รันไม่ได้
   — BudgetGuard ต้องรู้ราคาเสมอ ไม่งั้นคุมงบไม่ได้ (`PricingRegistry.merged()` รวมสองแหล่ง)
5. **overlay ไม่ทำลาย .env**: ค่าว่างใน UI = ใช้ `.env` ตามเดิม; ปุ่ม "ล้างค่า" คืนสู่ `.env` ทั้งหมด
   (`effective_llm_settings()` / `effective_pricing()` เป็นจุดรวมที่ debate/persona_ai เรียก)

## ทางเลือกที่ไม่เอา

- **รับ API key จาก UI เก็บใน DB (เข้ารหัส)** แบบ SwarmSight (`engine_configs.encrypted_api_key`) —
  ปฏิเสธ: เพิ่มพื้นผิวรั่วของ secret และขัดกติกา repo ที่ secrets อยู่ `.env` จุดเดียว; self-hosted
  ทีมเดียว (มติ D9) ตั้ง `.env` ได้อยู่แล้ว
- **ปล่อยให้รัน model ที่ไม่มีราคา** — ปฏิเสธ: BudgetGuard ตาบอด = งบบานเงียบๆ (จุดอ่อน SwarmSight)

## ผลกระทบ

- Ollama (local) ตั้งราคา 0 ได้ = จำลองด้วยโมเดลบนเครื่องตัวเอง ข้อมูลไม่ออกนอกเครื่อง (ตรง NFR-04)
- model ใหม่ที่ผู้ใช้เพิ่ม ต้องกรอกราคาเอง (หน้า Settings มีช่อง หรือแก้ `config/pricing.yaml`) —
  ราคามาตรฐาน (qwen) มีให้แล้ว
- เปลี่ยน model backend ได้โดยไม่กระทบ Prediction Registry เดิม (NFR-10 — model_version ถูก stamp ต่อ run)
