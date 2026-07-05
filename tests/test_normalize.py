from graphlayer.extraction import Entity, Extraction, Relation
from graphlayer.normalize import canonical_name, normalize_extraction


def test_alias_merging():
    assert canonical_name("กรุงเทพมหานคร") == "กทม."
    assert canonical_name("  กรุงเทพฯ ") == "กทม."
    assert canonical_name("กลุ่มไรเดอร์") == "กลุ่มไรเดอร์"  # ไม่มี alias = คงเดิม


def test_normalize_merges_duplicate_entities_and_drops_self_loops():
    ex = Extraction(
        entities=(
            Entity("กทม.", "องค์กร"),
            Entity("กรุงเทพมหานคร", "องค์กร"),
            Entity("กลุ่มไรเดอร์", "กลุ่มผู้มีส่วนได้เสีย"),
        ),
        relations=(
            # หลัง merge กลายเป็น self-loop → ต้องถูกตัดทิ้ง
            Relation("กทม.", "คือ", "กรุงเทพมหานคร", "-"),
            Relation("กรุงเทพมหานคร", "รับฟัง", "กลุ่มไรเดอร์", "-"),
        ),
    )
    out = normalize_extraction(ex)
    assert {e.name for e in out.entities} == {"กทม.", "กลุ่มไรเดอร์"}
    assert len(out.relations) == 1
    assert out.relations[0].source == "กทม."  # alias ใน relation ถูกแปลงด้วย
