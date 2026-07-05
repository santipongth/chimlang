"""RBAC ขั้นต่ำ (GOV-06) — แยกสิทธิ์ create / run / export / admin

Phase 1 ระดับ API layer: ตรวจสิทธิ์ก่อนทำ action; election mode ปลดล็อกเฉพาะ role
ที่ผ่าน verification (Phase 1 = admin เท่านั้น จนกว่าจะมีระบบ verify org จริง)
"""

from dataclasses import dataclass, field
from enum import StrEnum


class Permission(StrEnum):
    CREATE = "create"  # สร้าง workspace/scenario
    RUN = "run"  # สั่งรัน simulation
    EXPORT = "export"  # export รายงาน
    ADMIN = "admin"  # จัดการสิทธิ์ + ปลดล็อก election mode


class Role(StrEnum):
    VIEWER = "viewer"
    ANALYST = "analyst"
    OPERATOR = "operator"
    ADMIN = "admin"


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.VIEWER: frozenset(),
    Role.ANALYST: frozenset({Permission.CREATE, Permission.RUN}),
    Role.OPERATOR: frozenset({Permission.CREATE, Permission.RUN, Permission.EXPORT}),
    Role.ADMIN: frozenset(Permission),
}


class PermissionDeniedError(Exception):
    def __init__(self, role: Role, permission: Permission):
        super().__init__(f"role '{role}' ไม่มีสิทธิ์ '{permission}' (GOV-06)")
        self.role = role
        self.permission = permission


class ElectionNotVerifiedError(Exception):
    def __init__(self, role: Role):
        super().__init__(
            f"role '{role}' ไม่ได้รับอนุญาตให้ใช้ election mode — "
            "Phase 1 จำกัดเฉพาะ admin ที่ผ่าน verification (GOV-06)"
        )


@dataclass(frozen=True)
class Principal:
    user_id: str
    role: Role
    election_verified: bool = field(default=False)

    def can(self, permission: Permission) -> bool:
        return permission in ROLE_PERMISSIONS[self.role]

    def require(self, permission: Permission) -> None:
        if not self.can(permission):
            raise PermissionDeniedError(self.role, permission)

    def require_election_access(self) -> None:
        """ปลดล็อก election scenario ได้เฉพาะ admin ที่ verify แล้ว (GOV-06 + GOV-02)"""
        if not (self.role == Role.ADMIN and self.election_verified):
            raise ElectionNotVerifiedError(self.role)
