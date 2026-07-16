# P8-M5 offline benchmark report — 16 ก.ค. 2569

ชุดนี้เป็น fixture ภาษาไทยขนาดเล็กสำหรับตรวจ contract/harness ของ Phase 8 M5 โดยไม่เรียก LLM
และไม่ใช่หลักฐานว่าโมเดลแม่นในโลกจริง จึงรายงานตัวเลขดิบและ sample size โดยไม่ตั้ง pass threshold
ย้อนหลังเพื่อให้ checklist ดูเขียว

## ผลดิบ

| มิติ | n | ผล |
|---|---:|---|
| Thai retrieval | 2 queries | Recall@5 = 1.000, MRR@5 = 1.000 |
| Evidence relevance | 2 claims | citation validity = 1.000, precision = 1.000, unsupported = 1 |
| Subgroup fidelity | 3 groups | MAE = 0.013333, max error = 0.020000 |
| Social desirability | 2 cases | direction accuracy = 1.000, mean absolute gap = 0.350 |
| Future calibration | 4 resolved predictions | Brier = 0.0825, baseline = 0.2500, skill = 0.670, ECE = 0.275 |
| Run-local reflection smoke | 1 paired fixture, 2 calls | อยู่ใน call bound; verifier error ลดลงใน fixture |

## ข้อจำกัดที่ต้องคงไว้ในรายงาน

- Retrieval corpus เล็กและแต่งขึ้นเพื่อจับภาษาไทยไม่มีเว้นวรรค ไม่ใช่ relevance benchmark จากผู้ประเมินอิสระ
- Evidence/reflection เป็น contract smoke fixture; การลด error เกิดจาก paired fixture ที่กำหนดไว้ล่วงหน้า
  จึงห้ามตีความเป็น causal benefit ของ reflection หรือคุณภาพ analyst model
- Social-desirability มีเพียง 2 ทิศทางตัวอย่าง ไม่แทนประชากรไทยจริง
- Future calibration n=4 เล็กเกินสรุปความแม่น; ECE 0.275 ถูกเก็บตามจริง ไม่ซ่อนแม้ Brier ดีกว่า baseline
- งานถัดไปเชิงวิจัยคือเพิ่ม qrels ไทยที่ human-label, subgroup ground truth และ prediction อนาคตที่ resolve จริง

รันซ้ำ: `uv run python -m scripts.run_phase8_benchmarks`
