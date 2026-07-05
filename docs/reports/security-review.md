# Security Self-Review — Phase 4 M6 (6 ก.ค. 2026)

> รีวิวภายในโดย agent ผู้พัฒนา — **ไม่ใช่ penetration test อิสระ** (NFR-05 กำหนด pen test
> ภายนอกก่อน GA จริง ซึ่งยังไม่ทำ) เอกสารนี้บอกตรงๆ ว่าอะไรบังคับแล้ว/อะไรยังไม่ทำ

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
