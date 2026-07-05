"""tests P1-M4: บทบาทครบตาม PRD, GOV-05 clause ใน prompt, parsing/fail-closed, จัดลำดับ risk"""

from simulation.redteam import (
    ROLES,
    Attack,
    build_attack_prompt,
    build_score_prompt,
    parse_attack,
    parse_score,
    render_attack_surface_report,
    run_red_team,
)


def test_roles_match_prd_list():
    ids = {r.role_id for r in ROLES}
    # PRD REH-02: troll, IO, คู่แข่ง, สื่อสายจับผิด, นักกฎหมาย
    assert {"troll", "io_operative", "competitor", "investigative_media", "lawyer"} <= ids
    assert len(ROLES) >= 5


def test_attack_prompt_has_gov05_and_thai_guardrails():
    prompt = build_attack_prompt(ROLES[0], "แผนทดสอบ", 1)
    assert "GOV-05" in prompt
    assert "ห้ามเขียนคอนเทนต์พร้อมเผยแพร่จริง" in prompt  # กฎเหล็กข้อ 5
    assert "ภาษาไทยเท่านั้น" in prompt
    assert "ห้ามกุตัวเลข" in prompt


def test_parse_attack_valid_and_garbage():
    role = ROLES[0]
    ok = parse_attack(
        role, '{"attack": "จุดประเด็นภาษีคนจน", "exploit": "ไม่มีข้อยกเว้นชัด", "channel": "X"}'
    )
    assert ok is not None and ok.role_id == role.role_id
    assert parse_attack(role, "ตอบไม่เป็น JSON") is None
    assert parse_attack(role, '{"attack": ""}') is None  # โจมตีว่างเปล่า = ทิ้ง


def test_parse_score_fail_closed_scores_medium_not_dropped():
    a = Attack("troll", "ชาวเน็ต", "x", "y", "z")
    s = parse_score(a, "ประเมินไม่ได้ครับ")
    assert (s.likelihood, s.damage) == (3, 3)  # ความเสี่ยงที่วัดไม่ได้ห้ามหายจากรายงาน
    s2 = parse_score(a, '{"likelihood": 5, "damage": 4, "reason": "จุดติดง่าย"}')
    assert s2.risk == 20
    s3 = parse_score(a, '{"likelihood": 9, "damage": 0, "reason": "นอกช่วง"}')
    assert (s3.likelihood, s3.damage) == (3, 3)  # นอกช่วง 1-5 = fail-closed


def test_run_red_team_sorted_by_risk_with_fake_adapter():
    class FakeAdapter:
        def __init__(self):
            self.calls = 0

        def chat(self, tier, messages, **kwargs):
            from types import SimpleNamespace

            self.calls += 1
            content = messages[0]["content"]
            if "นักวิเคราะห์ความเสี่ยง" in content:  # judge call
                score = 5 if "แรงสุด" in content else 2
                return SimpleNamespace(
                    text=f'{{"likelihood": {score}, "damage": {score}, "reason": "r"}}'
                )
            marker = "แรงสุด" if "troll" not in content and "แซะ" not in content else "เบา"
            return SimpleNamespace(
                text=f'{{"attack": "ประเด็น{marker}", "exploit": "e", "channel": "c"}}'
            )

    scored = run_red_team(FakeAdapter(), "แผนทดสอบ", attacks_per_role=1, seed=1)
    assert len(scored) == len(ROLES)
    risks = [s.risk for s in scored]
    assert risks == sorted(risks, reverse=True)  # เรียงมาก→น้อยเสมอ


def test_report_ranked_and_labeled():
    a_hi = parse_score(
        Attack("lawyer", "นักกฎหมาย", "ฟ้องศาลปกครอง", "อำนาจไม่ชัด", "ศาล"),
        '{"likelihood": 5, "damage": 5, "reason": "ช่องกฎหมายจริง"}',
    )
    a_lo = parse_score(
        Attack("troll", "ชาวเน็ต", "ทำมีม", "ภาพลักษณ์", "X"),
        '{"likelihood": 2, "damage": 1, "reason": "แรงไม่พอ"}',
    )
    report = render_attack_surface_report("แผนทดสอบ", [a_hi, a_lo])
    assert "Attack Surface Report" in report
    assert "GOV-05" in report and "simulation_estimate" in report
    assert report.index("ฟ้องศาลปกครอง") < report.index("ทำมีม")  # risk สูงขึ้นก่อน
    assert build_score_prompt("s", a_hi.attack)  # sanity: prompt สร้างได้
