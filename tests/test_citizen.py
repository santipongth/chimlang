"""tests P3: CIT-01 validation/session-only, CIT-02 portal, CIT-03 k-anonymity, CIT-04 disclaimer"""

import pytest
from fastapi.testclient import TestClient

import api.app as api_app
from simulation.citizen import (
    CITIZEN_DISCLAIMER,
    K_ANONYMITY,
    CitizenInputs,
    FeedbackPool,
    ImpactTwin,
    InvalidCitizenInputError,
    build_impact_twin,
    match_segment,
    render_citizen_portal,
)
from simulation.persona import PersonaFactory

DSN = "postgresql://chimlang:chimlang@localhost:5432/chimlang"


def _inputs(**over) -> CitizenInputs:
    base = dict(
        income_band="15k-30k",
        region="ชานเมือง",
        commute="รถยนต์ส่วนตัว",
        occupation="พนักงานออฟฟิศ",
        age_band="31-45",
        household_size=3,
    )
    base.update(over)
    return CitizenInputs(**base)


# --- CIT-01 ---


def test_inputs_closed_choices_only():
    with pytest.raises(InvalidCitizenInputError):
        _inputs(region="บ้านเลขที่ 99/1 ซอยลาดพร้าว")  # free text = ปฏิเสธโดยโครงสร้าง
    with pytest.raises(InvalidCitizenInputError):
        _inputs(household_size=99)


def test_match_segment_transparent_rules():
    factory = PersonaFactory()
    assert match_segment(_inputs(occupation="ไรเดอร์/ขนส่ง"), factory) == "gig_transport_workers"
    assert match_segment(_inputs(age_band="60 ขึ้นไป"), factory) == "elderly_community"
    assert match_segment(_inputs(region="นอกแนวขนส่งสาธารณะ"), factory) == "suburban_no_transit"
    assert match_segment(_inputs(), factory) == "working_commuter"


def test_impact_twin_ranges_and_disclaimer():
    twin = build_impact_twin(_inputs(), PersonaFactory(), agents=60, max_agents=1000, seed=42)
    for lo, hi in (twin.concern_baseline, twin.concern_after_response):
        assert 0.0 <= lo <= hi <= 1.0  # ช่วงเสมอ (TRUST-09)
    d = twin.to_dict()
    assert d["disclaimer"] == CITIZEN_DISCLAIMER  # CIT-04
    assert "ความไม่แน่นอน" in d["note"]


# --- CIT-03 k-anonymity (DB จริง) ---


@pytest.fixture()
def pool() -> FeedbackPool:
    p = FeedbackPool(DSN)
    try:
        p.setup()
    except Exception:
        pytest.skip("PostgreSQL ไม่พร้อม")
    import psycopg

    with psycopg.connect(DSN) as conn:
        conn.execute("DELETE FROM citizen_feedback WHERE segment_id LIKE 'test-%'")
    return p


def test_k_anonymity_withholds_until_20(pool):
    for _ in range(K_ANONYMITY - 1):
        pool.add("test-seg", "เห็นด้วย")
    assert all(a["segment_id"] != "test-seg" for a in pool.aggregates())  # 19 เสียง = กัก
    assert "test-seg" in pool.withheld_segments()
    pool.add("test-seg", "ไม่เห็นด้วย")  # ครบ 20
    released = [a for a in pool.aggregates() if a["segment_id"] == "test-seg"]
    assert released and all(a["n_total"] == K_ANONYMITY for a in released)


def test_feedback_stance_validated(pool):
    with pytest.raises(InvalidCitizenInputError):
        pool.add("test-seg2", "ข้อความอิสระยาวๆ")  # stance นอกลิสต์ = ปฏิเสธ


# --- CIT-02/04 portal ---


def test_portal_disclaimer_permanent_top_and_bottom():
    twin = ImpactTwin("working_commuter", "วัยทำงาน", (0.3, 0.5), (0.1, 0.3), "n")
    page = render_citizen_portal("ทดสอบ", twin, [])
    assert page.count(CITIZEN_DISCLAIMER) >= 2  # หัว + ท้าย = ถาวรจริง
    assert "30%–50%" in page or "30%" in page
    assert "20 คน" in page or "20 เสียง" in page  # สื่อสารเกณฑ์ k-anonymity


# --- CIT-03 ครึ่งหลัง: inject เสียงจริงกลับเข้า sim ---


def test_disagree_share_and_no_feedback_returns_none():
    from simulation.citizen import apply_feedback_round, disagree_share_from

    assert disagree_share_from([]) is None
    aggs = [
        {"segment_id": "s", "stance": "เห็นด้วย", "count": 12, "n_total": 20},
        {"segment_id": "s", "stance": "ไม่เห็นด้วย", "count": 5, "n_total": 20},
        {"segment_id": "s", "stance": "กังวลแต่ยังไม่ตัดสินใจ", "count": 3, "n_total": 20},
    ]
    assert disagree_share_from(aggs) == pytest.approx(0.4)  # (5+3)/20
    assert (
        apply_feedback_round([], PersonaFactory(), max_agents=1000, seed=1) is None
    )  # ไม่มีเสียงผ่านเกณฑ์ = ไม่ inject


def test_feedback_effect_shows_both_ranges():
    from simulation.citizen import apply_feedback_round, render_citizen_portal

    aggs = [
        {"segment_id": "s", "stance": "ไม่เห็นด้วย", "count": 15, "n_total": 20},
        {"segment_id": "s", "stance": "เห็นด้วย", "count": 5, "n_total": 20},
    ]
    effect = apply_feedback_round(aggs, PersonaFactory(), agents=60, max_agents=1000, seed=7)
    assert effect is not None and effect.disagree_share == pytest.approx(0.75)
    for lo, hi in (effect.concern_without_feedback, effect.concern_with_feedback):
        assert 0.0 <= lo <= hi <= 1.0
    # เสียงค้าน 75% เป็น prior → รอบ "หลังรับเสียง" ต้องเริ่มสูงกว่ารอบปกติ
    assert effect.concern_with_feedback[0] >= 0.5
    twin = ImpactTwin("working_commuter", "วัยทำงาน", (0.3, 0.5), (0.1, 0.3), "n")
    page = render_citizen_portal("t", twin, aggs, effect)
    assert "เสียงจริงเปลี่ยนผลจำลองอย่างไร" in page
    assert "ก่อน" in page and "หลัง" in page  # แสดงคู่เสมอ = โปร่งใส


def test_inject_feedback_to_memory(pool):
    from governance.pii import PIIDetector
    from simulation.citizen import inject_feedback_to_memory
    from simulation.memory import WorldMemory

    memory = WorldMemory(DSN, PIIDetector())
    memory.setup()
    memory.reset_world("test-citizen-ws")
    aggs = [{"segment_id": "test-seg", "stance": "เห็นด้วย", "count": 20, "n_total": 20}]
    assert inject_feedback_to_memory(aggs, memory, "test-citizen-ws") == 1
    items = memory.recall("test-citizen-ws")
    assert items and "aggregate" in items[0].content and items[0].kind == "real_event"


# --- Production route boundary ---


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(api_app.app)


def test_citizen_demo_routes_are_not_mounted_in_production(client):
    assert client.post("/citizen/impact.json", json={}).status_code == 404
    assert client.post("/citizen/feedback.json", json={}).status_code == 404
