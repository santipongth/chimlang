# ADR-0012 — Public GA identity, tenant isolation และ TLS

สถานะ: **Deferred — บันทึกใน `docs/FUTURE-WORK.md` ตามมติผู้ใช้ 16 ก.ค. 2026**

วันที่: 16 ก.ค. 2026

## บริบท

ระบบปัจจุบันถูกอนุมัติสำหรับ self-hosted single-tenant และใช้ API key + RBAC. การเปิด public GA
ต้องเพิ่ม TLS termination, enterprise identity และ tenant isolation ซึ่งเป็นการเปลี่ยน architecture/data model
จึงห้ามเลือกแทนผู้ใช้โดยไม่มี ADR ตาม `AGENTS.md`.

## ทางเลือกที่เสนอ

1. **TLS:** Caddy ใน production Compose, รับ `PUBLIC_DOMAIN`/อีเมล certificate และไม่ publish API :8000
   โดยตรง; ทางเลือกคือให้องค์กร terminate TLS ที่ load balancer เดิม
2. **Identity:** provider-neutral OIDC Authorization Code + PKCE; map group/claim → role เดิมและเก็บ API key
   สำหรับ service account/MCP. ไม่ผูก business logic กับ vendor. SAML ทำผ่าน OIDC broker หากจำเป็น
3. **Tenant isolation:** เพิ่ม `tenant_id` ใน operational tables และบังคับ PostgreSQL Row-Level Security;
   tenant มาจาก signed OIDC claim เท่านั้น. ตาราง prediction/audit ยังคง append-only ภายใน tenant
4. **Rollout:** migration แบบ expand/backfill/enforce, default tenant สำหรับ snapshot เก่า, shadow policy test,
   แล้วจึงเปิด multi-tenant flag; ห้ามเปิดเพียงด้วย header ที่ client กำหนดเอง

## เหตุผลที่แนะนำ

- OIDC เป็นมาตรฐานกลางและคง RBAC/REST/MCP contract เดิมได้
- PostgreSQL RLS เป็นด่าน fail-closed ใกล้ system of record มากกว่ากรองเฉพาะ application query
- TLS ที่ reverse proxy แยก certificate lifecycle ออกจาก FastAPI และรองรับ deployment เดิม

## มติที่ต้องการเมื่อหยิบงานกลับมาทำ

- TLS อยู่ที่ Caddy ใน Compose หรือ load balancer/reverse proxy ขององค์กร
- OIDC provider/issuer และ claim ที่ใช้ map tenant/role
- ยอมรับ PostgreSQL RLS + default tenant migration หรือคง single-tenant ต่อ

จนกว่าจะมีมติ `public-ga` readiness ต้อง block OIDC/tenant/TLS/independent pen-test และระบบยังถือว่า
self-hosted single-tenant เท่านั้น
