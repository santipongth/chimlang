import { useEffect, useMemo, useState } from "react";
import { GraphSummary, InsightsData, ObservabilityData, fetchGraphSummary, fetchInsights, fetchObservability } from "../api";
import { useLang } from "../i18n";
import { InfoTip, PageHeader } from "../ui";

// หน้า Insights (P5-M6): knowledge graph interactive (แบบ studio: wedge cluster + hub ring
// + click → side panel) + analytics ข้าม run จาก audit/registry

const CLUSTER_COLORS = [
  "var(--color-chart-1)",
  "var(--color-chart-2)",
  "var(--color-chart-3)",
  "var(--color-chart-4)",
  "var(--color-chart-5)",
];

function KnowledgeGraph({ data, t }: { data: GraphSummary; t: (k: string) => string }) {
  const [filter, setFilter] = useState<string>("__all");
  const [sel, setSel] = useState<string | null>(null);

  const kindColor = useMemo(() => {
    const m = new Map<string, string>();
    data.kinds.forEach((k, i) => m.set(k, CLUSTER_COLORS[i % CLUSTER_COLORS.length]));
    return m;
  }, [data.kinds]);

  const hubs = useMemo(() => new Set(data.hubs), [data.hubs]);

  // Wedge layout ตาม studio: จัดกลุ่มตาม kind บนวงกลม, hub อยู่วงใน
  const positions = useMemo(() => {
    const W = 720, H = 430, cx = W / 2, cy = H / 2;
    const map = new Map<string, { x: number; y: number }>();
    const byKind = new Map<string, GraphSummary["nodes"]>();
    data.nodes.forEach((n) => {
      const arr = byKind.get(n.kind) ?? [];
      arr.push(n);
      byKind.set(n.kind, arr);
    });
    const kindArr = [...byKind.keys()];
    kindArr.forEach((k, ki) => {
      const nodes = byKind.get(k)!;
      const a0 = (ki / kindArr.length) * Math.PI * 2 - Math.PI / 2;
      const a1 = ((ki + 1) / kindArr.length) * Math.PI * 2 - Math.PI / 2;
      nodes.forEach((n, i) => {
        const isHub = hubs.has(n.name);
        const r = isHub ? 90 : 165 + ((i % 3) * 22);
        const theta = a0 + ((i + 0.5) / nodes.length) * (a1 - a0);
        map.set(n.name, { x: cx + Math.cos(theta) * r, y: cy + Math.sin(theta) * r });
      });
    });
    return { map, W, H };
  }, [data.nodes, hubs]);

  const selNode = sel ? data.nodes.find((n) => n.name === sel) : null;
  const connections = sel ? data.edges.filter((e) => e.from === sel || e.to === sel) : [];
  const connected = new Set<string>(sel ? [sel] : []);
  connections.forEach((e) => {
    connected.add(e.from);
    connected.add(e.to);
  });
  const visible = (name: string) =>
    filter === "__all" || data.nodes.find((n) => n.name === name)?.kind === filter;

  return (
    <div className="bg-card border border-border rounded-2xl p-5">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">
          🕸 {t("ins_graph_title")} <InfoTip text={t("tip_hub")} />
        </h2>
        <div className="flex flex-wrap items-center gap-1">
          <button
            onClick={() => setFilter("__all")}
            className={`rounded-full border px-2.5 py-1 text-xs ${filter === "__all" ? "bg-primary text-white border-primary" : "border-border text-muted-foreground hover:bg-muted"}`}
          >
            {t("ins_all")}
          </button>
          {data.kinds.map((k) => (
            <button
              key={k}
              onClick={() => setFilter(k)}
              className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs ${filter === k ? "bg-primary text-white border-primary" : "border-border text-muted-foreground hover:bg-muted"}`}
            >
              <span className="h-2 w-2 rounded-full" style={{ background: kindColor.get(k) }} /> {k}
            </button>
          ))}
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-[1fr_240px]">
        <div className="relative overflow-hidden rounded-xl border border-border bg-background">
          <svg viewBox={`0 0 ${positions.W} ${positions.H}`} className="h-[430px] w-full">
            {data.edges.map((e, i) => {
              const a = positions.map.get(e.from);
              const b = positions.map.get(e.to);
              if (!a || !b) return null;
              const dim = sel != null && e.from !== sel && e.to !== sel;
              const vis = visible(e.from) && visible(e.to);
              return (
                <line
                  key={i}
                  x1={a.x}
                  y1={a.y}
                  x2={b.x}
                  y2={b.y}
                  stroke="var(--color-muted-foreground)"
                  strokeOpacity={!vis ? 0.05 : dim ? 0.1 : 0.3}
                  strokeWidth={1}
                />
              );
            })}
            {data.nodes.map((n) => {
              const p = positions.map.get(n.name);
              if (!p) return null;
              const isHub = hubs.has(n.name);
              const color = kindColor.get(n.kind) ?? CLUSTER_COLORS[0];
              const dim = sel != null && !connected.has(n.name);
              const r = isHub ? 11 : 6;
              return (
                <g
                  key={n.name}
                  onClick={() => setSel(sel === n.name ? null : n.name)}
                  style={{ cursor: "pointer", opacity: !visible(n.name) ? 0.15 : dim ? 0.25 : 1 }}
                >
                  {isHub && <circle cx={p.x} cy={p.y} r={r + 5} fill="none" stroke={color} strokeOpacity={0.4} strokeWidth={1.5} />}
                  <circle cx={p.x} cy={p.y} r={r} fill={color} stroke="white" strokeWidth={1.5} />
                  <text x={p.x} y={p.y - r - 4} textAnchor="middle" fontSize={isHub ? 11 : 9} fill="var(--color-foreground)" style={{ pointerEvents: "none" }}>
                    {n.name.length > 20 ? n.name.slice(0, 20) + "…" : n.name}
                  </text>
                </g>
              );
            })}
          </svg>
          <div className="pointer-events-none absolute bottom-2 left-2 rounded-full bg-background/85 px-2 py-0.5 text-[10px] text-muted-foreground">
            ⭐ {t("ins_hub_hint")}
          </div>
        </div>

        {/* Side panel — click-to-drill */}
        <div className="rounded-xl border border-border bg-background p-3 text-sm">
          {!selNode ? (
            <p className="text-xs text-muted-foreground">{t("ins_select_hint")}</p>
          ) : (
            <div>
              <div className="flex items-center justify-between">
                <span className="text-xs uppercase tracking-wider text-muted-foreground">{t("ins_node")}</span>
                <button onClick={() => setSel(null)} className="text-xs text-muted-foreground hover:text-foreground">✕</button>
              </div>
              <div className="mt-2 flex items-center gap-2">
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: kindColor.get(selNode.kind) }} />
                <span className="text-xs text-muted-foreground">{selNode.kind}</span>
                {hubs.has(selNode.name) && (
                  <span className="rounded-full bg-primary/10 px-1.5 py-0.5 text-[10px] text-primary-strong">HUB</span>
                )}
              </div>
              <div className="mt-1 font-medium">{selNode.name}</div>
              <div className="mt-2 text-xs text-muted-foreground">
                degree {selNode.degree} · {t("ins_sources")} {selNode.sources}
              </div>
              <div className="mt-3 text-xs uppercase tracking-wider text-muted-foreground">{t("ins_connections")}</div>
              <ul className="mt-1 max-h-48 space-y-1 overflow-y-auto text-xs">
                {connections.map((e, i) => (
                  <li key={i} className="rounded bg-muted/60 px-2 py-1">
                    <span className="text-muted-foreground">{e.relation} →</span>{" "}
                    {e.from === selNode.name ? e.to : e.from}
                  </li>
                ))}
                {connections.length === 0 && <li className="text-muted-foreground">—</li>}
              </ul>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function Insights() {
  const { t, formatCurrency, formatNumber } = useLang();
  const [graph, setGraph] = useState<GraphSummary | null>(null);
  const [stats, setStats] = useState<InsightsData | null>(null);
  const [ops, setOps] = useState<ObservabilityData | null>(null);
  const [graphError, setGraphError] = useState("");
  const [statsError, setStatsError] = useState("");

  useEffect(() => {
    fetchGraphSummary().then(setGraph).catch((e) => setGraphError(String(e.message ?? e)));
    fetchInsights().then(setStats).catch((e) => setStatsError(String(e.message ?? e)));
    fetchObservability().then(setOps).catch(() => setOps(null));
  }, []);

  const card = "bg-card border border-border rounded-2xl p-5";
  const maxRuns = Math.max(1, ...(stats?.runs_per_day.map((d) => d.runs) ?? [1]));

  return (
    <div className="space-y-6">
      <PageHeader eyebrow={t("ins_eyebrow")} title={t("ins_title")} desc={t("ins_sub")} />

      {/* Cross-run stats */}
      {statsError && <div className="bg-red-50 border border-red-200 text-red-700 rounded-2xl p-5 text-sm">{statsError}</div>}
      {stats && (
        <>
          <div className="grid gap-4 sm:grid-cols-3">
            <div className={card}>
              <div className="text-xs uppercase tracking-wider text-muted-foreground">{t("ins_total_runs")}</div>
              <div className="mt-1 font-display text-4xl font-semibold">{stats.total_runs}</div>
            </div>
            <div className={card}>
              <div className="text-xs uppercase tracking-wider text-muted-foreground">{t("ins_exports")}</div>
              <div className="mt-1 font-display text-4xl font-semibold">{stats.exports}</div>
              <p className="mt-1 text-xs text-muted-foreground">{t("ins_exports_note")}</p>
            </div>
            <div className={card}>
              <div className="text-xs uppercase tracking-wider text-muted-foreground">{t("ins_predictions")}</div>
              <div className="mt-1 font-display text-4xl font-semibold">
                {stats.predictions_by_domain.reduce((s, d) => s + d.total, 0)}
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                {t("ins_resolved")} {stats.predictions_by_domain.reduce((s, d) => s + d.resolved, 0)}
              </p>
            </div>
          </div>

          {stats.runs_per_day.length > 0 && (
            <div className={card}>
              <div className="text-xs uppercase tracking-wider text-muted-foreground mb-3">{t("ins_runs_per_day")}</div>
              <div className="flex items-end gap-1 h-24">
                {stats.runs_per_day.map((d) => (
                  <div key={d.day} className="flex-1 rounded-t bg-primary/70 hover:bg-primary transition" style={{ height: `${(d.runs / maxRuns) * 100}%` }} title={`${d.day}: ${d.runs} runs`} />
                ))}
              </div>
              <div className="mt-1 flex justify-between text-[10px] text-muted-foreground">
                <span>{stats.runs_per_day[0]?.day}</span>
                <span>{stats.runs_per_day[stats.runs_per_day.length - 1]?.day}</span>
              </div>
            </div>
          )}

          {stats.predictions_by_domain.length > 0 && (
            <div className={card}>
              <div className="text-xs uppercase tracking-wider text-muted-foreground mb-3">{t("ins_by_domain")}</div>
              <div className="space-y-2">
                {stats.predictions_by_domain.map((d) => (
                  <div key={d.domain} className="flex items-center gap-3 text-sm">
                    <span className="w-40 shrink-0 truncate">{d.domain}</span>
                    <div className="h-2 flex-1 overflow-hidden rounded-full bg-secondary">
                      <div className="h-full bg-primary" style={{ width: `${(d.resolved / Math.max(1, d.total)) * 100}%` }} />
                    </div>
                    <span className="w-28 shrink-0 text-right text-xs text-muted-foreground tabular-nums">
                      {d.resolved}/{d.total} {t("ins_resolved_short")}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {ops && (
        <section className={card + " space-y-4"} aria-labelledby="provider-health-title">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 id="provider-health-title" className="font-semibold">{t("ins_provider_health")}</h2>
              <p className="mt-1 text-xs text-muted-foreground">{t("ins_provider_note")}</p>
            </div>
            <a href="/metrics" className="rounded-lg border border-border px-3 py-1.5 text-xs text-primary-strong hover:bg-primary/5">{t("ins_metrics_link")}</a>
          </div>
          <div className="grid gap-3 sm:grid-cols-4">
            <div className="rounded-xl bg-muted/50 p-3"><div className="text-[10px] uppercase text-muted-foreground">{t("ins_queued")}</div><div className="text-2xl font-semibold">{formatNumber(ops.queue.queued)}</div></div>
            <div className="rounded-xl bg-muted/50 p-3"><div className="text-[10px] uppercase text-muted-foreground">{t("ins_running")}</div><div className="text-2xl font-semibold">{formatNumber(ops.queue.running)}</div></div>
            <div className="rounded-xl bg-muted/50 p-3"><div className="text-[10px] uppercase text-muted-foreground">{t("ins_errors")}</div><div className="text-2xl font-semibold">{formatNumber(ops.queue.errors)}</div></div>
            <div className="rounded-xl bg-muted/50 p-3"><div className="text-[10px] uppercase text-muted-foreground">{t("ins_queue_avg")}</div><div className="text-2xl font-semibold">{formatNumber(ops.queue.avg_latency_seconds, { maximumFractionDigits: 1 })}s</div></div>
          </div>
          <div className="overflow-x-auto rounded-xl border border-border">
            <table className="w-full text-left text-xs">
              <thead className="bg-muted/50 text-muted-foreground"><tr><th className="px-3 py-2">{t("ins_provider_operation")}</th><th className="px-3 py-2">{t("ins_success")}</th><th className="px-3 py-2">{t("ins_latency")}</th><th className="px-3 py-2">{t("ins_cost")}</th></tr></thead>
              <tbody>
                {ops.providers.map((p) => (
                  <tr key={`${p.provider}-${p.operation}`} className="border-t border-border">
                    <td className="px-3 py-2"><code>{p.provider}</code> · {p.operation} <span className="text-muted-foreground">({p.calls})</span></td>
                    <td className="px-3 py-2">{formatNumber(p.success_rate * 100, { maximumFractionDigits: 1 })}%</td>
                    <td className="px-3 py-2">{formatNumber(p.avg_latency_ms, { maximumFractionDigits: 0 })} ms</td>
                    <td className="px-3 py-2">{formatCurrency(p.cost_usd, { minimumFractionDigits: 4, maximumFractionDigits: 4 })}</td>
                  </tr>
                ))}
                {ops.providers.length === 0 && <tr><td colSpan={4} className="px-3 py-4 text-muted-foreground">{t("ins_no_provider")}</td></tr>}
              </tbody>
            </table>
          </div>
          {ops.failure_taxonomy.length > 0 && (
            <div className="flex flex-wrap gap-2 text-xs">
              {ops.failure_taxonomy.map((f) => <span key={f.reason} className="rounded-full bg-red-50 px-2.5 py-1 text-red-700">{f.reason}: {f.count}</span>)}
            </div>
          )}
        </section>
      )}

      {/* Knowledge graph */}
      {graphError && (
        <div className="bg-amber-50 border border-amber-200 text-amber-800 rounded-2xl p-5 text-sm">
          🕸 {t("ins_graph_down")} — {graphError}
        </div>
      )}
      {graph && graph.nodes.length > 0 && <KnowledgeGraph data={graph} t={t} />}
      {graph && graph.nodes.length === 0 && (
        <p className="text-sm text-muted-foreground">{t("ins_graph_empty")}</p>
      )}
    </div>
  );
}
