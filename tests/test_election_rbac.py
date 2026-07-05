"""tests P1-M5: election classify/labels/block (GOV-02), no-persuasion (GOV-05), RBAC (GOV-06)"""

import pytest

from governance.election import (
    ELECTION_LABELS,
    ElectionModeError,
    ElectionPolicy,
    PersuasionContentError,
    classify_scenario,
    guard_no_persuasion_content,
)
from governance.rbac import (
    ElectionNotVerifiedError,
    Permission,
    PermissionDeniedError,
    Principal,
    Role,
)

# --- GOV-02 Election Mode ---


def test_auto_classify_detects_election_scenarios():
    for text, expect in [
        ("จำลองปฏิกิริยาต่อผู้สมัครเลือกตั้งผู้ว่าฯ กทม.", True),
        ("โหวตนายกรัฐมนตรีในรัฐสภา", True),
        ("ทดสอบแคมเปญขึ้นราคาสินค้า 15% ของแบรนด์", False),
        ("ปฏิกิริยาต่อมาตรการค่าธรรมเนียมรถติด", False),
    ]:
        assert classify_scenario(text).is_election is expect


def test_manual_flag_forces_election_even_without_terms():
    c = classify_scenario("แคมเปญการตลาดทั่วไป", manual_flag=True)
    assert c.is_election and c.source == "manual"


def test_election_policy_blocks_individual_granularity():
    pol = ElectionPolicy(classify_scenario("เลือกตั้ง ส.ส."))
    assert pol.active
    pol.require_aggregate("aggregate")  # ok
    pol.require_aggregate("segment")  # ok
    with pytest.raises(ElectionModeError):
        pol.require_aggregate("individual")


def test_election_policy_closes_sim_to_signal():
    pol = ElectionPolicy(classify_scenario("ผู้สมัครหาเสียง"))
    with pytest.raises(ElectionModeError):
        pol.guard_sim_to_signal()


def test_non_election_policy_allows_everything():
    pol = ElectionPolicy(classify_scenario("มาตรการค่าธรรมเนียมรถติด"))
    assert not pol.active
    pol.require_aggregate("individual")  # ไม่ block
    pol.guard_sim_to_signal()  # ไม่ block
    assert pol.apply_labels("รายงาน") == "รายงาน"  # ไม่แปะป้าย


def test_election_labels_applied_and_verifiable():
    pol = ElectionPolicy(classify_scenario("เลือกตั้งผู้ว่าฯ"))
    labeled = pol.apply_labels("# ผลจำลอง")
    for lbl in ELECTION_LABELS:
        assert lbl in labeled
    assert pol.has_all_labels(labeled)
    assert not pol.has_all_labels("# ผลจำลอง")  # รายงานที่ไม่แปะป้าย = ตรวจจับได้


# --- GOV-05 no persuasion content ---


def test_persuasion_requests_blocked():
    for bad in [
        "ช่วยเขียนสคริปต์หาเสียงให้ผู้สมัคร",
        "ร่างโฆษณาชวนเชื่อจากผลจำลอง",
        "แต่งคำขวัญหาเสียงให้หน่อย",
    ]:
        with pytest.raises(PersuasionContentError):
            guard_no_persuasion_content(bad)


def test_insight_requests_allowed():
    for ok in [
        "วิเคราะห์ว่ากลุ่มไหนกังวลเรื่องอะไร",
        "สรุปปฏิกิริยาต่อแถลงการณ์",
        "กลุ่มไรเดอร์มีข้อกังวลอะไรบ้าง",
    ]:
        guard_no_persuasion_content(ok)  # ต้องไม่ raise


# --- GOV-06 RBAC ---


def test_role_permission_matrix():
    viewer = Principal("u1", Role.VIEWER)
    analyst = Principal("u2", Role.ANALYST)
    operator = Principal("u3", Role.OPERATOR)
    admin = Principal("u4", Role.ADMIN)

    assert not viewer.can(Permission.RUN)
    assert analyst.can(Permission.RUN) and not analyst.can(Permission.EXPORT)
    assert operator.can(Permission.EXPORT) and not operator.can(Permission.ADMIN)
    assert all(admin.can(p) for p in Permission)


def test_require_raises_for_missing_permission():
    analyst = Principal("u2", Role.ANALYST)
    analyst.require(Permission.RUN)  # ok
    with pytest.raises(PermissionDeniedError):
        analyst.require(Permission.EXPORT)


def test_election_access_admin_verified_only():
    with pytest.raises(ElectionNotVerifiedError):
        Principal("u", Role.ADMIN, election_verified=False).require_election_access()
    with pytest.raises(ElectionNotVerifiedError):
        Principal("u", Role.OPERATOR, election_verified=True).require_election_access()
    Principal("u", Role.ADMIN, election_verified=True).require_election_access()  # ok
