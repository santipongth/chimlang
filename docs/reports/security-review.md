# Security Self-Review — Phase 4 M6 (6 ก.ค. 2026) + อัปเดต Phase 5 (12 ก.ค. 2026)

> รีวิวภายในโดย agent ผู้พัฒนา — **ไม่ใช่ penetration test อิสระ** (NFR-05 กำหนด pen test
> ภายนอกก่อน GA จริง ซึ่งยังไม่ทำ) เอกสารนี้บอกตรงๆ ว่าอะไรบังคับแล้ว/อะไรยังไม่ทำ

## 🆕 Phase 8 M7 production hardening (16 ก.ค. 2026)

- monthly budget มี transaction advisory lock + reservation ก่อน enqueue, actual-spend settlement และ release;
  จึงไม่ใช่ read-then-enqueue check ที่ concurrent sweep แซงกันได้อีก
- CI export lock แล้วรัน `pip-audit -r` และ `npm audit --audit-level=high`; local audit ณ วันส่งมอบ
  ไม่พบ known vulnerability ใน dependency (ตัว package `chimlang` เองถูก skip เพราะไม่ใช่ package บน PyPI)
- `scripts.production_readiness` ไม่แสดงค่า secret และ fail-closed สำหรับ public GA เมื่อไม่มี HTTPS,
  independent pen-test, OIDC หรือ PostgreSQL RLS
- ADR-0012 ถูก Deferred: ระบบ production ปัจจุบันยังเป็น self-hosted single-tenant + API key ตามมติเดิม;
  readiness metadata ไม่ได้แปลว่า OIDC/RLS ถูก implement แล้ว

## 🆕 Surface ใหม่จาก Phase 5 (12 ก.ค. 2026)

| Surface | การป้องกัน | ความเสี่ยงคงเหลือ (ตรงๆ) |
|---|---|---|
| `/gallery.json`, `/gallery/{token}.json`, `/gallery/{token}/vote` — **สาธารณะ ไม่ต้องมี key** (โดยเจตนา ADR-0004) | แชร์ต้อง EXPORT+watermark+PII gate+ไม่ใช่ election; snapshot frozen; vote dedup ด้วย hash(salt\|ip\|ua) ไม่เก็บ ip ดิบ; rate limit 60/นาที | rate limiter เป็น per-process in-memory (หลาย worker = quota แยกกัน); vote dedup หลบได้ถ้าเปลี่ยน ip/ua (ยอมรับ — เป็น sentiment ไม่ใช่การลงคะแนนทางการ) |
| `/predictions/{id}/resolve` (P5-M3) | RUN perm (analyst+), append-only 2 ชั้น (UNIQUE + trigger), audit ทุกครั้ง | resolver ป้อน outcome ผิดได้ — ป้องกันด้วย note บังคับใจ + immutable ทำให้ตรวจย้อนเจอ |
| Watchlist webhook (P5-M5) | https เท่านั้น, best-effort, URL เป็น secret ใน `.env` ไม่เก็บ DB/ไม่ log | SSRF ในทางทฤษฎีถ้าผู้ดูแลตั้ง URL ชี้ intranet เอง — ผู้ตั้งค่าคือ admin ของเครื่องเองจึงยอมรับ; payload alert ไม่มีข้อมูลลับ |
| Persona packs (P5-M7) | PII gate ทุกข้อความรวมที่ AI สร้าง (fail-closed เมื่อ detector ปิด), validate โครงเข้ม, LLM ผ่าน BudgetGuard | prompt injection ใส่ใน pack prompt มีผลแค่ segments ที่ยังต้องผ่าน validate/PII — เสี่ยงต่ำ |
| MCP server (P5-M9, ADR-0005) | **ห่อ REST เท่านั้น ไม่มี privileged path** — auth/RBAC/election/cap บังคับที่ API ตามเดิม; key อยู่ env ของ process MCP | สิทธิ์ของ agent ภายนอก = role ของ key ที่ออกให้ — ผู้ดูแลต้องออก key ขั้นต่ำที่จำเป็น (แนะนำ analyst ไม่ใช่ admin) |

## ✅ บังคับแล้วระดับโค้ด + มี test

| ด้าน | กลไก |
|---|---|
| Secrets | อยู่ใน `.env` เท่านั้น (gitignore), ไม่มีการ log key; `.env.prod` แยกจาก dev |
| PII (GOV-01) | detector fail-closed ทุกทางเข้าข้อมูล: ingest corpus, war room feed, living memory; Citizen = ตัวเลือกปิดล้วน ไม่มีช่อง free text |
| AuthN/AuthZ (GOV-06) | X-API-Key + RBAC 4 role; viewer รันไม่ได้, analyst export ไม่ได้; election = admin verified เท่านั้น; คีย์รูปแบบเสีย = ใช้ไม่ได้ |
| Election (GOV-02) | aggregate-only + ป้ายบังคับ + Sim-to-Signal ปิด — บังคับทั้ง API และใน task (ยิงตรงข้าม API ก็โดน) |
| Export (GOV-03) | จุดเดียว + watermark 2 ชั้น (md/PDF), ปิด flag = ไม่มีไฟล์ออก |
| Append-only (GOV-04/TRUST-01) | PostgreSQL trigger กัน UPDATE/DELETE — ทดสอบยิง SQL ตรง |
| SQL injection | ทุก query ใช้ parameterized (psycopg placeholders) — ไม่มี string interpolation จาก user input |
| Rate limit | signal endpoint 429 (SIG-04) |
| HTTP headers | nosniff / X-Frame-Options DENY / Referrer-Policy (middleware) |
| Cost/DoS ภายใน | BudgetGuard ทุก LLM call + cap agents ต่อ run + clamp ที่ endpoint |

## ⚠️ ยังไม่ทำ / เป็นหน้าที่ตอน deploy จริง (บอกตรงๆ)

1. **TLS/HTTPS** — image เสิร์ฟ HTTP :8000; production ต้องมี reverse proxy (Caddy/nginx) ทำ TLS
2. **Penetration test อิสระ** (NFR-05) — จำเป็นก่อนเปิดให้บุคคลภายนอกใช้จริง
3. **SSO/SAML** สำหรับ enterprise — ยังเป็น API key; พอสำหรับ self-hosted ทีมเดียว
4. **Workspace isolation ระดับ tenant** — ยังเป็น single-tenant (สอดคล้องมติ self-hosted)
5. Rate limit ครอบทุก endpoint + audit ของ 401/403 — มีเฉพาะ signal; ควรขยายเมื่อเปิด public
6. Dependency scanning อัตโนมัติ (dependabot/pip-audit ใน CI)

## คำแนะนำเมื่อเปิดใช้จริง (self-hosted ตามมติผู้ใช้)

- ตั้ง `AUTH_ENABLED=true` + `API_KEYS` ที่แข็งแรง (สุ่มยาว ≥ 32 ตัว) ใน `.env.prod` เสมอ
- เปลี่ยน `POSTGRES_PASSWORD` / `NEO4J_PASSWORD` จากค่า dev
- อย่าเปิดพอร์ต 8000 ออก internet ตรงๆ — ผ่าน reverse proxy + TLS เท่านั้น
