# P9-M2 — MIRACL Thai retrieval benchmark

วันที่รัน: 17 ก.ค. 2026
สถานะ: **measured — full governed corpus/dev set**

## Dataset contract

| รายการ | ค่าที่ใช้จริง |
|---|---|
| MIRACL topics/qrels revision | `5be20db9509754dadad47689368639fcec739c00` |
| MIRACL corpus revision | `d921ec7e349ce0d28daf30b2da9da5ee698bef0d` |
| license | Apache-2.0 |
| Thai corpus | 2 shards, 542,166/542,166 passages |
| Thai dev | 733/733 queries |
| topics SHA-256 | `6ef23316d1224d9fef9e3f8bc2fdf527dad1a3bba98657617398c226503f5a46` |
| qrels SHA-256 | `81097e891775f67a9b98d41309f9c452dc4e09572b0cbf4952d4107ed0fe1407` |
| corpus shard 0 SHA-256 | `49728f2682602179d8381d0bf0eeaf6eb75bdb5332f9366832ee8e430e4f422c` |
| corpus shard 1 SHA-256 | `62c501dbbe34af63449ccce9fe62f4b09e7296872a330217c2895969ab961c8a` |

แหล่งข้อมูลคือ [MIRACL repository](https://github.com/project-miracl/miracl) และ
[MIRACL corpus](https://huggingface.co/datasets/miracl/miracl-corpus/tree/main/miracl-corpus-v1.0-th).

## ผลดิบ

| metric | raw value |
|---|---:|
| Recall@100 | `0.8645883410208103` |
| MRR@10 | `0.45551711817059704` |
| nDCG@10 | `0.45184514527907516` |
| query count | `733` |
| ranking latency | `306.3348339000004 s` |
| total latency | `319.0432978000026 s` |
| provider cost | `$0.00` |
| raw-result SHA-256 | `0ebcba9b024a5c7959b22ad4fb89be2f3e309d32bdff94dbbd9cd602a6264638` |
| Validation dataset/report | `validation-miracl-9bb5b3a295ad` / `validation-report-3f144d1e3ece466a` |

Raw per-query result ถูกสร้างที่ `.tmp/miracl-th/miracl-th-0ebcba9b024a.json`; runner
`scripts/run_miracl_th.py` สร้างซ้ำได้จาก revisions/hashes ข้างต้น และ Validation Lab เก็บ aggregate,
metadata กับ raw-result hash แบบ append-only

## วิธีรันและ governance

- retrieval เป็น BM25 ที่ใช้ token + Thai character trigram แบบเดียวกับ fallback ของระบบ ไม่ใช่
  Pyserini baseline และไม่ได้เรียก embedding/LLM
- compressed bytes ถูก hash ระหว่าง stream และไม่ persist; ทุก title/text ผ่าน `redact_and_verify`
  ก่อนเขียน sanitized gzip cache
- detector แทนที่ person name 66,270 ครั้ง, phone 83, Thai ID 16 และ email 18 ครั้งในสอง shards
- metrics นี้จึงวัด **governed sanitized Chimlang BM25 pipeline บน MIRACL qrels** ไม่ควรนำไปเทียบตรงกับ
  published MIRACL baseline ที่ใช้ corpus ดิบ/tokenizer อื่น

## Audit ของรอบที่ไม่ครบ

รอบแรกอ่านเฉพาะ `docs-0` 500,000 passages และได้ผลที่สูง/ต่ำต่างจากรอบเต็ม จึงห้ามอ้างผลนั้น
ระบบไม่ได้ลบหรือแก้ย้อนหลัง แต่ append `benchmark_invalidation`
`validation-report-eb37ba33ee6c4a01` เพื่อ invalidate
`validation-report-4b7ff2ee06464d91` พร้อมเหตุผลว่า shard `docs-1` ถูกละไว้

## ข้อจำกัด

- เป็น retrieval relevance benchmark ไม่ใช่หลักฐาน simulation accuracy หรือ population validity
- ไม่มี provider cost แต่มีค่า CPU/network/disk ที่รายงานนี้ยังไม่แปลงเป็นเงิน
- human-panel และ pilot usability claim ยังถูก block จนมีการเก็บผลจริงตาม consent/protocol
