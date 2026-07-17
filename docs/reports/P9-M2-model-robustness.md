# P9-M2 — Thai multi-model robustness run

วันที่รัน: 17 ก.ค. 2026
สถานะ: measured consistency artifact; ไม่ใช่ accuracy benchmark

## ชุดทดสอบและ governance

- 6 เคสภาษาไทยแบบ stratified: policy, product และ crisis อย่างละ 2 persona
- 3 โมเดลผ่าน OpenRouter: google/gemini-2.5-flash-lite, google/gemini-2.5-flash และ
  google/gemini-3.1-flash-lite-preview
- ทุก call ผ่าน core/llm adapter + BudgetGuard; temperature 0, seed 20260717, structured schema เดียว
- preflight 0.007092 USD ภายใต้ cap 5 USD/run และ 50 USD/month; actual measured run 0.002412 USD
- pricing snapshot มาจาก OpenRouter models API และถูก pin ลง report metadata
- ไม่ persist rationale ดิบ; เก็บเฉพาะ stance/confidence/token/cost/latency/Thai-language flag

## ผลดิบ

| metric | ผล |
|---|---:|
| calls สำเร็จ/คาดหมาย | 18/18 |
| structured parse success | 100% |
| rationale ภาษาไทย | 100% |
| pairwise stance agreement | 0.888889 |
| mean confidence dispersion | 0.059075 |
| actual cost | 0.002412 USD |

| model | parse | cost USD | p50 latency | mean confidence |
|---|---:|---:|---:|---:|
| Gemini 2.5 Flash Lite | 6/6 | 0.0002452 | 0.867s | 0.7667 |
| Gemini 2.5 Flash | 6/6 | 0.0012573 | 1.4065s | 0.7667 |
| Gemini 3.1 Flash Lite Preview | 6/6 | 0.0009095 | 1.2035s | 0.8750 |

Artifact:

- dataset validation-model-robustness-57c638b1cbef
- report validation-report-43283b5d9fa44f13
- raw result hash d26cb50f335f20df55471f0a8e227aa97fc62fc571c760191822989c1c00c269

## ความพยายามที่ไม่ผ่าน

ก่อนรอบ measured มีสองรอบที่ fail closed:

1. Qwen Flash/Qwen 30B/Gemini: Qwen calls ล้มจาก provider errors; report
   validation-report-c6efb642aafb4bc9 ถูก invalidate ด้วย validation-report-78b25b3c270c4417
2. Mistral/Llama/Gemini: non-Google routes ถูก OpenRouter account data-policy ปฏิเสธ; report
   validation-report-30e1db1fa14a406c ถูก invalidate ด้วย validation-report-54731a4be5fd45df

สองรอบนี้เสียจริงรวมประมาณ 0.0004808 USD; provider spend ทั้ง session รวมประมาณ 0.0028928 USD.
ไม่มีการลบหรือเขียนทับประวัติ และไม่เอา failed calls มาทำให้ agreement ของรอบ measured ดูดีขึ้น

## ข้อจำกัด

agreement 0.888889 หมายถึงโมเดลให้หมวด stance ตรงกันใน prompt เดียวกัน ไม่ได้แปลว่าคำตอบถูกต้อง,
แทนประชากรไทยได้ หรือ calibrated กับ outcome จริง ชุดนี้มีเพียง 6 synthetic cases และสามโมเดลมาจาก
provider family เดียวกันเพราะ account routing policy จึงยังไม่ใช่ cross-provider external validity

แหล่งราคา/model: https://openrouter.ai/api/v1/models
