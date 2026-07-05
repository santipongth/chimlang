"""Auth + RBAC ที่ API (P4-M4 — GOV-06 บังคับจริง)

รูปแบบ: API key ผ่าน header `X-API-Key` — คีย์กำหนดใน env:
    AUTH_ENABLED=true
    API_KEYS=คีย์:ชื่อผู้ใช้:role[:verified],คีย์2:ชื่อ:role

- AUTH_ENABLED=false (default ช่วง dev): ทุก request เป็น dev-admin (verified) + log เตือน
- เปิดแล้ว: ไม่มี/คีย์ผิด = 401; สิทธิ์ไม่พอ = 403 (Principal.require)
- Citizen endpoints เปิดสาธารณะโดยเจตนา (P4 ของ PRD คือประชาชน) — ไม่บังคับคีย์
- Election scenario: ต้อง admin ที่ verified เท่านั้น (GOV-02 + GOV-06)
"""

from fastapi import Header, HTTPException

from core.config import get_settings
from governance.rbac import (
    ElectionNotVerifiedError,
    Permission,
    PermissionDeniedError,
    Principal,
    Role,
)

DEV_PRINCIPAL = Principal("dev-local", Role.ADMIN, election_verified=True)


def parse_api_keys(raw: str) -> dict[str, Principal]:
    """แปลง API_KEYS จาก env — รายการที่รูปแบบเสีย = ข้าม (fail-closed: คีย์นั้นใช้ไม่ได้)"""
    out: dict[str, Principal] = {}
    for entry in raw.split(","):
        parts = [p.strip() for p in entry.strip().split(":")]
        if len(parts) < 3 or not parts[0]:
            continue
        try:
            role = Role(parts[2])
        except ValueError:
            continue
        out[parts[0]] = Principal(
            user_id=parts[1],
            role=role,
            election_verified=len(parts) > 3 and parts[3] == "verified",
        )
    return out


def get_principal(x_api_key: str | None = Header(default=None)) -> Principal:
    settings = get_settings()
    if not settings.auth_enabled:
        return DEV_PRINCIPAL  # โหมด dev — เปิด AUTH_ENABLED=true ก่อนขึ้น production
    if not x_api_key:
        raise HTTPException(status_code=401, detail="ต้องส่ง X-API-Key (GOV-06)")
    principal = parse_api_keys(settings.api_keys).get(x_api_key)
    if principal is None:
        raise HTTPException(status_code=401, detail="API key ไม่ถูกต้อง (GOV-06)")
    return principal


def require(principal: Principal, permission: Permission) -> None:
    try:
        principal.require(permission)
    except PermissionDeniedError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e


def require_election(principal: Principal) -> None:
    try:
        principal.require_election_access()
    except ElectionNotVerifiedError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
