# FUTURE WORK — งานหลัง Phase 8

อัปเดตล่าสุด: 16 ก.ค. 2026

เอกสารนี้เป็น source of truth สำหรับงานที่ตั้งใจเลื่อนไว้หลัง Phase 8 เพื่อให้กลับมาอ่านต่อได้โดยไม่ต้องมี
ประวัติแชต งานในนี้ **ยังไม่ถือว่าอนุมัติ architecture หรืออนุญาต deploy**; เมื่อจะเริ่มงานที่มีคำว่า
“ต้องมีมติ” ให้เปลี่ยน ADR/brief และขอข้อมูลที่ระบุก่อน

## สถานะปัจจุบัน

- ระบบที่รองรับจริง: self-hosted, single-tenant, API key + RBAC, HTTP หลังเครือข่ายที่เชื่อถือได้
- `python -m scripts.production_readiness --profile public-ga --env-file .env.prod` จะ fail-closed
  จนกว่า TLS, independent pen-test, OIDC และ tenant RLS พร้อม
- Phase 8 M1–M7 ปิดแล้ว; baseline 387 backend tests + frontend/E2E ผ่าน
- ข้อเสนอเดิมอยู่ใน `docs/adr/ADR-0012-public-ga-identity-tenancy-tls.md` แต่ผู้ใช้สั่งเลื่อน 3 งานหลัก
  ด้านล่างไว้เป็น future work จึงยังไม่มี vendor/claim/tenant design ที่ถือเป็นมติ

## ลำดับที่แนะนำเมื่อกลับมาทำ Public GA

1. ตกลง tenant/role contract และแผน backfill ก่อน เพราะกระทบ schema และ authorization ทุกชั้น
2. Implement tenant isolation + adversarial isolation tests
3. Implement OIDC บน tenant/role contract ที่ตกลงแล้ว โดยคง API key เฉพาะ service account/MCP
4. วาง TLS termination และทดสอบ callback/SSE ผ่าน public URL จริง
5. จ้าง penetration test อิสระ แก้ findings แล้ว rerun `public-ga` readiness

TLS ต้องพร้อมก่อนเปิด OIDC ต่อผู้ใช้จริง แต่การออกแบบ tenant claim ต้องเสร็จก่อนเขียน OIDC mapping เพื่อไม่
ผูก schema กับ claim ที่ยังไม่ตกลง

---

## FW-GA-01 — TLS/HTTPS termination

สถานะ: **Deferred — ต้องมีมติและข้อมูล deployment**

ความสำคัญ: Blocker ก่อนเปิดอินเทอร์เน็ต/public GA

### ปัญหาและเป้าหมาย

production Compose ปัจจุบัน publish FastAPI ที่ `:8000` แบบ HTTP. เป้าหมายคือไม่ expose API โดยตรง,
redirect HTTP→HTTPS, terminate certificate ที่ reverse proxy/load balancer และรักษา SSE/large response/health
checks ให้ทำงานเหมือนเดิม

### ทางเลือกที่ต้องตัดสินใจ

- **Caddy ใน Compose (แนะนำเมื่อเป็น standalone self-hosted):** config/renew certificate ง่าย แต่เพิ่ม
  service และ volume certificate ที่ต้อง backup
- **Reverse proxy/load balancer ขององค์กร:** เหมาะเมื่อมี ingress, WAF หรือ certificate lifecycle อยู่แล้ว;
  repo เก็บเพียง trusted-proxy contract และ deployment guide

อย่าใส่ Caddy/nginx เพิ่มพร้อมกันหรือ publish ทั้ง proxy และ `:8000` ออกสาธารณะ

### ข้อมูลที่ต้องเตรียม

- public domain และสิทธิ์แก้ DNS
- ใครเป็นผู้ terminate TLS, certificate issuer/อีเมล และพอร์ต 80/443 ที่เปิดได้
- public URL ของ UI/API, upload/body limit, request timeout และ network topology
- หากมี load balancer เดิม: forwarded-header format และรายการ trusted proxy CIDRs

### Implementation checklist

- ปิด public port ของ API; expose เฉพาะเครือข่าย Compose/internal network
- เพิ่ม HTTPS listener, HTTP redirect, certificate persistence/renewal และ health endpoint
- trust `X-Forwarded-*` เฉพาะ proxy ที่กำหนด; ห้ามเชื่อ header จาก client ตรง
- เพิ่ม HSTS หลังยืนยัน HTTPS ทุก subdomain แล้ว, CSP ที่เข้ากับ Vite app, และ secure cookie flags สำหรับ OIDC
- ทดสอบ `/app/`, API, PDF/export, SSE reconnect, large run payload และ error/timeout ผ่าน proxy
- เขียน rollback/runbook สำหรับ certificate renewal failure

### Acceptance criteria

- สแกนจากภายนอกเข้าถึงได้เฉพาะ 80/443; 80 redirect ไป canonical HTTPS
- TLS certificate valid/renew ได้; API `:8000` เข้าจากอินเทอร์เน็ตไม่ได้
- security headers ครบและ SSE reconnect ไม่สูญ event
- `production_readiness public-ga` ผ่าน check `tls`

---

## FW-GA-02 — Enterprise SSO ผ่าน OIDC

สถานะ: **Deferred — ต้องเลือก provider/claims**

ความสำคัญ: Blocker สำหรับ enterprise/public user authentication

### ปัญหาและเป้าหมาย

ระบบปัจจุบันใช้ static API key ซึ่งเหมาะกับทีมเดียวและ service account แต่ไม่มี user lifecycle, MFA,
revocation หรือ organization identity. เป้าหมายคือ provider-neutral OIDC Authorization Code + PKCE,
map signed claims ไปยัง tenant/role เดิม และคง API key เฉพาะ MCP/automation ที่ออกแบบเป็น service account

### ข้อมูลที่ต้องเตรียม

- OIDC issuer/provider, client id/secret และ redirect/logout URLs
- claim ที่เป็น stable user id, tenant/organization id, groups/roles และ verified-email policy
- ตาราง mapping group→Chimlang role (`viewer/analyst/operator/admin`) และผู้มีสิทธิ์ election verification
- session lifetime, idle timeout, MFA/conditional-access policy และ break-glass admin procedure
- ต้องรองรับ SAML โดยตรงหรือให้ identity broker แปลง SAML→OIDC

### Security/implementation checklist

- validate issuer, audience, signature/JWKS, expiry, nonce, state และ PKCE ทุก login
- browser session ใช้ `HttpOnly + Secure + SameSite` cookie; ไม่เก็บ bearer token ใน localStorage
- CSRF protection สำหรับ state-changing browser requests และ rotate session หลัง login/privilege change
- tenant/role มาจาก signed claim หรือ server mapping เท่านั้น; ห้ามรับจาก query/header ที่ client กำหนดเอง
- audit login success/failure, role mapping, logout/revocation โดยไม่ log token/secret/PII เกินจำเป็น
- API key เดิมกลายเป็น scoped service account พร้อม rotation/expiry ไม่ใช่ fallback admin แบบถาวร
- เพิ่ม unit/integration tests สำหรับ wrong issuer/audience, expired token, key rotation, role downgrade,
  cross-tenant claim และ election permission

### Acceptance criteria

- ผู้ใช้ login/logout/revocation ผ่าน provider จริงและ role ตรง mapping
- token ปลอม/หมดอายุ/wrong audience ถูก block; ไม่มี token ใน log/localStorage
- service account/MCP ยังทำงานด้วย key ที่ scope/rotate ได้
- `production_readiness public-ga` ผ่าน check `oidc`

---

## FW-GA-03 — Multi-tenant isolation ด้วย PostgreSQL RLS

สถานะ: **Deferred — ต้องยืนยันว่าจะเปิด multi-tenant และแผนข้อมูลเก่า**

ความสำคัญ: Blocker ก่อนให้หลายองค์กรใช้ฐานข้อมูลเดียวกัน

### ปัญหาและเป้าหมาย

ตาราง operational ปัจจุบันเป็น single-tenant. การเติม `tenant_id` เฉพาะ API filter ไม่พอ เพราะ query ใหม่,
Celery task หรือ maintenance script อาจลืม filter. เป้าหมายคือ tenant context ที่มาจาก signed identity และ
PostgreSQL Row-Level Security เป็น fail-closed boundary ใกล้ system of record พร้อมรักษา append-only triggers
ของ prediction/audit

### ข้อมูลที่ต้องเตรียม

- tenant identifier claim จาก OIDC และชื่อ/id ของ default tenant สำหรับ snapshot เก่า
- จะใช้ shared database+RLS หรือ database แยกต่อ tenant; data residency/retention ของแต่ละองค์กร
- super-admin/support access, export/delete/offboarding policy และ cross-tenant aggregate ว่าอนุญาตหรือไม่
- ownership ของ gallery public snapshot, model/provider settings, budgets, API keys และ webhook ต่อ tenant

### Migration plan (expand → backfill → enforce)

1. inventory ทุกตาราง/unique key/FK/cache/vector/Neo4j node และ object ที่ต้องมี tenant
2. เพิ่ม nullable `tenant_id` + tenant table โดยยังไม่เปิด RLS
3. backfill snapshot เก่าเข้า default tenant และตรวจ orphan/duplicate ก่อนเปลี่ยน unique key เป็น composite
4. propagate tenant ผ่าน API principal → Celery headers/payload → retrieval/LLM ledger/audit/telemetry
5. เปิด RLS policies แบบ deny เมื่อไม่มี tenant context; owner/bypass role ไม่ใช้กับ request/worker ปกติ
6. เปลี่ยน `tenant_id` เป็น NOT NULL, เพิ่ม composite FK/index และเปิด feature flag ทีละ environment
7. Neo4j/vector/cache/query ทุกเส้นทางต้องมี tenant boundary เดียวกัน; public gallery แยก frozen-public policy

### Adversarial tests บังคับ

- tenant A เดา run id/share token/member id ของ B แล้วอ่าน/แก้/ลบไม่ได้
- worker/retry/SSE/experiment/calibration/export/search/vector retrieval ไม่ข้าม tenant
- SQL query ที่ไม่มี tenant context คืนศูนย์แถวหรือถูกปฏิเสธ ไม่ fallback เป็น global
- admin support action ต้อง explicit, audited และไม่ใช้ browser-supplied tenant header
- backup/restore และ tenant offboarding ไม่กระทบ tenant อื่น

### Acceptance criteria

- automated two-tenant isolation suite ผ่านทุก API/worker/storage boundary
- PostgreSQL RLS เปิดและ request/worker role ไม่มี `BYPASSRLS`
- snapshot เก่าครบใน default tenant; append-only prediction/audit triggers ยังทำงาน
- `production_readiness public-ga` ผ่าน check `tenant_isolation`

---

## งานอื่นที่ยังเหลือ

### A. จำเป็นก่อน Public GA

1. **Independent penetration test + remediation** — ต้องเป็นบุคคล/ทีมภายนอก; self-review และ scanner
   อัตโนมัติแทนไม่ได้. เก็บ report path ให้ readiness ตรวจและทำ retest หลังแก้ Critical/High
2. **Distributed rate limiting + auth abuse audit** — rate limiter บางจุดยังเป็น in-memory/per-process;
   ควรใช้ Redis policy แยก public/auth/run/export และ audit 401/403 โดยไม่เก็บ credential
3. **Backup/restore/DR drill** — กำหนด RPO/RTO, encrypted PostgreSQL/Neo4j/Redis/certificate backup,
   restore test และ disaster runbook; volume อย่างเดียวไม่ใช่ backup
4. **Operational SLO/alerts** — queue latency, stale jobs, provider health, budget exhaustion, DB/storage,
   certificate expiry และ error taxonomy มี metrics แล้วแต่ยังต้องตั้ง alert owner/escalation จริง
5. **Legal/ethics readiness** — ToS/privacy/retention/liability, election-mode eligibility และ data-processing
   agreement ต้องผ่าน human legal/ethics review (PRD Open Questions #2/#6)

### B. Trust และ external validity — สำคัญกว่าการเพิ่ม simulation feature

1. **MIRACL Thai retrieval benchmark จริง** — download เข้า `.tmp/`, pin revision/hash/license, PII
   redact+verify, รัน BM25/vector/hybrid และรายงาน raw Recall/MRR/nDCG/cost/latency. ตอนนี้มีเพียง harness
   ขนาดเล็ก จึงห้ามอ้าง external validity
2. **Future-event calibration จริง** — สะสม binary predictions ที่มี measurement/due date, resolve ด้วย
   evidence และรายงาน Brier/reliability/ECE พร้อม sample uncertainty; ห้ามสร้าง outcome จำลองเพิ่มจำนวน
3. **TRUST-08 human panel** — ตัดสินใจว่าจะสร้าง consent-based panel เองหรือ partner บริษัทวิจัยตลาด;
   pre-register sampling/agreement metric และให้ human approve persona adjustment
4. **Population/subgroup calibration** — นำสำมะโน/แบบสำรวจที่มี provenance มา calibrate segment share,
   media diet และ cultural priors; synthetic priors ปัจจุบันยังไม่ใช่ population truth
5. **Pilot/field evidence** — เป้าหมาย PRD เรื่อง pilot customers/war-room incidents เป็น business validation
   ไม่ใช่สิ่งที่ unit test พิสูจน์ได้

### C. Engineering debt ที่ทำได้ภายหลังโดยไม่เปลี่ยน product contract

1. แยก endpoint กลุ่มที่เหลือจาก `api/app.py` (ยังประมาณ 2,000 บรรทัด) เป็น routers/services พร้อม
   response models เพื่อให้ generated OpenAPI types ไม่ต้อง cast
2. ย้าย raw `fetch` ที่เหลือใน `web/src/api.ts` (ประมาณ 37 จุด) ไป typed client/TanStack Query
3. ลด on-demand chart chunks เพิ่มเติม (ECharts ~642 kB, Cytoscape ~444 kB) หากข้อมูล real-user
   performance ชี้ว่าจำเป็น; initial bundle ถูกลดเหลือ ~82 kB แล้วจึงไม่ใช่ blocker
4. แก้ warning FastAPI/TestClient ที่รอ `httpx2` โดยอัปเกรดเมื่อ dependency ecosystem รองรับและ CI ผ่าน
5. เพิ่ม real production load/soak test ที่มี auth, Redis queue, SSE reconnect, budget reservation และ
   1,000-agent payload พร้อมกัน ไม่ใช้เฉพาะ mocked browser payload

### D. งานที่ต้องมีมติธุรกิจ/ผลิตภัณฑ์

- business model/metering: per-seat, per-run หรือ enterprise license (PRD Open Question #4)
- open-source strategy และ license review (Open Question #5; repo คง private จนมีมติ)
- election-mode eligibility: ใครใช้ scenario การเมืองได้และขั้นตอน verification/legal review
- semantic/long-term autonomous memory: เริ่มเมื่อ benchmark แสดงประโยชน์ชัด; ตอนนี้คง run-local reflection

## สิ่งที่ยังไม่ควรทำอัตโนมัติ

- deep 5,000 agents ต้องขออนุมัติเพิ่ม; cap ปัจจุบัน 1,000
- continuous forecast, autonomous outcome scraping และ Debate 3 seeds เป็น default ยังอยู่นอกงบ $50/เดือน
- public votes ห้ามป้อนกลับ engine อัตโนมัติ
- ห้ามอ้าง benchmark, calibration หรือ pen-test ว่า “ผ่าน” ก่อนมี dataset/outcome/report จริง
