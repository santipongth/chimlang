"""M2 — ingest corpus เข้า knowledge graph

uv run python scripts/ingest_corpus.py --corpus data/samples/corpus            # เต็ม
uv run python scripts/ingest_corpus.py --corpus data/samples/corpus --dry-run  # PII อย่างเดียว
"""

import argparse
from pathlib import Path

from core.config import get_settings
from core.llm import BudgetGuard, CostEstimator, LLMAdapter, PricingRegistry, TierLoad
from graphlayer.ingest import ingest_corpus
from graphlayer.store import Neo4jStore


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--dry-run", action="store_true", help="ตรวจ PII อย่างเดียว ไม่เรียก LLM")
    args = parser.parse_args()

    settings = get_settings()
    docs = [p for p in sorted(Path(args.corpus).glob("*.md")) if not p.name.startswith("README")]
    print(f"corpus: {args.corpus} | เอกสาร {len(docs)} ไฟล์ | dry_run={args.dry_run}")

    adapter = store = None
    guard = BudgetGuard(cap_usd=settings.run_budget_usd_cap)
    if not args.dry_run:
        pricing = PricingRegistry.from_yaml()
        estimate = CostEstimator(pricing).estimate(
            [
                TierLoad(
                    settings.llm_model_analyst,
                    calls=len(docs),
                    avg_input_tokens=4000,
                    avg_output_tokens=1500,
                )
            ]
        )
        guard.check_estimate(estimate)
        print(f"cost estimate: ${estimate.total_usd:.4f} (cap ${settings.run_budget_usd_cap:.2f})")
        adapter = LLMAdapter(settings, pricing, guard)
        store = Neo4jStore(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password)
        store.verify()
        store.setup()

    try:
        results = ingest_corpus(
            args.corpus,
            settings,
            adapter,
            store,
            dry_run=args.dry_run,
            on_progress=lambda r: print(
                f"  {r.status:<18} {r.doc}  ({r.entities}E/{r.relations}R) {r.detail[:60]}"
            ),
        )
    finally:
        if store:
            store.close()

    blocked = [r for r in results if r.status == "blocked_pii"]
    failed = [r for r in results if r.status == "failed_extraction"]
    ok = [r for r in results if r.status == "ingested"]
    print(
        f"\nสรุป: ingested {len(ok)} | blocked (PII) {len(blocked)} | extraction fail {len(failed)}"
    )
    if not args.dry_run:
        total_e = sum(r.entities for r in ok)
        total_r = sum(r.relations for r in ok)
        print(f"entities รวม {total_e} | relations รวม {total_r}")
        print(f"ใช้เงินจริง: ${guard.spent_usd:.4f}")


if __name__ == "__main__":
    main()
