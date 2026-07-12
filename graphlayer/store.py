"""Neo4j store — knowledge graph พร้อม provenance ทุก node/edge (NFR-08, D3)

provenance: ทุก entity/relation บันทึกไฟล์ต้นทาง + วันที่เอกสาร — จำเป็นต่อ
retrieval filter ของ hindcast (กรองตามวันที่ได้ทุก layer)
"""

from dataclasses import dataclass

from neo4j import GraphDatabase

from graphlayer.extraction import Extraction


@dataclass(frozen=True)
class IndirectPath:
    nodes: tuple[str, ...]
    relations: tuple[str, ...]


class Neo4jStore:
    def __init__(self, uri: str, user: str, password: str):
        self._driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self) -> None:
        self._driver.close()

    def verify(self) -> None:
        self._driver.verify_connectivity()

    def setup(self) -> None:
        with self._driver.session() as s:
            s.run(
                "CREATE CONSTRAINT entity_name IF NOT EXISTS "
                "FOR (e:Entity) REQUIRE e.name IS UNIQUE"
            )

    def upsert_extraction(self, ex: Extraction, *, source_doc: str, doc_date: str) -> None:
        with self._driver.session() as s:
            for e in ex.entities:
                s.run(
                    """MERGE (n:Entity {name: $name})
                       ON CREATE SET n.type = $type, n.sources = [$doc], n.doc_dates = [$date]
                       ON MATCH SET n.sources = CASE WHEN $doc IN n.sources THEN n.sources
                                                ELSE n.sources + $doc END,
                                    n.doc_dates = CASE WHEN $date IN n.doc_dates THEN n.doc_dates
                                                  ELSE n.doc_dates + $date END""",
                    name=e.name,
                    type=e.type,
                    doc=source_doc,
                    date=doc_date,
                )
            for r in ex.relations:
                s.run(
                    """MATCH (a:Entity {name: $src}), (b:Entity {name: $dst})
                       MERGE (a)-[rel:REL {type: $rel_type}]->(b)
                       SET rel.evidence = $evidence, rel.source_doc = $doc, rel.doc_date = $date""",
                    src=r.source,
                    dst=r.target,
                    rel_type=r.relation,
                    evidence=r.evidence,
                    doc=source_doc,
                    date=doc_date,
                )

    def query_indirect(self, a: str, b: str, max_hops: int = 3) -> IndirectPath | None:
        """หาความสัมพันธ์ทางอ้อมระหว่าง entity 2 ตัว (รากฐาน SIM-10 Impact Waterfall)"""
        query = (
            f"MATCH p = shortestPath((a:Entity {{name: $a}})"
            f"-[*..{int(max_hops)}]-(b:Entity {{name: $b}})) "
            "RETURN [n IN nodes(p) | n.name] AS names, [r IN relationships(p) | r.type] AS rels"
        )
        with self._driver.session() as s:
            record = s.run(query, a=a, b=b).single()
        if record is None:
            return None
        return IndirectPath(nodes=tuple(record["names"]), relations=tuple(record["rels"]))

    def neighbors(self, name: str) -> list[tuple[str, str]]:
        """คืน (relation, ชื่อ entity เพื่อนบ้าน) ของ entity หนึ่งตัว"""
        with self._driver.session() as s:
            result = s.run(
                "MATCH (a:Entity {name: $name})-[r:REL]-(b:Entity) "
                "RETURN r.type AS rel, b.name AS other",
                name=name,
            )
            return [(rec["rel"], rec["other"]) for rec in result]

    def graph_summary(self, limit: int = 150) -> dict:
        """P5-M6 — snapshot ของ graph สำหรับ visualization: nodes (top-degree) + edges ระหว่างกัน

        จำกัดที่ top-N ตาม degree เพื่อให้ render ได้จริง — provenance ต่อ node ยังย้อนได้
        ผ่าน sources (NFR-08)
        """
        with self._driver.session() as s:
            node_rows = s.run(
                "MATCH (e:Entity) OPTIONAL MATCH (e)-[r:REL]-() "
                "RETURN e.name AS name, e.type AS kind, count(r) AS degree, "
                "size(coalesce(e.sources, [])) AS sources "
                "ORDER BY degree DESC, name LIMIT $limit",
                limit=int(limit),
            )
            nodes = [
                {
                    "name": rec["name"],
                    "kind": rec["kind"] or "other",
                    "degree": int(rec["degree"]),
                    "sources": int(rec["sources"]),
                }
                for rec in node_rows
            ]
            names = [n["name"] for n in nodes]
            edge_rows = s.run(
                "MATCH (a:Entity)-[r:REL]->(b:Entity) "
                "WHERE a.name IN $names AND b.name IN $names "
                "RETURN a.name AS src, b.name AS dst, r.type AS relation LIMIT 500",
                names=names,
            )
            edges = [
                {"from": rec["src"], "to": rec["dst"], "relation": rec["relation"]}
                for rec in edge_rows
            ]
        return {"nodes": nodes, "edges": edges}

    def entity_count(self) -> int:
        with self._driver.session() as s:
            return s.run("MATCH (e:Entity) RETURN count(e) AS c").single()["c"]

    def delete_by_source_prefix(self, prefix: str) -> None:
        """ลบ node ที่มาจาก source ที่ขึ้นต้นด้วย prefix (ใช้เก็บกวาด test data)"""
        with self._driver.session() as s:
            s.run(
                "MATCH (e:Entity) WHERE any(src IN e.sources WHERE src STARTS WITH $p) "
                "DETACH DELETE e",
                p=prefix,
            )
