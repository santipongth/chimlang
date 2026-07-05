"""Impact Waterfall (SIM-10) — ไล่ผลกระทบลำดับ 2-3 ผ่าน knowledge graph

จาก entity ต้นทาง (เช่น นโยบาย) ใช้ Neo4j หา stakeholder ที่ถูกกระทบทางอ้อม
พร้อมเส้นทางความสัมพันธ์เต็ม (ทุก hop ย้อนถึงไฟล์ต้นทางได้ตาม provenance ใน graph)
"""

from dataclasses import dataclass

from graphlayer.store import Neo4jStore


@dataclass(frozen=True)
class ImpactRow:
    target: str
    hops: int
    path: tuple[str, ...]  # ชื่อ entity ตามเส้นทาง
    relations: tuple[str, ...]


def impact_waterfall(store: Neo4jStore, source: str, *, max_hops: int = 3) -> list[ImpactRow]:
    """entity ที่ห่างจาก source 2-3 hops (ผลกระทบทางอ้อม) เรียงตามระยะใกล้→ไกล"""
    # shortestPath ไม่รองรับ min length ≥ 2 (บทเรียน M2) — ใช้ plain match แล้วเลือก path สั้นสุดต่อ b
    query = (
        f"MATCH p = (a:Entity {{name: $source}})-[*2..{int(max_hops)}]-(b:Entity) "
        "WHERE a <> b AND NOT (a)-[]-(b) "
        "WITH b, p ORDER BY length(p) "
        "WITH b, collect(p)[0] AS sp "
        "RETURN b.name AS target, length(sp) AS hops, "
        "[n IN nodes(sp) | n.name] AS names, [r IN relationships(sp) | r.type] AS rels "
        "ORDER BY hops, target LIMIT 30"
    )
    with store._driver.session() as s:
        records = s.run(query, source=source).data()
    return [
        ImpactRow(
            target=r["target"],
            hops=int(r["hops"]),
            path=tuple(r["names"]),
            relations=tuple(r["rels"]),
        )
        for r in records
    ]


def render_waterfall(source: str, rows: list[ImpactRow]) -> str:
    lines = [
        f"## Impact Waterfall (SIM-10): ผลกระทบทางอ้อมจาก «{source}»",
        "",
        "> ลำดับ 2-3 hop จาก knowledge graph — ทุกเส้นทางย้อนถึงเอกสารต้นทางได้ (provenance)",
        "",
    ]
    if not rows:
        lines.append("(ไม่พบผลกระทบทางอ้อมในระยะ 2-3 hop)")
        return "\n".join(lines)
    by_hops: dict[int, list[ImpactRow]] = {}
    for r in rows:
        by_hops.setdefault(r.hops, []).append(r)
    for hops in sorted(by_hops):
        lines.append(f"### ลำดับที่ {hops} ({len(by_hops[hops])} ราย)")
        for r in by_hops[hops][:8]:
            arrow = " → ".join(r.path)
            lines.append(f"- **{r.target}** — เส้นทาง: {arrow}")
        lines.append("")
    return "\n".join(lines)
