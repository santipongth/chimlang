"""Citizen Mode (CIT-01..04) — Personal Impact Twin + Portal + Feedback Loop

หลักความเป็นส่วนตัว (NFR-04, เข้มกว่า GOV-01):
- CIT-01: อินพุตเป็น **ตัวเลือกปิด (categorical) เท่านั้น ≤ 10 ฟิลด์** — ไม่มี free text
  = ไม่มีช่องให้ PII เล็ดลอดโดยโครงสร้าง; ประมวลผลแบบ session-only ห้าม persist อินพุตดิบ
- CIT-03: feedback เก็บเป็น (segment, stance) เท่านั้น และปล่อย aggregate เมื่อ
  กลุ่มมีอย่างน้อย k=20 คน (k-anonymity) — ต่ำกว่านั้นถูกกักไว้
- CIT-04: ทุก output มี disclaimer ถาวร (ค่าคงที่เดียว ห้ามลบ)
"""

from dataclasses import dataclass

import psycopg

from simulation.persona import PersonaFactory

CITIZEN_DISCLAIMER = (
    "ผลนี้เป็นการจำลองด้วย AI (simulation_estimate) ไม่ใช่โพลจริง "
    "ไม่ใช่คำสัญญาของหน่วยงานรัฐ และอาจต่างจากผลจริง — ใช้เพื่อความเข้าใจเบื้องต้นเท่านั้น"
)

K_ANONYMITY = 20  # CIT-03: ปล่อย aggregate เมื่อ n ≥ 20 เท่านั้น

INCOME_BANDS = ("ต่ำกว่า 15k", "15k-30k", "30k-60k", "60k ขึ้นไป")
REGIONS = ("ในเมืองชั้นใน", "แนวรถไฟฟ้า", "ชานเมือง", "นอกแนวขนส่งสาธารณะ")
COMMUTES = ("รถไฟฟ้า/รถเมล์", "รถยนต์ส่วนตัว", "มอเตอร์ไซค์", "เดิน/ใกล้ที่ทำงาน")
OCCUPATIONS = ("พนักงานออฟฟิศ", "ค้าขาย/กิจการเล็ก", "ไรเดอร์/ขนส่ง", "เกษียณ/ดูแลบ้าน", "นักเรียนนักศึกษา")
AGE_BANDS = ("18-30", "31-45", "46-60", "60 ขึ้นไป")
STANCES = ("เห็นด้วย", "ไม่เห็นด้วย", "กังวลแต่ยังไม่ตัดสินใจ")


class InvalidCitizenInputError(ValueError):
    pass


@dataclass(frozen=True)
class CitizenInputs:
    """≤ 10 ฟิลด์ ตัวเลือกปิดทั้งหมด (CIT-01) — ไม่มี free text โดยเจตนา"""

    income_band: str
    region: str
    commute: str
    occupation: str
    age_band: str
    household_size: int  # 1-10

    def __post_init__(self):
        checks = [
            (self.income_band, INCOME_BANDS, "income_band"),
            (self.region, REGIONS, "region"),
            (self.commute, COMMUTES, "commute"),
            (self.occupation, OCCUPATIONS, "occupation"),
            (self.age_band, AGE_BANDS, "age_band"),
        ]
        for value, allowed, field_name in checks:
            if value not in allowed:
                raise InvalidCitizenInputError(f"{field_name} ต้องเป็นหนึ่งใน {allowed}")
        if not 1 <= self.household_size <= 10:
            raise InvalidCitizenInputError("household_size ต้องอยู่ระหว่าง 1-10")


def match_segment(inputs: CitizenInputs, factory: PersonaFactory) -> str:
    """จับคู่ครัวเรือน → segment id ด้วยกติกาโปร่งใส (อธิบายได้ ไม่ใช่ black box)"""
    if inputs.occupation == "ไรเดอร์/ขนส่ง":
        sid = "gig_transport_workers"
    elif inputs.occupation == "ค้าขาย/กิจการเล็ก":
        sid = "small_business"
    elif inputs.age_band == "60 ขึ้นไป" or inputs.occupation == "เกษียณ/ดูแลบ้าน":
        sid = "elderly_community"
    elif inputs.region == "นอกแนวขนส่งสาธารณะ":
        sid = "suburban_no_transit"
    elif inputs.region == "ชานเมือง":
        sid = "working_commuter"
    elif inputs.region == "แนวรถไฟฟ้า" and inputs.occupation == "พนักงานออฟฟิศ":
        sid = "office_inner_city"
    elif inputs.age_band == "18-30":
        sid = "young_urban"
    else:
        sid = "office_inner_city" if inputs.commute == "รถไฟฟ้า/รถเมล์" else "working_commuter"
    known = {s["id"] for s in factory.segments}
    return sid if sid in known else "working_commuter"


@dataclass(frozen=True)
class ImpactTwin:
    """ผลลัพธ์ CIT-01 — ระดับ segment + ช่วงความไม่แน่นอนเสมอ (TRUST-09)"""

    segment_id: str
    segment_name: str
    concern_baseline: tuple[float, float]  # ช่วงสัดส่วนกลุ่มนี้ที่กังวล (ไม่มีมาตรการสื่อสาร)
    concern_after_response: tuple[float, float]  # ช่วงหลังมีคำชี้แจง
    note: str

    def to_dict(self) -> dict:
        return {
            "segment": self.segment_name,
            "concern_baseline_range": [round(x, 3) for x in self.concern_baseline],
            "concern_after_response_range": [round(x, 3) for x in self.concern_after_response],
            "note": self.note,
            "disclaimer": CITIZEN_DISCLAIMER,  # CIT-04: ถาวร
        }


def build_impact_twin(
    inputs: CitizenInputs,
    factory: PersonaFactory,
    *,
    agents: int = 100,
    max_agents: int,
    seed: int,
    rounds: int = 20,
) -> ImpactTwin:
    """CIT-01 — จำลองผลกระทบระดับ segment (ช่วงจากหลาย seed) — session-only ไม่บันทึกอินพุต"""
    from simulation.engine import Message
    from simulation.experiment import run_whatif

    sid = match_segment(inputs, factory)
    seg_name = next(s["name"] for s in factory.segments if s["id"] == sid)
    _estimate, outcomes = run_whatif(
        lambda s: factory.sample(agents, seed=s, max_agents=max_agents),
        seeds=[seed + i for i in range(8)],
        rounds=rounds,
        base_messages=[
            Message("rumor", "rumor", "ข่าวลือ: จะเก็บค่าธรรมเนียมมอเตอร์ไซค์ทุกคัน", 1, "public_feed")
        ],
        event=Message(
            "official",
            "correction",
            "หน่วยงานชี้แจง: ยกเว้นมอเตอร์ไซค์และรถขนส่งสาธารณะ",
            8,
            "public_feed",
            counters="rumor",
        ),
        target_msg_id="rumor",
    )

    def seg_rate(result) -> float:
        members = [st for st in result.states.values() if st.persona.segment_id == sid]
        if not members:
            return 0.0
        return sum(1 for st in members if st.believed.get("rumor")) / len(members)

    base_rates = [seg_rate(o.baseline) for o in outcomes]
    resp_rates = [seg_rate(o.variant) for o in outcomes]
    n_members = sum(
        1 for st in outcomes[0].baseline.states.values() if st.persona.segment_id == sid
    )
    return ImpactTwin(
        segment_id=sid,
        segment_name=seg_name,
        concern_baseline=(min(base_rates), max(base_rates)),
        concern_after_response=(min(resp_rates), max(resp_rates)),
        note=(
            f"จำลองจากตัวแทนกลุ่มนี้ {n_members} ตัวใน population {agents} — "
            "ช่วงกว้าง = ความไม่แน่นอนจริง อย่าอ่านเป็นตัวเลขแม่นยำ"
        ),
    )


class FeedbackPool:
    """CIT-03 — เก็บเฉพาะ (segment, stance); ปล่อย aggregate เมื่อ n ≥ k เท่านั้น"""

    def __init__(self, dsn: str):
        self._dsn = dsn

    def _conn(self):
        return psycopg.connect(self._dsn)

    def setup(self) -> None:
        with self._conn() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS citizen_feedback ("
                "id BIGSERIAL PRIMARY KEY, ts TIMESTAMPTZ NOT NULL DEFAULT now(), "
                "segment_id TEXT NOT NULL, stance TEXT NOT NULL)"
            )

    def add(self, segment_id: str, stance: str) -> None:
        if stance not in STANCES:
            raise InvalidCitizenInputError(f"stance ต้องเป็นหนึ่งใน {STANCES}")
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO citizen_feedback (segment_id, stance) VALUES (%s, %s)",
                (segment_id, stance),
            )

    def aggregates(self) -> list[dict]:
        """เฉพาะ segment ที่มีเสียง ≥ k=20 — ต่ำกว่านั้นถูกกักเพื่อกันระบุตัวตน"""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT segment_id, stance, count(*) FROM citizen_feedback "
                "GROUP BY segment_id, stance"
            ).fetchall()
        totals: dict[str, int] = {}
        for seg, _stance, cnt in rows:
            totals[seg] = totals.get(seg, 0) + cnt
        released = []
        for seg, stance, cnt in rows:
            if totals[seg] >= K_ANONYMITY:
                released.append(
                    {"segment_id": seg, "stance": stance, "count": cnt, "n_total": totals[seg]}
                )
        return sorted(released, key=lambda r: (r["segment_id"], r["stance"]))

    def withheld_segments(self) -> list[str]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT segment_id, count(*) FROM citizen_feedback GROUP BY segment_id"
            ).fetchall()
        return sorted(seg for seg, cnt in rows if cnt < K_ANONYMITY)


@dataclass(frozen=True)
class FeedbackEffect:
    """CIT-03 ครึ่งหลัง — เสียงจริงเปลี่ยนผลจำลองอย่างไร (แสดงต่อสาธารณะ)"""

    disagree_share: float  # สัดส่วนเสียงไม่เห็นด้วย/กังวล จาก aggregate ที่ปล่อยแล้ว
    concern_without_feedback: tuple[float, float]
    concern_with_feedback: tuple[float, float]


def disagree_share_from(aggregates: list[dict]) -> float | None:
    """สัดส่วนเสียง 'ไม่เห็นด้วย' + 'กังวล' จาก aggregate ที่ผ่าน k-anonymity แล้วเท่านั้น"""
    total = sum(a["count"] for a in aggregates)
    if total == 0:
        return None
    negative = sum(a["count"] for a in aggregates if a["stance"] != "เห็นด้วย")
    return negative / total


def apply_feedback_round(
    aggregates: list[dict],
    factory: PersonaFactory,
    *,
    agents: int = 100,
    max_agents: int,
    seed: int,
    rounds: int = 20,
) -> FeedbackEffect | None:
    """รัน sim คู่ (ไม่มี/มีเสียงจริงเป็น prior) — เสียงจริง preseed ระดับความกังวลตั้งต้น

    คืน None ถ้ายังไม่มี aggregate ที่ผ่าน k-anonymity (ไม่มีเสียงจริงให้ inject)
    """
    from simulation.engine import FabricSimulation, Message
    from simulation.warroom import _preseed_believers

    share = disagree_share_from(aggregates)
    if share is None:
        return None
    rumor_text = "ข่าวลือ: จะเก็บค่าธรรมเนียมมอเตอร์ไซค์ทุกคัน"

    def concern_range(with_prior: bool) -> tuple[float, float]:
        rates = []
        for s in range(4):
            personas = factory.sample(agents, seed=seed + s, max_agents=max_agents)
            sim = FabricSimulation(personas, seed=seed + s)
            if with_prior:
                sim.preseed(
                    Message("rumor", "rumor", rumor_text, 0, "public_feed"),
                    _preseed_believers(personas, share),
                )
            else:
                sim.inject(Message("rumor", "rumor", rumor_text, 1, "public_feed"))
            result = sim.run(rounds)
            rates.append(
                sum(1 for st in result.states.values() if st.believed.get("rumor"))
                / len(result.states)
            )
        return (min(rates), max(rates))

    return FeedbackEffect(
        disagree_share=share,
        concern_without_feedback=concern_range(False),
        concern_with_feedback=concern_range(True),
    )


def inject_feedback_to_memory(aggregates: list[dict], memory, workspace: str) -> int:
    """บันทึก aggregate (ที่ผ่าน k-anonymity แล้วเท่านั้น) เข้า Living Memory เป็นเหตุการณ์จริง"""
    written = 0
    for a in aggregates:
        memory.remember(
            workspace,
            "real_event",
            f"เสียงประชาชน (aggregate ≥{K_ANONYMITY} คน) กลุ่ม {a['segment_id']}: "
            f"{a['stance']} {a['count']}/{a['n_total']}",
        )
        written += 1
    return written


def render_citizen_portal(
    title: str,
    twin: ImpactTwin,
    aggregates: list[dict],
    effect: "FeedbackEffect | None" = None,
) -> str:
    """CIT-02 — หน้า portal ฉบับประชาชน: ภาษาง่าย + ช่วงความไม่แน่นอน + disclaimer ถาวร"""
    b_lo, b_hi = twin.concern_baseline
    a_lo, a_hi = twin.concern_after_response
    lines = [
        f"# {title} — ฉบับประชาชน",
        "",
        f"> ⚠️ {CITIZEN_DISCLAIMER}",
        "",
        f"## ครัวเรือนแบบคุณ (กลุ่ม: {twin.segment_name})",
        "",
        f"- ถ้า**ไม่มี**คำชี้แจงเพิ่ม: คนกลุ่มเดียวกับคุณราว **{b_lo:.0%}–{b_hi:.0%}** กังวลเรื่องนี้",
        f"- ถ้า**มี**คำชี้แจงจากหน่วยงาน: ความกังวลลดเหลือราว **{a_lo:.0%}–{a_hi:.0%}**",
        f"- {twin.note}",
        "",
        'ตัวเลขเป็น "ช่วง" เพราะการจำลองมีความไม่แน่นอนจริง — เราไม่แสดงตัวเลขเดี่ยวที่ดูแม่นเกินจริง',
        "",
        "## เสียงจริงจากประชาชน (เฉพาะกลุ่มที่มีผู้ตอบ ≥ 20 คน เพื่อคุ้มครองตัวตน)",
        "",
    ]
    if aggregates:
        lines += ["| กลุ่ม | ความเห็น | จำนวน |", "|---|---|---|"]
        lines += [
            f"| {a['segment_id']} | {a['stance']} | {a['count']}/{a['n_total']} |"
            for a in aggregates
        ]
    else:
        lines.append("_ยังไม่มีกลุ่มใดถึงเกณฑ์ 20 เสียง — ความเห็นถูกเก็บไว้อย่างปลอดภัยจนกว่าจะถึงเกณฑ์_")
    if effect is not None:
        wo_lo, wo_hi = effect.concern_without_feedback
        w_lo, w_hi = effect.concern_with_feedback
        lines += [
            "",
            "## เสียงจริงเปลี่ยนผลจำลองอย่างไร (CIT-03)",
            "",
            f"- เสียงไม่เห็นด้วย/กังวลจากประชาชนจริง: **{effect.disagree_share:.0%}** "
            "→ ถูกป้อนเป็นจุดตั้งต้นของการจำลองรอบใหม่",
            f"- ผลจำลอง**ก่อน**รับเสียงจริง: กังวล {wo_lo:.0%}–{wo_hi:.0%}",
            f"- ผลจำลอง**หลัง**รับเสียงจริง: กังวล {w_lo:.0%}–{w_hi:.0%}",
            "- ความโปร่งใส: เราแสดงทั้งสองตัวเลขเสมอ เพื่อให้เห็นว่าเสียงของคุณมีผลจริงต่อแบบจำลอง",
        ]
    lines += ["", f"> ⚠️ {CITIZEN_DISCLAIMER}"]  # ปิดท้ายซ้ำ — ถาวรจริง (CIT-04)
    return "\n".join(lines)
