"""Hub/cluster analysis สำหรับ graph viz (P5-M6) — pure function, test ได้โดยไม่ต้องมี Neo4j

Hub Nodes ตาม SIM-09: entity ที่ degree สูงสุด top 15% (ไม่เกิน 6 ตัว อย่างน้อย 1)
— นิยามเดียวกับที่ SwarmSight ใช้ ซึ่งอ่านง่ายบน viz จริง
"""

HUB_TOP_FRACTION = 0.15
HUB_MAX = 6


def compute_hubs(nodes: list[dict]) -> list[str]:
    """คืนชื่อ node ที่เป็น hub — nodes ต้องมี key name/degree"""
    if not nodes:
        return []
    ranked = sorted(nodes, key=lambda n: (-int(n["degree"]), n["name"]))
    k = max(1, min(HUB_MAX, round(len(ranked) * HUB_TOP_FRACTION)))
    return [n["name"] for n in ranked[:k] if int(n["degree"]) > 0][:HUB_MAX] or [ranked[0]["name"]]
