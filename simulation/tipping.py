"""Tipping point detection — PRD pipeline ขั้น 7 บังคับ: "Tipping Points ในทุกรายงาน"

นิยาม: round ที่สัดส่วนผู้เชื่อข้อความ (belief share) เปลี่ยน ≥ threshold ภายใน round เดียว
— เทียบเคียง SwarmSight ที่ใช้ Δavg stance ≥ 0.25 บนสเกล [-1,1] (= 12.5% ของช่วง);
ของเราใช้ belief share บนสเกล [0,1] จึงตั้ง default 0.15 — สูงกว่าอัตราแพร่ปกติ
(~5-8%/round ที่ calibration ปัจจุบัน) พอที่จะไม่จับการแพร่ธรรมดาเป็น tipping
แต่จับเหตุการณ์แบบ broadcast/คำชี้แจงทางการ (20%+/round) ได้

series สร้างจาก reasoning trail (NFR-08) — deterministic ต่อ seed เท่า engine เอง
"""

from dataclasses import dataclass

from simulation.engine import RunResult

DEFAULT_THRESHOLD = 0.15


@dataclass(frozen=True)
class TippingPoint:
    round_no: int
    before: float  # belief share ณ สิ้น round ก่อนหน้า
    after: float  # belief share ณ สิ้น round นี้
    delta: float

    def to_dict(self) -> dict:
        return {
            "round": self.round_no,
            "before": round(self.before, 4),
            "after": round(self.after, 4),
            "delta": round(self.delta, 4),
        }


def belief_series(result: RunResult, msg_id: str) -> list[float]:
    """สัดส่วนผู้เชื่อ msg_id ณ สิ้นสุดแต่ละ round — index 0 = สถานะ preseed, ยาว rounds+1

    เหตุการณ์ที่เปลี่ยนสถานะเชื่อใน trail:
    - believed / preseeded → เริ่มเชื่อ
    - revised:<msg_id> (belief revision จากข่าวหักล้าง) → เลิกเชื่อ
    """
    n = len(result.states) or 1
    events: dict[int, list[tuple[str, bool]]] = {}
    for e in result.trail:
        if e["msg"] == msg_id and e["action"] in ("believed", "preseeded"):
            events.setdefault(e["round"], []).append((e["agent"], True))
        elif e["action"] == f"revised:{msg_id}":
            events.setdefault(e["round"], []).append((e["agent"], False))
    believers: set[str] = set()
    series: list[float] = []
    for r in range(result.rounds + 1):
        for agent, on in events.get(r, ()):
            if on:
                believers.add(agent)
            else:
                believers.discard(agent)
        series.append(len(believers) / n)
    return series


def detect_tipping_points(
    series: list[float], *, threshold: float = DEFAULT_THRESHOLD
) -> list[TippingPoint]:
    """จุดที่ |Δ belief share| ระหว่าง round ติดกัน ≥ threshold (ทั้งพุ่งขึ้นและดิ่งลง)"""
    if not 0.0 < threshold <= 1.0:
        raise ValueError("threshold ต้องอยู่ในช่วง (0, 1]")
    points: list[TippingPoint] = []
    for i in range(1, len(series)):
        delta = series[i] - series[i - 1]
        if abs(delta) >= threshold:
            points.append(
                TippingPoint(round_no=i, before=series[i - 1], after=series[i], delta=delta)
            )
    return points


def tipping_from_run(
    result: RunResult, msg_id: str, *, threshold: float = DEFAULT_THRESHOLD
) -> list[TippingPoint]:
    return detect_tipping_points(belief_series(result, msg_id), threshold=threshold)
