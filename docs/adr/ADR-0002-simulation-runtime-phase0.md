# ADR-0002: Simulation runtime สำหรับ Phase 0 — runtime เบาของเราเอง (OASIS-compatible ภายหลัง)

- **สถานะ**: Accepted (5 ก.ค. 2026 — มติผู้ใช้)
- **เกี่ยวข้อง**: TECH-DECISIONS D2, PHASE0-BRIEF M3, แผนความเสี่ยงข้อ 4

## บริบท

D2 เลือก "ต่อยอด CAMEL-AI OASIS" พร้อมเงื่อนไข spike time-boxed ใน M3 — ถ้าติดขัดให้เขียน ADR เสนอทางเลือก

## ผล spike (5 ก.ค. 2026)

ติดตั้ง `camel-oasis` แบบ ephemeral สำเร็จ (`uv run --with camel-oasis`): import ผ่าน, camel 0.2.78

| ประเด็น | ข้อค้นพบ |
|---|---|
| น้ำหนัก dependency | 126 packages รวม **torch + transformers + sentence-transformers (หลาย GB)** — Phase 0 ใช้ LLM ผ่าน OpenRouter เท่านั้น ไม่ได้ inference local |
| Platform model | API ออกแบบรอบ Twitter/Reddit (`generate_twitter_agent_graph`, `DefaultPlatformType`, recsys) — ช่องทางไทยทั้ง 4 (LINE closed group / public feed / algo feed / offline WOM) ต้องเขียน platform ใหม่เองในสถาปัตยกรรมของ OASIS |
| จุดแข็งของ OASIS | scale ถึงหลักล้าน agents + recsys จำลอง — **ไม่ใช่ความต้องการของ Phase 0** (ข้อจำกัดผู้ใช้: ≤10 agents ช่วง dev; เป้าเฟส: 100–1,000) |
| การเชื่อมระบบเรา | budget guard / adapter tier / reasoning trail / seed ต้อง bypass หรือห่อ model layer ของ camel อีกชั้น — เพิ่ม surface ที่ต้องกัน bug โดยไม่ได้ฟีเจอร์ที่ต้องใช้ |

สรุป: สิ่งที่ Phase 0 ต้องการ (round-based loop + 4 ช่องทางไทย custom + cultural priors + trail + cost guard)
ต้อง**เขียนเองทุกชิ้นอยู่แล้ว** ไม่ว่าจะวางบน OASIS หรือไม่ — OASIS ให้แต่โครงที่ต้องรื้อรอบๆ

## ข้อเสนอ

1. **Phase 0: เขียน simulation runtime เบาของเราเอง** ใน `simulation/` — agent dataclass (persona/belief/memory สั้น),
   channel simulator 4 แบบพารามิเตอร์แพร่ต่างกัน, round loop เรียก LLM ผ่าน `core/llm` (ได้ budget guard + trail ฟรี),
   deterministic ด้วย `random.Random(seed)` ของเราเอง
2. **ออกแบบ interface ให้สลับ runtime ได้** (spirit เดียวกับ D4 pgvector→Zep): channel/agent abstraction ไม่ผูกกับ loop
   — ถ้า Phase 1+ ต้อง scale เกินหลักพันหรืออยาก reuse recsys ของ OASIS ค่อยประเมินใหม่เป็น ADR-000X
3. D2 ยังคงคุณค่า: ใช้ OASIS/MiroFish เป็น **reference design** (โครงสร้าง action space, memory pattern) ไม่ใช่ dependency

## ผลที่ตามมา

- (+) dependency บาง (ไม่มี torch), ควบคุม reproducibility/cost/trail ได้ 100%, ทุกบรรทัดตรงความต้องการ PRD
- (+) benchmark FAB-01 ทำได้เร็ว เพราะพารามิเตอร์การแพร่อยู่ในมือเราตรงๆ
- (−) ไม่ได้ community/optimization ของ OASIS — ยอมรับได้ที่ scale Phase 0; ความเสี่ยง scale ถูกยกไป Phase 1 พร้อมจุดประเมินใหม่ชัดเจน
- TECH-DECISIONS D2 จะถูกอัปเดตให้ชี้ ADR นี้เมื่อผู้ใช้อนุมัติ
