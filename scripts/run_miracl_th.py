"""Run a pinned, governance-safe MIRACL Thai BM25 benchmark.

Raw remote bytes are hashed in flight and never persisted.  Every passage is
redacted and re-verified before the reusable sanitized cache is written.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import heapq
import json
import math
import re
import time
import zlib
from collections import defaultdict
from pathlib import Path

import httpx

from core.config import get_settings
from core.run_manifest import canonical_hash
from core.validation_store import ValidationStore
from governance.pii import PIIDetector, load_allowlist

DATA_REVISION = "5be20db9509754dadad47689368639fcec739c00"
CORPUS_REVISION = "d921ec7e349ce0d28daf30b2da9da5ee698bef0d"
LICENSE = "Apache-2.0"
BASE_DATA = f"https://huggingface.co/datasets/miracl/miracl/resolve/{DATA_REVISION}"
BASE_CORPUS = f"https://huggingface.co/datasets/miracl/miracl-corpus/resolve/{CORPUS_REVISION}"
TOPICS_URL = BASE_DATA + "/miracl-v1.0-th/topics/topics.miracl-v1.0-th-dev.tsv"
QRELS_URL = BASE_DATA + "/miracl-v1.0-th/qrels/qrels.miracl-v1.0-th-dev.tsv"
CORPUS_URLS = [
    BASE_CORPUS + "/miracl-corpus-v1.0-th/docs-0.jsonl.gz",
    BASE_CORPUS + "/miracl-corpus-v1.0-th/docs-1.jsonl.gz",
]


def _term_counts(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for term in (word.lower() for word in re.findall(r"[\w\u0E00-\u0E7F]{3,}", text)):
        counts[term] = counts.get(term, 0) + 1
    thai = re.sub(r"[^\u0E00-\u0E7F]", "", text)
    for index in range(max(0, len(thai) - 2)):
        term = thai[index : index + 3]
        counts[term] = counts.get(term, 0) + 1
    return counts


def _download_text(client: httpx.Client, url: str) -> tuple[str, str]:
    response = client.get(url)
    response.raise_for_status()
    payload = response.content
    return payload.decode("utf-8"), hashlib.sha256(payload).hexdigest()


def _sanitize_corpus(client: httpx.Client, url: str, target: Path) -> dict:
    detector = PIIDetector(load_allowlist())
    raw_hash = hashlib.sha256()
    redactions: dict[str, int] = defaultdict(int)
    passages = 0
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    pending = b""
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")

    def write_safe(line: bytes, output) -> None:
        nonlocal passages
        row = json.loads(line)
        title = detector.redact_and_verify(str(row.get("title") or ""))
        text = detector.redact_and_verify(str(row.get("text") or ""))
        for result in (title, text):
            for kind, count in result.counts.items():
                redactions[kind] += count
        safe = {"docid": str(row["docid"]), "title": title.text, "text": text.text}
        output.write(json.dumps(safe, ensure_ascii=False) + "\n")
        passages += 1

    with (
        client.stream("GET", url) as response,
        gzip.open(partial, "wt", encoding="utf-8") as output,
    ):
        response.raise_for_status()
        for chunk in response.iter_bytes():
            raw_hash.update(chunk)
            pending += decoder.decompress(chunk)
            while b"\n" in pending:
                line, pending = pending.split(b"\n", 1)
                if line.strip():
                    write_safe(line, output)
        pending += decoder.flush()
        if pending.strip():
            write_safe(pending, output)
    partial.replace(target)
    metadata = {
        "raw_sha256": raw_hash.hexdigest(),
        "passages": passages,
        "pii_redactions": dict(redactions),
    }
    target.with_suffix(target.suffix + ".metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return metadata


def _load_queries(raw: str, max_queries: int) -> tuple[dict[str, str], int]:
    all_queries = {}
    for line in raw.splitlines():
        query_id, query = line.split("\t", 1)
        all_queries[query_id] = query
    if max_queries <= 0 or max_queries >= len(all_queries):
        return all_queries, len(all_queries)
    ordered = list(all_queries.items())
    if max_queries == 1:
        return dict(ordered[:1]), len(all_queries)
    indexes = [
        round(index * (len(ordered) - 1) / (max_queries - 1)) for index in range(max_queries)
    ]
    return {ordered[index][0]: ordered[index][1] for index in indexes}, len(all_queries)


def _load_qrels(raw: str, query_ids: set[str]) -> dict[str, dict[str, int]]:
    qrels: dict[str, dict[str, int]] = defaultdict(dict)
    for line in raw.splitlines():
        fields = line.split()
        if len(fields) >= 4 and fields[0] in query_ids:
            qrels[fields[0]][fields[2]] = int(fields[3])
    return dict(qrels)


def _rank(caches: list[Path], queries: dict[str, str], *, top_k: int = 100) -> dict[str, list[str]]:
    query_terms = {query_id: set(_term_counts(text)) for query_id, text in queries.items()}
    vocabulary = set().union(*query_terms.values())
    document_frequency: dict[str, int] = defaultdict(int)
    document_count = 0
    total_length = 0
    for cache in caches:
        with gzip.open(cache, "rt", encoding="utf-8") as source:
            for line in source:
                row = json.loads(line)
                counts = _term_counts(str(row["title"]) + " " + str(row["text"]))
                document_count += 1
                total_length += sum(counts.values())
                for term in counts.keys() & vocabulary:
                    document_frequency[term] += 1
    if document_count == 0:
        raise RuntimeError("MIRACL corpus ว่าง")
    average_length = total_length / document_count
    inverse_document_frequency = {
        term: math.log(1 + (document_count - frequency + 0.5) / (frequency + 0.5))
        for term, frequency in document_frequency.items()
    }
    term_queries: dict[str, set[str]] = defaultdict(set)
    for query_id, terms in query_terms.items():
        for term in terms:
            term_queries[term].add(query_id)
    heaps: dict[str, list[tuple[float, str]]] = defaultdict(list)
    for cache in caches:
        with gzip.open(cache, "rt", encoding="utf-8") as source:
            for line in source:
                row = json.loads(line)
                docid = str(row["docid"])
                counts = _term_counts(str(row["title"]) + " " + str(row["text"]))
                length = sum(counts.values())
                scores: dict[str, float] = defaultdict(float)
                for term in counts.keys() & term_queries.keys():
                    frequency = counts[term]
                    denominator = frequency + 1.2 * (0.25 + 0.75 * length / average_length)
                    contribution = (
                        inverse_document_frequency.get(term, 0.0) * frequency * 2.2 / denominator
                    )
                    for query_id in term_queries[term]:
                        scores[query_id] += contribution
                for query_id, score in scores.items():
                    item = (score, docid)
                    if len(heaps[query_id]) < top_k:
                        heapq.heappush(heaps[query_id], item)
                    elif item > heaps[query_id][0]:
                        heapq.heapreplace(heaps[query_id], item)
    return {
        query_id: [docid for _, docid in sorted(heaps.get(query_id, []), reverse=True)]
        for query_id in queries
    }


def _metrics(
    rankings: dict[str, list[str]], qrels: dict[str, dict[str, int]]
) -> tuple[dict, list[dict]]:
    rows = []
    for query_id, ranking in rankings.items():
        judgments = qrels.get(query_id, {})
        relevant = {docid for docid, relevance in judgments.items() if relevance > 0}
        recall = sum(docid in relevant for docid in ranking[:100]) / max(1, len(relevant))
        reciprocal_rank = next(
            (1 / rank for rank, docid in enumerate(ranking[:10], 1) if docid in relevant), 0.0
        )
        gains = [
            (2 ** judgments.get(docid, 0) - 1) / math.log2(rank + 1)
            for rank, docid in enumerate(ranking[:10], 1)
        ]
        ideal = sorted((value for value in judgments.values() if value > 0), reverse=True)[:10]
        ideal_gain = sum(
            (2**value - 1) / math.log2(rank + 1) for rank, value in enumerate(ideal, 1)
        )
        rows.append(
            {
                "query_id": query_id,
                "relevant": len(relevant),
                "recall_at_100": recall,
                "mrr_at_10": reciprocal_rank,
                "ndcg_at_10": sum(gains) / ideal_gain if ideal_gain else 0.0,
            }
        )
    aggregate = {
        key: sum(row[key] for row in rows) / max(1, len(rows))
        for key in ("recall_at_100", "mrr_at_10", "ndcg_at_10")
    }
    aggregate["query_count"] = len(rows)
    return aggregate, rows


def _register_result(result: dict) -> tuple[str, str]:
    metadata = result["metadata"]
    complete = bool(metadata.get("benchmark_complete"))
    store = ValidationStore(get_settings().postgres_url)
    dataset_id = store.register_dataset(
        kind="miracl_th",
        name="MIRACL Thai dev",
        revision=DATA_REVISION,
        license_name=LICENSE,
        content_hash=canonical_hash(metadata),
        metadata=metadata,
        actor="miracl-runner",
    )
    report = store.register_report(
        dataset_id,
        kind="miracl_retrieval" if complete else "miracl_retrieval_incomplete",
        metrics=result["metrics"],
        raw_result_hash=result["raw_result_hash"],
        metadata=metadata,
        actor="miracl-runner",
    )
    return dataset_id, report["report_id"]


def run(*, workdir: Path, max_queries: int, register: bool) -> dict:
    started = time.perf_counter()
    workdir.mkdir(parents=True, exist_ok=True)
    caches = [
        workdir / f"miracl-th-{CORPUS_REVISION[:12]}-sanitized.jsonl.gz",
        workdir / f"miracl-th-{CORPUS_REVISION[:12]}-docs-1-sanitized.jsonl.gz",
    ]
    corpus_shards = []
    with httpx.Client(follow_redirects=True, timeout=httpx.Timeout(120, read=600)) as client:
        topics_raw, topics_hash = _download_text(client, TOPICS_URL)
        qrels_raw, qrels_hash = _download_text(client, QRELS_URL)
        for index, (url, cache) in enumerate(zip(CORPUS_URLS, caches, strict=True)):
            metadata_path = cache.with_suffix(cache.suffix + ".metadata.json")
            if cache.exists():
                if not metadata_path.exists():
                    raise RuntimeError("sanitized MIRACL cache ไม่มี provenance metadata")
                shard = json.loads(metadata_path.read_text(encoding="utf-8"))
                shard["cache_reused"] = True
            else:
                shard = _sanitize_corpus(client, url, cache)
            shard["shard"] = index
            corpus_shards.append(shard)
    queries, available_queries = _load_queries(topics_raw, max_queries)
    qrels = _load_qrels(qrels_raw, set(queries))
    ranking_started = time.perf_counter()
    rankings = _rank(caches, queries)
    metrics, per_query = _metrics(rankings, qrels)
    passage_count = sum(int(item["passages"]) for item in corpus_shards)
    benchmark_complete = passage_count == 542_166 and len(queries) == available_queries
    metadata = {
        "dataset_revision": DATA_REVISION,
        "corpus_revision": CORPUS_REVISION,
        "license": LICENSE,
        "topics_sha256": topics_hash,
        "qrels_sha256": qrels_hash,
        "corpus": {
            "shards": corpus_shards,
            "passages": passage_count,
            "expected_passages": 542_166,
        },
        "available_dev_queries": available_queries,
        "evaluation_scope": "full-dev"
        if len(queries) == available_queries
        else "stratified-dev-sample",
        "benchmark_complete": benchmark_complete,
        "retrieval_mode": "bm25-thai-trigram",
        "provider_cost_usd": 0.0,
        "ranking_latency_seconds": time.perf_counter() - ranking_started,
        "total_latency_seconds": time.perf_counter() - started,
    }
    result = {"metrics": metrics, "metadata": metadata, "per_query": per_query}
    raw_hash = canonical_hash(result)
    result["raw_result_hash"] = raw_hash
    output = workdir / f"miracl-th-{raw_hash[:12]}.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    result["output_path"] = str(output)
    if register:
        result["dataset_id"], result["report_id"] = _register_result(result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Pinned MIRACL Thai BM25 benchmark")
    parser.add_argument("--workdir", type=Path, default=Path(".tmp/miracl-th"))
    parser.add_argument(
        "--max-queries",
        type=int,
        default=0,
        help="0 evaluates all dev queries; positive values are an evenly spaced sample",
    )
    parser.add_argument(
        "--register", action="store_true", help="append dataset/report to Validation Lab"
    )
    parser.add_argument(
        "--register-output",
        type=Path,
        help="register a previously written raw result without ranking again",
    )
    args = parser.parse_args()
    if args.register_output:
        result = json.loads(args.register_output.read_text(encoding="utf-8"))
        result["dataset_id"], result["report_id"] = _register_result(result)
    else:
        result = run(workdir=args.workdir, max_queries=args.max_queries, register=args.register)
    summary = {key: value for key, value in result.items() if key != "per_query"}
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
