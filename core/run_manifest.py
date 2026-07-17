"""Immutable run specification and manifest contracts (ADR-0014)."""

from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from core.db import connection

REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_SPEC_VERSION = 1
RUN_MANIFEST_VERSION = 1


def canonical_json(value: Any) -> str:
    """Return stable UTF-8 JSON used by every manifest hash."""
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        default=str,
    )


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _snapshot(value: Any) -> Any:
    """Detach caller-owned mutable values through canonical JSON."""
    return json.loads(canonical_json(value))


class RunSpecV1(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = RUN_SPEC_VERSION
    request: dict[str, Any]
    seed: int
    population_snapshot: dict[str, Any]
    input_mode: Literal["latest", "frozen"] = "latest"
    source_run_id: str = ""


class RunManifestV1(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = RUN_MANIFEST_VERSION
    run_id: str
    status: str
    complete: bool
    incomplete_reasons: list[str]
    reproducibility: Literal["frozen-inputs-best-effort", "incomplete"]
    determinism: Literal["provider-best-effort"] = "provider-best-effort"
    spec: RunSpecV1
    versions: dict[str, Any]
    pricing: dict[str, Any]
    governance: dict[str, Any]
    snapshots: dict[str, Any]
    artifact_hashes: dict[str, str]
    config_hash: str
    manifest_hash: str


def normalize_run_request(
    raw: dict[str, Any],
    *,
    agents: int,
    rounds: int,
    seed: int,
) -> dict[str, Any]:
    """Normalize the accepted request, including defaults and clamped values."""
    sources = []
    for source in raw.get("sources") or []:
        sources.append(
            {
                "kind": str(source.get("kind", "text")).strip(),
                "label": str(source.get("label", "")).strip(),
                "url": str(source.get("url", "") or "").strip(),
                "text": str(source.get("text", "") or ""),
            }
        )
    views = sorted(
        {
            str(view)
            for view in (raw.get("views") or [])
            if str(view) in {"overview", "debate", "canvas", "evidence"}
        }
    )
    return {
        "engine": str(raw.get("engine", "fabric")),
        "subject": str(raw.get("subject", "")).strip(),
        "domain": str(raw.get("domain", "ทั่วไป")).strip() or "ทั่วไป",
        "agents": int(agents),
        "requested_agents": int(raw.get("agents") or agents),
        "rounds": int(rounds),
        "pack_id": raw.get("pack_id"),
        "red_team": bool(raw.get("red_team")),
        "sources": sources,
        "claim": str(raw.get("claim", "")).strip(),
        "measurement": str(raw.get("measurement", "")).strip(),
        "due_days": int(raw.get("due_days") or 30),
        "probability": raw.get("probability"),
        "seed": int(seed),
        "views": views or ["canvas", "debate", "evidence", "overview"],
        "live_news": bool(raw.get("live_news")),
        "retrieval_mode": str(raw.get("retrieval_mode", "hybrid")),
        "parent_run_id": str(raw.get("parent_run_id", "") or ""),
        "reflection": bool(raw.get("reflection")),
        "experiment_id": str(raw.get("experiment_id", "") or ""),
        "project_id": str(raw.get("project_id", "") or ""),
        "evidence_set_id": str(raw.get("evidence_set_id", "") or ""),
    }


def build_run_spec(
    request: dict[str, Any],
    *,
    seed: int,
    population_segments: list[dict[str, Any]],
    input_mode: Literal["latest", "frozen"] = "latest",
    source_run_id: str = "",
) -> RunSpecV1:
    return RunSpecV1(
        request=_snapshot(request),
        seed=seed,
        population_snapshot={
            "kind": "persona-segments-v1",
            "segments": _snapshot(population_segments),
            "segments_hash": canonical_hash(population_segments),
        },
        input_mode=input_mode,
        source_run_id=source_run_id,
    )


def request_hash(spec: RunSpecV1) -> str:
    """Hash request semantics for Idempotency-Key conflict detection."""
    return canonical_hash(
        {
            "request": spec.request,
            "seed": spec.seed,
            "population_snapshot": spec.population_snapshot,
            "input_mode": spec.input_mode,
            "source_run_id": spec.source_run_id,
        }
    )


def _file_hash(relative: str) -> str:
    path = REPO_ROOT / relative
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return "unavailable"


def _git_version() -> str:
    configured = os.getenv("CHIMLANG_GIT_SHA", "").strip()
    if configured:
        return configured
    head = REPO_ROOT / ".git" / "HEAD"
    try:
        ref = head.read_text(encoding="utf-8").strip()
        if ref.startswith("ref: "):
            return (REPO_ROOT / ".git" / ref[5:]).read_text(encoding="utf-8").strip()
        return ref
    except OSError:
        return "unknown"


def version_snapshot(engine: str) -> dict[str, Any]:
    engine_files = (
        ["simulation/engine.py", "simulation/experiment.py", "trust/universe.py"]
        if engine == "fabric"
        else [
            "simulation/debate.py",
            "simulation/debate_protocol.py",
            "simulation/reflection.py",
        ]
    )
    return {
        "git": _git_version(),
        "engine": {
            "name": engine,
            "contract": "chimlang-engine-v1",
            "files": {name: _file_hash(name) for name in engine_files},
        },
        "adapter": {
            "contract": "core-llm-adapter-v1",
            "source_hash": _file_hash("core/llm/adapter.py"),
        },
        "prompts": {
            "contract": "thai-only-governed-prompts-v1",
            "source_hash": _file_hash("simulation/debate.py")
            if engine == "debate"
            else _file_hash("simulation/engine.py"),
        },
    }


def model_and_pricing_snapshot(engine: str) -> tuple[dict[str, Any], dict[str, Any]]:
    if engine != "debate":
        return {"provider": "none", "models": {}}, {}
    from core.llm.userconfig import effective_llm_settings, effective_pricing

    settings = effective_llm_settings()
    registry = effective_pricing()
    models = {
        "crowd": settings.llm_model_crowd,
        "analyst": settings.llm_model_analyst,
        "embedding": settings.llm_model_embedding,
    }
    prices: dict[str, Any] = {}
    for tier, model in models.items():
        if not model:
            continue
        price = registry.get(model)
        prices[tier] = {
            "model": model,
            "input_usd_per_m": price.input_usd_per_m,
            "output_usd_per_m": price.output_usd_per_m,
        }
    return {
        "base_url": settings.llm_base_url,
        "models": models,
        "embedding_dimension": settings.llm_embedding_dimension,
        "run_budget_usd_cap": settings.run_budget_usd_cap,
    }, prices


def capture_run_snapshots(dsn: str, run_id: str, detail: dict[str, Any]) -> dict[str, Any]:
    """Capture stored evidence/news/posts without network or LLM I/O."""
    with connection(dsn) as conn:
        chunks = conn.execute(
            "SELECT source_label, seq, content FROM run_chunks "
            "WHERE run_id = %s ORDER BY source_label, seq",
            (run_id,),
        ).fetchall()
        news = conn.execute(
            "SELECT provider, query, url, title, content, fetched_at::text, channel_tags, "
            "status, error, pii_redactions FROM news_items WHERE run_id = %s ORDER BY id",
            (run_id,),
        ).fetchall()
    evidence_snapshot = [
        {"source_label": row[0], "seq": row[1], "content": row[2]} for row in chunks
    ]
    news_snapshot = [
        {
            "provider": row[0],
            "query": row[1],
            "url": row[2],
            "title": row[3],
            "content": row[4],
            "fetched_at": row[5],
            "channel_tags": row[6],
            "status": row[7],
            "error": row[8],
            "pii_redactions": row[9],
        }
        for row in news
    ]
    if not news_snapshot:
        news_snapshot = _snapshot(
            ((detail.get("payload") or {}).get("news") or {}).get("items") or []
        )
    return {
        "evidence": evidence_snapshot,
        "news": news_snapshot,
        "posts": _snapshot(detail.get("posts") or []),
        "result": _snapshot(detail.get("payload") or {}),
    }


def build_manifest(
    *,
    run_id: str,
    status: str,
    spec: RunSpecV1,
    versions: dict[str, Any],
    pricing: dict[str, Any],
    governance: dict[str, Any],
    snapshots: dict[str, Any],
) -> RunManifestV1:
    versions = _snapshot(versions)
    pricing = _snapshot(pricing)
    governance = _snapshot(governance)
    snapshots = _snapshot(snapshots)
    artifacts = {
        "spec": canonical_hash(spec),
        "population": canonical_hash(spec.population_snapshot),
        "evidence": canonical_hash(snapshots.get("evidence") or []),
        "news": canonical_hash(snapshots.get("news") or []),
        "posts": canonical_hash(snapshots.get("posts") or []),
        "result": canonical_hash(snapshots.get("result") or {}),
    }
    config_basis = {
        "spec": spec.model_dump(mode="json"),
        "versions": versions,
        "pricing": pricing,
        "governance": governance,
    }
    config_hash = canonical_hash(config_basis)
    incomplete_reasons: list[str] = []
    if status != "complete":
        incomplete_reasons.append(f"terminal-status:{status}")
    if not spec.request.get("subject") or not spec.request.get("engine"):
        incomplete_reasons.append("normalized-request-missing")
    if not spec.population_snapshot.get("segments"):
        incomplete_reasons.append("population-snapshot-missing")
    git_version = str(versions.get("git") or "")
    if git_version in {"", "unknown", "unavailable"}:
        incomplete_reasons.append("git-version-missing")
    for component in ("engine", "adapter", "prompts", "model"):
        if not versions.get(component):
            incomplete_reasons.append(f"{component}-version-missing")
    version_hashes = [
        *(versions.get("engine", {}).get("files", {}) or {}).values(),
        versions.get("adapter", {}).get("source_hash", ""),
        versions.get("prompts", {}).get("source_hash", ""),
    ]
    if any(value in {"", "unknown", "unavailable"} for value in version_hashes):
        incomplete_reasons.append("code-artifact-hash-missing")
    if governance.get("pii_detector") != "passed":
        incomplete_reasons.append("governance-decision-missing")
    if not snapshots.get("result"):
        incomplete_reasons.append("result-snapshot-missing")
    if spec.request.get("engine") == "debate":
        model_names = versions.get("model", {}).get("models", {}) or {}
        if not model_names.get("crowd") or not model_names.get("analyst"):
            incomplete_reasons.append("debate-model-config-missing")
        if not pricing.get("crowd") or not pricing.get("analyst"):
            incomplete_reasons.append("debate-pricing-missing")
    complete = not incomplete_reasons
    base = {
        "schema_version": RUN_MANIFEST_VERSION,
        "run_id": run_id,
        "status": status,
        "complete": complete,
        "incomplete_reasons": incomplete_reasons,
        "reproducibility": "frozen-inputs-best-effort" if complete else "incomplete",
        "determinism": "provider-best-effort",
        "spec": spec.model_dump(mode="json"),
        "versions": versions,
        "pricing": pricing,
        "governance": governance,
        "snapshots": snapshots,
        "artifact_hashes": artifacts,
        "config_hash": config_hash,
    }
    return RunManifestV1(**base, manifest_hash=canonical_hash(base))


class RunManifestStore:
    def __init__(self, dsn: str):
        self._dsn = dsn

    def insert(self, manifest: RunManifestV1) -> bool:
        with connection(self._dsn) as conn:
            row = conn.execute(
                "INSERT INTO run_manifests "
                "(run_id, schema_version, complete, config_hash, manifest_hash, "
                "reproducibility, spec, manifest) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb) "
                "ON CONFLICT (run_id) DO NOTHING RETURNING run_id",
                (
                    manifest.run_id,
                    manifest.schema_version,
                    manifest.complete,
                    manifest.config_hash,
                    manifest.manifest_hash,
                    manifest.reproducibility,
                    canonical_json(manifest.spec),
                    canonical_json(manifest),
                ),
            ).fetchone()
        return row is not None

    def get(self, run_id: str) -> dict[str, Any]:
        with connection(self._dsn) as conn:
            row = conn.execute(
                "SELECT created_at, schema_version, complete, config_hash, manifest_hash, "
                "reproducibility, manifest FROM run_manifests WHERE run_id = %s",
                (run_id,),
            ).fetchone()
        if row is None:
            raise ValueError(f"ไม่พบ manifest ของ run {run_id}")
        manifest = dict(row[6])
        manifest.setdefault("run_id", run_id)
        manifest.setdefault("schema_version", row[1])
        manifest.setdefault("complete", row[2])
        manifest.setdefault("config_hash", row[3])
        manifest.setdefault("manifest_hash", row[4])
        manifest.setdefault("reproducibility", row[5])
        manifest["created_at"] = row[0].isoformat()
        return manifest


def spec_from_run(detail: dict[str, Any]) -> RunSpecV1 | None:
    raw = (detail.get("config") or {}).get("run_spec")
    if not isinstance(raw, dict) or raw.get("schema_version") != RUN_SPEC_VERSION:
        return None
    return RunSpecV1.model_validate(deepcopy(raw))


def verify_manifest_hash(manifest: dict[str, Any]) -> bool:
    if manifest.get("schema_version") != RUN_MANIFEST_VERSION:
        return False
    expected = str(manifest.get("manifest_hash") or "")
    basis = {
        key: value for key, value in manifest.items() if key not in {"manifest_hash", "created_at"}
    }
    return bool(expected) and canonical_hash(basis) == expected
