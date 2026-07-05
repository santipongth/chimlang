"""Influence Graph & Cluster Analysis (SIM-09) — ระดับ segment เท่านั้น (กฎเหล็กข้อ 7)

สร้าง influence matrix จาก reasoning trail: ทุกครั้งที่ agent ได้ยินข้อความ เครดิตอิทธิพล
ถูกกระจายให้ "segment ของผู้ที่กำลังแชร์อยู่ขณะนั้น" (น้ำหนักเฉลี่ย) — เป็นการประมาณ
ระดับกลุ่มโดยเจตนา ไม่สร้าง edge รายบุคคล และ output ไม่มี agent id เด็ดขาด
(ห้าม map ไปยังบุคคลจริง — บังคับด้วย test)

- Hub segments = กลุ่มที่ส่งอิทธิพลออกมากสุด (ผู้นำความคิดจำลองระดับกลุ่ม)
- Cluster pairs = คู่กลุ่มที่อิทธิพลไหลสองทางแรงสุด (การเกาะกลุ่มของ narrative)
"""

from collections import defaultdict
from dataclasses import dataclass

from simulation.engine import RunResult


@dataclass(frozen=True)
class InfluenceMatrix:
    # (from_segment, to_segment) -> น้ำหนักอิทธิพลสะสม — ระดับ segment เท่านั้น
    weights: dict[tuple[str, str], float]

    def out_weight(self, segment: str) -> float:
        return sum(w for (src, _), w in self.weights.items() if src == segment)


def build_influence(result: RunResult, msg_id: str) -> InfluenceMatrix:
    """ประมาณอิทธิพลระดับ segment จาก trail — deterministic เพราะ trail deterministic"""
    seg_of = {aid: st.persona.segment_name for aid, st in result.states.items()}
    sharing_since: dict[str, int] = {}  # agent -> round ที่เริ่มแชร์ msg นี้
    revised_at: dict[str, int] = {}
    for e in result.trail:
        if e["msg"] != msg_id:
            continue
        if e["action"] in ("shared", "seeded", "preseeded"):
            sharing_since.setdefault(e["agent"], e["round"])
        if e["action"].startswith("revised:") and e["action"] == f"revised:{msg_id}":
            revised_at[e["agent"]] = e["round"]

    weights: dict[tuple[str, str], float] = defaultdict(float)
    for e in result.trail:
        if e["msg"] != msg_id or e["action"] != "heard":
            continue
        r, listener = e["round"], e["agent"]
        sources = [
            a
            for a, since in sharing_since.items()
            if since < r and revised_at.get(a, 10**9) > r and a != listener
        ]
        if not sources:
            continue
        credit = 1.0 / len(sources)
        for src in sources:
            weights[(seg_of[src], seg_of[listener])] += credit
    return InfluenceMatrix(weights=dict(weights))


def hub_segments(matrix: InfluenceMatrix) -> list[tuple[str, float]]:
    segs = {src for src, _ in matrix.weights}
    return sorted(((s, matrix.out_weight(s)) for s in segs), key=lambda x: -x[1])


def cluster_pairs(matrix: InfluenceMatrix, *, top: int = 5) -> list[tuple[str, str, float]]:
    """คู่ segment ที่อิทธิพลไหลสองทางรวมแรงสุด (เรียงมาก→น้อย)"""
    seen: set[frozenset] = set()
    pairs = []
    for (a, b), w in matrix.weights.items():
        if a == b:
            continue
        key = frozenset((a, b))
        if key in seen:
            continue
        seen.add(key)
        both = w + matrix.weights.get((b, a), 0.0)
        pairs.append((a, b, both))
    return sorted(pairs, key=lambda x: -x[2])[:top]


def render_influence_section(matrix: InfluenceMatrix, mutation_share: float | None = None) -> str:
    hubs = hub_segments(matrix)
    lines = [
        "## Influence Graph (SIM-09) — ระดับ segment ในโลกจำลองเท่านั้น",
        "",
        "> ⚠️ ห้ามนำไป map หาบุคคลจริง (กฎเหล็กข้อ 7) — ตัวเลขคือน้ำหนักอิทธิพลจำลองระดับกลุ่ม",
        "",
        "### Hub segments (ผู้นำความคิดจำลอง — อิทธิพลขาออกสูงสุด)",
        "",
        "| กลุ่ม | อิทธิพลขาออก |",
        "|---|---|",
    ]
    lines += [f"| {seg} | {w:.2f} |" for seg, w in hubs]
    lines += ["", "### Cluster pairs (คู่กลุ่มที่ narrative ไหลถึงกันแรงสุด)", ""]
    for a, b, w in cluster_pairs(matrix):
        lines.append(f"- {a} ↔ {b}: {w:.2f}")
    if mutation_share is not None:
        lines += [
            "",
            f"### Rumor mutation (FAB-04): {mutation_share:.0%} ของผู้ได้ยินได้รับเวอร์ชันเพี้ยน "
            "(เกิดใน closed group — ตรวจสอบ/แก้ยากที่สุด)",
        ]
    return "\n".join(lines)
