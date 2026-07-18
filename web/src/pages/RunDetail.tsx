import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  CircleSlash,
  FileSearch,
  Info,
  Radio,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  SkipForward,
  X,
} from "lucide-react";
import {
  DebateRunPayload,
  EvidenceSourceItem,
  FabricRunPayload,
  SimRunDetail,
  ValidationReport,
  cancelRun,
  pct,
  rerunRun,
  shareRun,
  unshareRun,
  validateRun,
} from "../api";
import { getRunDetailTyped, getValidationTyped } from "../openapi-client";
import { useRunEvents } from "../hooks/useRunEvents";
import { VirtualizedDebateList } from "../components/VirtualizedDebateList";
import {
  ContentionGraph,
  EvidenceLineage,
  ScenarioComparisonChart,
  StabilityMatrix,
  StanceTimelineChart,
  UniverseRangeChart,
} from "../components/RunVisualizations";
import { useLang } from "../i18n";
import { InfoTip, PageHeader, Tabs } from "../ui";

// Run detail (P6-M2) — หน้าเดียวรองรับทั้ง fabric (dashboard payload) และ debate (posts+replay)

type Tab = "overview" | "debate" | "evidence" | "canvas" | "validation" | "report";

function StatusIcon({ status }: { status: string }) {
  if (status === "ready") return <CheckCircle2 className="inline h-3.5 w-3.5 text-primary" />;
  if (status === "redacted") return <ShieldCheck className="inline h-3.5 w-3.5 text-amber-600" />;
  if (status === "blocked") return <ShieldAlert className="inline h-3.5 w-3.5 text-red-600" />;
  if (status === "skipped") return <SkipForward className="inline h-3.5 w-3.5 text-amber-600" />;
  if (status === "empty") return <CircleSlash className="inline h-3.5 w-3.5 text-muted-foreground" />;
  return <AlertTriangle className="inline h-3.5 w-3.5 text-amber-600" />;
}

function StanceTrend({ values, t }: { values: number[]; t: (k: string) => string }) {
  if (!values.length) {
    return <div className="flex h-32 items-center justify-center text-sm text-muted-foreground">{t("rd_stance_no_data")}</div>;
  }
  const columns = { gridTemplateColumns: `repeat(${values.length}, minmax(36px, 1fr))` };
  return (
    <div className="overflow-x-auto pb-1">
      <div className="min-w-[240px]">
        <div className="relative h-28 pl-8">
          <span className="absolute left-0 top-0 text-[10px] tabular-nums text-muted-foreground">+1</span>
          <span className="absolute left-2 top-1/2 -translate-y-1/2 text-[10px] tabular-nums text-muted-foreground">0</span>
          <span className="absolute bottom-0 left-0 text-[10px] tabular-nums text-muted-foreground">-1</span>
          <div className="absolute inset-y-0 left-8 right-0 border-y border-border/60">
            <div className="absolute inset-x-0 top-1/2 border-t border-border" />
            <div className="absolute inset-0 grid gap-2 px-2" style={columns}>
              {values.map((raw, i) => {
                const stance = Math.max(-1, Math.min(1, Number(raw) || 0));
                const positive = stance >= 0;
                return (
                  <div key={i} className="relative h-full">
                    <div
                      className={`absolute left-1/2 w-3/5 -translate-x-1/2 ${positive ? "bottom-1/2 rounded-t bg-primary/75" : "top-1/2 rounded-b bg-red-400/80"}`}
                      style={{ height: `${Math.max(2, Math.abs(stance) * 50)}%` }}
                      title={`${t("rd_round_word")} ${i + 1}: ${stance.toFixed(2)}`}
                    />
                  </div>
                );
              })}
            </div>
          </div>
        </div>
        <div className="ml-8 grid gap-2 px-2 pt-1" style={columns}>
          {values.map((stance, i) => (
            <div key={i} className="text-center text-[10px] tabular-nums text-muted-foreground">
              <div>r{i + 1}</div>
              <div className="font-medium text-foreground">{Number(stance).toFixed(2)}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function RedactionSummary({ counts, t }: { counts?: Record<string, number>; t: (k: string) => string }) {
  const entries = Object.entries(counts ?? {}).filter(([, count]) => count > 0);
  if (!entries.length) return null;
  return (
    <div className="mt-2 flex flex-wrap items-center gap-1 text-[11px] text-amber-700">
      <ShieldCheck className="h-3.5 w-3.5" />
      <span>{t("rd_pii_removed")}:</span>
      {entries.map(([kind, count]) => (
        <span key={kind} className="rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5">
          {kind} {count}
        </span>
      ))}
    </div>
  );
}

type RunPayloadView = Partial<DebateRunPayload & FabricRunPayload>;

export function hasUsableExecutiveSynthesis(
  synthesis: DebateRunPayload["synthesis"] | undefined,
): boolean {
  return Boolean(
    synthesis
    && synthesis.status !== "analyst_failed"
    && typeof synthesis.summary === "string"
    && synthesis.summary.trim().length > 0
    && typeof synthesis.confidence === "number"
    && Number.isFinite(synthesis.confidence)
    && synthesis.confidence >= 0
    && synthesis.confidence <= 1
    && Array.isArray(synthesis.distribution)
    && synthesis.distribution.length > 0
    && synthesis.distribution.every(
      (item) => item
        && typeof item.bucket === "string"
        && item.bucket.trim().length > 0
        && typeof item.pct === "number"
        && Number.isFinite(item.pct)
        && item.pct >= 0
        && item.pct <= 100,
    )
    && Array.isArray(synthesis.key_drivers)
    && synthesis.key_drivers.length > 0
    && synthesis.key_drivers.every(
      (item) => typeof item === "string" && item.trim().length > 0,
    )
    && Array.isArray(synthesis.risks)
    && synthesis.risks.length > 0
    && synthesis.risks.every(
      (item) => typeof item === "string" && item.trim().length > 0,
    ),
  );
}

export function ExecutiveReadout({
  data,
  p,
  isDebate,
  t,
  onRerunFrozen,
  rerunBusy = false,
}: {
  data: SimRunDetail;
  p: RunPayloadView;
  isDebate: boolean;
  t: (k: string) => string;
  onRerunFrozen?: () => void;
  rerunBusy?: boolean;
}) {
  if (isDebate && !hasUsableExecutiveSynthesis(p.synthesis)) {
    return (
      <section className="rounded-2xl border border-amber-300 bg-amber-50 p-5" role="alert" aria-live="polite">
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-amber-800">
          <AlertTriangle className="h-4 w-4" /> {t("rd_exec_readout")}
        </div>
        <h2 className="mt-2 text-xl font-semibold text-amber-950">{t("rd_synthesis_unavailable")}</h2>
        <p className="mt-2 text-sm text-amber-900">{t("rd_synthesis_unavailable_desc")}</p>
        {data.manifest?.complete && onRerunFrozen && (
          <button
            type="button"
            disabled={rerunBusy}
            onClick={onRerunFrozen}
            className="mt-4 inline-flex min-h-11 items-center gap-2 rounded-xl bg-amber-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            <RefreshCw className={`h-4 w-4 ${rerunBusy ? "animate-spin" : ""}`} />
            {t("rd_rerun_frozen_for_readout")}
          </button>
        )}
      </section>
    );
  }
  const summary = isDebate
    ? p.synthesis?.summary
    : p.brief?.lines?.[0]?.text || data.subject;
  const confidence = isDebate
    ? `${Math.round((p.synthesis?.confidence ?? 0) * 100)}%`
    : p.brief?.confidence_label || "range";
  const range = !isDebate && p.brief?.headline_range
    ? `${p.brief.headline_range[0]} to ${p.brief.headline_range[1]}`
    : isDebate
      ? `${p.metrics?.per_round_avg_stance?.at?.(-1)?.toFixed?.(2) ?? "0.00"} stance`
      : "n/a";
  const risks = isDebate ? (p.synthesis?.risks ?? []) : (p.brief?.lines ?? []).filter((x: any) => x.kind === "risk").map((x: any) => x.text);
  return (
    <section className="rounded-2xl border border-border bg-card p-5">
      <div className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
        <div>
          <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            <FileSearch className="h-4 w-4" /> {t("rd_exec_readout")}
          </div>
          <h2 className="text-xl font-semibold leading-snug">{summary}</h2>
          <p className="mt-2 text-sm text-muted-foreground">{t("rd_prediction_note")}</p>
        </div>
        <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-1">
          {[
            [t("rd_confidence"), confidence],
            [t("rd_metric_headline"), range],
            [t("rd_metric_evidence"), `${(p.sources ?? []).length + (p.news?.items ?? []).length} ${t("wiz_src_unit")}`],
          ].map(([k, v]) => (
            <div key={k} className="rounded-xl border border-border bg-background px-3 py-2">
              <div className="text-[11px] uppercase tracking-wider text-muted-foreground">{k}</div>
              <div className="mt-1 font-semibold">{v}</div>
            </div>
          ))}
        </div>
      </div>
      {risks.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {risks.slice(0, 3).map((r: string, i: number) => (
            <span key={i} className="inline-flex items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-xs text-amber-800">
              <AlertTriangle className="h-3.5 w-3.5" /> {r}
            </span>
          ))}
        </div>
      )}
    </section>
  );
}

function SocialSignalMap({ newsItems, t }: { newsItems: any[]; t: (k: string) => string }) {
  const channels = ["line_closed_group", "public_feed", "algo_feed", "offline_wom"];
  const ready = newsItems.filter((x) => x.status === "ready");
  return (
    <div className="rounded-2xl border border-border bg-background p-4">
      <div className="mb-3 flex items-center gap-2 text-sm font-semibold">
        <Radio className="h-4 w-4 text-primary" /> {t("rd_signal_map")}
      </div>
      <div className="grid gap-2 md:grid-cols-4">
        {channels.map((id) => {
          const count = ready.filter((x) => (x.channel_tags?.[id] ?? 0) > 0.12).length;
          return (
            <div key={id} className="rounded-xl border border-border bg-card p-3">
              <div className="text-xs font-medium">{t(`pk_ch_${id}`)}</div>
              <div className="mt-2 h-2 overflow-hidden rounded-full bg-secondary">
                <div className="h-full bg-primary" style={{ width: `${Math.min(100, count * 22)}%` }} />
              </div>
              <div className="mt-1 text-[11px] text-muted-foreground">{count} {t("rd_signals_unit")}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function TrustScorecard({ scorecard, t }: { scorecard: SimRunDetail["trust_scorecard"]; t: (k: string) => string }) {
  if (!scorecard) return null;
  const tone = scorecard.band === "strong" ? "text-primary-strong" : scorecard.band === "usable" ? "text-amber-700" : "text-red-700";
  // แปล label ของ check ตาม id — id ที่ไม่รู้จัก fallback เป็น label จาก API (detail คงเป็น technical)
  const checkLabel = (c: { id: string; label: string }) => {
    const key = `rd_tsc_${c.id}`;
    const translated = t(key);
    return translated === key ? c.label : translated;
  };
  const bandKey = `rd_tsc_band_${scorecard.band}`;
  const bandLabel = t(bandKey) === bandKey ? scorecard.band : t(bandKey);
  return (
    <section className="rounded-2xl border border-border bg-card p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t("rd_trust_scorecard")}</div>
          <div className={`mt-1 text-3xl font-semibold ${tone}`}>{scorecard.score}/100</div>
          <div className="text-xs text-muted-foreground">{bandLabel}</div>
        </div>
        <div className="grid flex-1 gap-2 md:grid-cols-3">
          {scorecard.checks.map((c) => (
            <div key={c.id} className={`rounded-xl border px-3 py-2 text-xs ${c.status === "block" ? "border-red-200 bg-red-50 text-red-700" : c.status === "warn" ? "border-amber-200 bg-amber-50 text-amber-700" : "border-primary/20 bg-primary/5 text-primary-strong"}`}>
              <div className="font-medium">{checkLabel(c)}</div>
              <div className="mt-0.5 text-muted-foreground">{c.detail}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function EvidenceDrawer({ item, onClose, t }: { item: any | null; onClose: () => void; t: (k: string) => string }) {
  if (!item) return null;
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/30 backdrop-blur-[2px]" onClick={onClose}>
      <aside className="h-full w-full max-w-lg overflow-auto border-l border-border bg-card p-6 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-sm font-semibold">
            <Info className="h-4 w-4 text-primary" /> {t("rd_metric_evidence")}
          </div>
          <button onClick={onClose} className="rounded-lg border border-border p-2 text-muted-foreground hover:bg-muted">
            <X className="h-4 w-4" />
          </button>
        </div>
        <h3 className="mt-4 text-lg font-semibold">{item.title || item.label || item.url || t("rd_evidence_item")}</h3>
        <div className="mt-3 grid grid-cols-[110px_1fr] gap-y-2 text-sm">
          <span className="text-muted-foreground">{t("rd_field_status")}</span><span><StatusIcon status={item.status} /> {item.status}</span>
          <span className="text-muted-foreground">{t("rd_field_type")}</span><span>{item.provider || item.kind || "source"}</span>
          {item.url && <><span className="text-muted-foreground">url</span><a href={item.url} target="_blank" rel="noreferrer" className="truncate text-primary-strong hover:underline">{item.url}</a></>}
          {item.chunks != null && <><span className="text-muted-foreground">{t("rd_evidence_chunks")}</span><span>{item.chunks}</span></>}
          {item.fetched_at && <><span className="text-muted-foreground">{t("rd_field_fetched")}</span><span>{String(item.fetched_at).slice(0, 16).replace("T", " ")}</span></>}
        </div>
        {item.error && <div className="mt-4 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">{item.error}</div>}
        <RedactionSummary counts={item.pii_redactions} t={t} />
        {item.content && <p className="mt-4 whitespace-pre-wrap text-sm text-muted-foreground">{item.content}</p>}
      </aside>
    </div>
  );
}

// แผนภาพสวอร์มของ debate — จุดยืน agent รอบสุดท้าย (x = จุดยืน −1..1, สี = ทิศ)
function DebateScatter({ posts, rounds, t }: { posts: any[]; rounds: number; t: (k: string) => string }) {
  const last = posts.filter((x) => x.round_no === rounds - 1 && !x.failed);
  const W = 560, H = 260, P = 40;
  const sx = (s: number) => P + ((s + 1) / 2) * (W - P * 2);
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto">
        <line x1={P} y1={H / 2} x2={W - P} y2={H / 2} stroke="var(--color-border)" />
        <line x1={W / 2} y1={30} x2={W / 2} y2={H - 30} stroke="var(--color-border)" strokeDasharray="4,4" />
        <text x={P} y={H - 12} fontSize="10" fill="var(--color-muted-foreground)">← {t("rd_scatter_oppose")}</text>
        <text x={W - P} y={H - 12} textAnchor="end" fontSize="10" fill="var(--color-muted-foreground)">{t("rd_scatter_support")} →</text>
        {last.map((x, i) => {
          const jitter = ((i * 53) % 100) - 50;
          const color = x.stance > 0.2 ? "var(--color-primary)" : x.stance < -0.2 ? "oklch(0.65 0.22 25)" : "oklch(0.6 0.02 250)";
          return (
            <circle key={i} cx={sx(x.stance)} cy={H / 2 + jitter * 0.9} r={7} fill={color} fillOpacity={0.6} stroke="white" strokeWidth={1.2}>
              <title>{`${x.segment}: ${x.stance >= 0 ? "+" : ""}${x.stance.toFixed(2)}\n${x.content}`}</title>
            </circle>
          );
        })}
      </svg>
      <p className="text-xs text-muted-foreground">{last.length} {t("rd_scatter_agents")}</p>
    </div>
  );
}

function DebateProtocolPanel({ protocol, t }: { protocol: any; t: (k: string) => string }) {
  if (!protocol) return null;
  const rounds = protocol.per_round_disagreement ?? [];
  const nodes = protocol.contention_graph?.nodes ?? [];
  const edges = protocol.contention_graph?.edges ?? [];
  const failures = Object.entries(protocol.failure_taxonomy ?? {});
  const verifier = protocol.verifier ?? null;
  const judge = protocol.analyst_judge ?? null;
  return (
    <div>
      <div className="grid gap-3 lg:grid-cols-[1fr_0.9fr]">
        <div className="rounded-2xl border border-border bg-background p-4">
          <div className="text-sm font-semibold">{t("rd_disagreement_round")}</div>
          <div className="mt-3 space-y-2">
            {rounds.map((r: any) => (
              <div key={r.round} className="grid grid-cols-[42px_1fr_52px] items-center gap-2 text-xs">
                <span className="text-muted-foreground">r{r.round + 1}</span>
                <div className="flex h-2 overflow-hidden rounded-full bg-secondary">
                  <span className="bg-red-400" style={{ width: `${Math.min(100, r.oppose * 12)}%` }} />
                  <span className="bg-muted-foreground/40" style={{ width: `${Math.min(100, r.neutral * 12)}%` }} />
                  <span className="bg-primary" style={{ width: `${Math.min(100, r.support * 12)}%` }} />
                </div>
                <span className="text-right tabular-nums">{Number(r.dispersion ?? 0).toFixed(2)}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="rounded-2xl border border-border bg-background p-4">
          <div className="text-sm font-semibold">{t("rd_contention_graph")}</div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {nodes.map((n: any) => (
              <span key={n.segment} className="rounded-full border border-border px-2 py-1 text-[11px]">
                {n.segment}: {Number(n.avg_stance ?? 0).toFixed(2)}
              </span>
            ))}
          </div>
          {edges.length > 0 && (
            <div className="mt-3 space-y-1 text-xs text-muted-foreground">
              {edges.slice(0, 5).map((e: any, i: number) => (
                <div key={i}>{e.from} - {e.to}: {t("rd_tension")} {Number(e.tension ?? 0).toFixed(2)}</div>
              ))}
            </div>
          )}
        </div>
      </div>
      {failures.length > 0 && (
        <div className="mt-3 border-l-2 border-amber-400 bg-amber-50 px-3 py-2 text-xs text-amber-800">
          <span className="font-medium">{t("rd_agent_response_failures")}:</span>{" "}
          {failures.map(([k, v], i) => (
            <span key={k}>{i > 0 ? ", " : ""}{t(`failure_${k}`) === `failure_${k}` ? k : t(`failure_${k}`)} {String(v)}</span>
          ))}
        </div>
      )}
      {(verifier || judge) && (
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          <div className="rounded-xl border border-border bg-background p-3 text-xs">
            <div className="font-semibold">{t("rd_verifier")}</div>
            <div className="mt-1 text-muted-foreground">
              {t("rd_verifier_summary")
                .replace("{status}", String(verifier?.status ?? t("rd_legacy_word")))
                .replace("{moves}", String(verifier?.moves_checked ?? 0))
                .replace("{findings}", String(verifier?.violations?.length ?? 0))}
            </div>
            <div className="mt-2 flex flex-wrap gap-1">
              {Object.entries(verifier?.counts ?? {}).map(([key, value]) => <span key={key} className="rounded-full bg-amber-50 px-2 py-0.5 text-amber-800">{key}: {String(value)}</span>)}
            </div>
          </div>
          <div className="rounded-xl border border-border bg-background p-3 text-xs">
            <div className="font-semibold">{t("rd_analyst_judge")}</div>
            <div className="mt-1 text-muted-foreground">{t("rd_verdict_word")} {judge?.verdict ?? t("rd_unavailable")}</div>
            <p className="mt-2">{judge?.citation_assessment ?? "—"}</p>
            <p className="mt-1">{judge?.contradiction_assessment ?? "—"}</p>
            <p className="mt-1">{judge?.schema_assessment ?? "—"}</p>
          </div>
        </div>
      )}
    </div>
  );
}

export default function RunDetail({
  runId,
  onBack,
  onOpenRun,
}: {
  runId: string;
  onBack: () => void;
  onOpenRun?: (runId: string) => void;
}) {
  const { lang, t } = useLang();
  const queryClient = useQueryClient();
  const runQuery = useQuery({
    queryKey: ["run", runId],
    queryFn: () => getRunDetailTyped(runId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "queued" || status === "running" ? 10_000 : false;
    },
  });
  const data: SimRunDetail | null = runQuery.data ?? null;
  const error = runQuery.error ? String((runQuery.error as Error).message ?? runQuery.error) : "";
  const [tab, setTab] = useState<Tab>("overview");
  const [replayRound, setReplayRound] = useState<number | null>(null);
  const [shareOpen, setShareOpen] = useState(false);
  const [shareBusy, setShareBusy] = useState(false);
  const [shareErr, setShareErr] = useState("");
  const [copied, setCopied] = useState(false);
  const [selectedEvidence, setSelectedEvidence] = useState<any | null>(null);
  const [actionErr, setActionErr] = useState("");
  const [contractBusy, setContractBusy] = useState(false);
  const [runActionBusy, setRunActionBusy] = useState("");
  const [validationEnabled, setValidationEnabled] = useState(false);
  const validationQuery = useQuery({
    queryKey: ["validation", runId],
    queryFn: () => getValidationTyped(runId),
    enabled: validationEnabled,
    refetchInterval: (query) => {
      const report = query.state.data;
      return report?.children?.some((child) => child.status === "queued" || child.status === "running") ? 5_000 : false;
    },
  });
  const validation: ValidationReport | null = validationQuery.data ?? null;

  const stream = useRunEvents(
    runId,
    data?.status === "queued" || data?.status === "running",
    () => queryClient.invalidateQueries({ queryKey: ["run", runId] }),
  );

  async function reload() {
    await runQuery.refetch();
  }

  async function cancelCurrentRun() {
    setRunActionBusy("cancel");
    setActionErr("");
    try {
      await cancelRun(runId);
      await reload();
    } catch (e: any) {
      setActionErr(String(e.message ?? e));
    } finally {
      setRunActionBusy("");
    }
  }

  async function rerun(inputMode: "frozen" | "latest") {
    setRunActionBusy(inputMode);
    setActionErr("");
    try {
      const key = globalThis.crypto?.randomUUID?.() ?? `rerun-${Date.now()}-${Math.random()}`;
      const accepted = await rerunRun(runId, inputMode, key);
      if (onOpenRun) onOpenRun(accepted.run_id);
      else window.location.hash = `/runs/${encodeURIComponent(accepted.run_id)}`;
    } catch (e: any) {
      setActionErr(String(e.message ?? e));
    } finally {
      setRunActionBusy("");
    }
  }

  async function startValidation() {
    setContractBusy(true);
    setActionErr("");
    try {
      await validateRun(runId);
      setValidationEnabled(true);
      await queryClient.invalidateQueries({ queryKey: ["validation", runId] });
    } catch (e: any) {
      setActionErr(String(e.message ?? e));
    } finally {
      setContractBusy(false);
    }
  }

  const card = "bg-card border border-border rounded-2xl p-6";
  const isDebate = data?.engine === "debate";
  const p = (data?.payload ?? {}) as RunPayloadView;
  const hasExecutiveSynthesis = !isDebate || hasUsableExecutiveSynthesis(p.synthesis);
  // มุมมองที่ผู้ใช้เลือกเปิดตอนสั่งรัน (P6-M6) — ว่าง = ครบทุกมุม
  const configuredViews = data?.config?.views;
  const enabledViews = Array.isArray(configuredViews)
    ? configuredViews.filter((view): view is string => typeof view === "string")
    : ["overview", "debate", "canvas", "evidence"];
  const showView = (v: string) => v === "report" || enabledViews.includes(v);
  const rounds = useMemo(
    () => (data ? [...new Set(data.posts.map((x) => x.round_no))].sort((a, b) => a - b) : []),
    [data],
  );
  const newsItems: EvidenceSourceItem[] = p.news?.items ?? [];
  const newsCounts = newsItems.reduce(
    (acc: Record<string, number>, item: EvidenceSourceItem) => {
      acc[item.status || "unknown"] = (acc[item.status || "unknown"] ?? 0) + 1;
      return acc;
    },
    {},
  );
  const sourceCounts = (p.sources ?? []).reduce(
    (acc: Record<string, number>, item: EvidenceSourceItem) => {
      acc[item.status || "unknown"] = (acc[item.status || "unknown"] ?? 0) + 1;
      return acc;
    },
    {},
  );
  const shownRound = replayRound ?? (rounds.length ? rounds[rounds.length - 1] : 0);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={`${data?.engine === "debate" ? "🗣 DEBATE" : "⚙ FABRIC"} · ${data?.created_at?.slice(0, 16).replace("T", " ") ?? ""}${stream.state === "live" || stream.state === "reconnecting" ? ` · ${stream.state}` : ""}`}
        title={data?.subject ?? runId}
        right={
          <button onClick={onBack} className="rounded-xl border border-border px-4 py-2 text-sm text-muted-foreground hover:bg-muted">
            ← {t("rd_back")}
          </button>
        }
      />

      {error && (
        <div className="rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-700">
          <p>{error}</p>
          <button type="button" onClick={reload} className="mt-3 rounded-lg border border-red-300 px-3 py-2 font-medium">
            {t("rd_reconnect")}
          </button>
        </div>
      )}
      {!data && !error && (
        <section className={card + " animate-pulse"}>
          <div className="h-4 w-40 rounded bg-muted" />
          <div className="mt-4 h-8 w-2/3 rounded bg-muted" />
          <div className="mt-3 h-3 w-1/2 rounded bg-muted" />
        </section>
      )}
      {data?.status === "error" && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-2xl p-5 text-sm">
          <p>{t("rd_failed")}: {data.error}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <button type="button" disabled={!!runActionBusy} onClick={() => rerun("latest")} className="rounded-lg bg-red-700 px-3 py-2 font-medium text-white disabled:opacity-50">
              {t("rd_rerun_latest")}
            </button>
            {data.manifest?.complete && (
              <button type="button" disabled={!!runActionBusy} onClick={() => rerun("frozen")} className="rounded-lg border border-red-300 px-3 py-2 font-medium disabled:opacity-50">
                {t("rd_rerun_frozen")}
              </button>
            )}
          </div>
        </div>
      )}

      {data && (data.status === "queued" || data.status === "running" || data.status === "canceled") && (
        <section className={card + " space-y-4"} aria-live="polite">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                {data.status === "canceled" ? t("rd_canceled") : t("rd_running_timeline")}
              </div>
              <h2 className="mt-1 font-display text-xl font-semibold">
                {data.progress_message || data.status}
              </h2>
              {data.status !== "canceled" && (
                <p className="mt-1 text-xs text-muted-foreground">
                  SSE: {stream.state} · event #{stream.lastEventId || "—"}
                </p>
              )}
            </div>
            <div className="flex flex-wrap gap-2">
              <button type="button" onClick={reload} className="rounded-lg border border-border px-3 py-2 text-sm hover:bg-muted">
                <RefreshCw className="mr-1 inline h-4 w-4" /> {t("rd_reconnect")}
              </button>
              {data.status !== "canceled" && (
                <button type="button" disabled={!!runActionBusy} onClick={cancelCurrentRun} className="rounded-lg border border-red-200 px-3 py-2 text-sm text-red-700 hover:bg-red-50 disabled:opacity-50">
                  {runActionBusy === "cancel" ? "…" : t("hist_cancel_action")}
                </button>
              )}
            </div>
          </div>
          {data.status !== "canceled" && (
            <div>
              <div className="mb-1 flex justify-between text-xs text-muted-foreground">
                <span>{data.status}</span><span>{data.progress ?? 0}%</span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-muted">
                <div className="h-full bg-primary transition-all" style={{ width: `${Math.max(2, data.progress ?? 0)}%` }} />
              </div>
            </div>
          )}
          {(data.events ?? []).length > 0 && (
            <ol className="space-y-2 border-l border-border pl-4 text-xs">
              {(data.events ?? []).slice(-6).map((event, index) => (
                <li key={`${event.created_at}-${index}`}>
                  <span className="font-medium">{event.event_type}</span>
                  <span className="ml-2 text-muted-foreground">{event.message}</span>
                </li>
              ))}
            </ol>
          )}
          {data.status === "canceled" && (
            <div className="flex flex-wrap gap-2">
              <button type="button" disabled={!!runActionBusy} onClick={() => rerun("latest")} className="rounded-lg bg-primary px-3 py-2 text-sm font-medium text-white disabled:opacity-50">
                {t("rd_run_latest")}
              </button>
              {data.manifest?.complete && (
                <button type="button" disabled={!!runActionBusy} onClick={() => rerun("frozen")} className="rounded-lg border border-border px-3 py-2 text-sm disabled:opacity-50">
                  {t("rd_rerun_frozen")}
                </button>
              )}
            </div>
          )}
        </section>
      )}

      {actionErr && <p className="rounded-xl border border-red-200 bg-red-50 p-3 text-xs text-red-700">{actionErr}</p>}

      {data && (data.status === "complete" || data.status === "error") && (
        <>
          <ExecutiveReadout
            data={data}
            p={p}
            isDebate={isDebate}
            t={t}
            onRerunFrozen={() => rerun("frozen")}
            rerunBusy={runActionBusy === "frozen"}
          />
          <TrustScorecard scorecard={data.trust_scorecard} t={t} />
          <Tabs<Tab>
            tabs={[
              { id: "overview" as Tab, label: t("rd_tab_result") },
              ...(isDebate && showView("debate") ? [{ id: "debate" as Tab, label: t("rd_tab_debate") }] : []),
              ...(showView("evidence") ? [{ id: "evidence" as Tab, label: t("rd_tab_evidence") }] : []),
              ...(showView("canvas") ? [{ id: "canvas" as Tab, label: t("rd_tab_uncertainty") }] : []),
              { id: "validation" as Tab, label: t("rd_tab_validation") },
              { id: "report" as Tab, label: t("rd_tab_audit") },
            ]}
            active={tab}
            onChange={setTab}
          />

          {tab === "overview" && isDebate && (
            <>
              <section className={card + " space-y-3"}>
                <h2 className="font-semibold">{t("rd_synthesis")}</h2>
                {!hasExecutiveSynthesis ? (
                  <p className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900" role="alert">
                    {t("rd_synthesis_unavailable_desc")}
                  </p>
                ) : (<>
                  <p className="text-sm">{p.synthesis?.summary}</p>
                  <div className="flex flex-wrap items-center gap-3 text-sm">
                  <span className="rounded-full bg-primary-soft px-3 py-1 text-primary-strong">
                    {t("rd_confidence")} {((p.synthesis?.confidence ?? 0) * 100).toFixed(0)}% <InfoTip text={t("tip_debate_conf")} />
                  </span>
                  {(p.metrics?.posts_failed ?? 0) > 0 && (
                    <span className="rounded-full bg-amber-50 border border-amber-200 px-3 py-1 text-amber-700">
                      ⚠️ {p.metrics?.posts_failed ?? 0} {t("rd_failed_posts")}
                    </span>
                  )}
                  {p.cost_usd != null && <span className="text-xs text-muted-foreground">{t("rd_cost")} ${p.cost_usd}</span>}
                  </div>
                  <div className="flex flex-wrap gap-2">
                  {(p.synthesis?.distribution ?? []).map((d: any) => (
                    <span key={d.bucket} className="rounded-full bg-muted px-3 py-1 text-xs">
                      {d.bucket}: {d.pct}%
                    </span>
                  ))}
                  </div>
                  <div className="grid gap-2 sm:grid-cols-2 text-sm">
                  <div>
                    <div className="text-xs uppercase tracking-wider text-muted-foreground">{t("rd_drivers")}</div>
                    <ul className="mt-1 list-disc pl-5 text-muted-foreground">
                      {(p.synthesis?.key_drivers ?? []).map((k: string, i: number) => <li key={i}>{k}</li>)}
                    </ul>
                  </div>
                  <div>
                    <div className="text-xs uppercase tracking-wider text-muted-foreground">{t("rd_risks")}</div>
                    <ul className="mt-1 list-disc pl-5 text-muted-foreground">
                      {(p.synthesis?.risks ?? []).map((k: string, i: number) => <li key={i}>{k}</li>)}
                    </ul>
                  </div>
                  </div>
                </>)}
              </section>
              <section className={card}>
                <h2 className="font-semibold mb-2">
                  {t("rd_stance_trend")} <InfoTip text={t("tip_stance_series")} />
                </h2>
                <StanceTrend values={p.metrics?.per_round_avg_stance ?? []} t={t} />
                {(p.metrics?.tipping_points ?? []).length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {(p.metrics?.tipping_points ?? []).map((tp: any, i: number) => (
                      <span key={i} className="rounded-full border border-amber-300 bg-amber-50 px-3 py-1 text-xs text-amber-700">
                        ⚡ r{tp.round + 1}: {(tp.delta * 100).toFixed(0)}%
                      </span>
                    ))}
                  </div>
                )}
              </section>
              <section className={card}>
                <h2 className="mb-2 font-semibold">{t("rd_stance_beeswarm")}</h2>
                <StanceTimelineChart posts={data.posts} />
              </section>
              <DebateProtocolPanel protocol={p.protocol} t={t} />
              <section className={card}>
                <h2 className="mb-3 font-semibold">{t("rd_contention_interactive")}</h2>
                <ContentionGraph posts={data.posts} />
              </section>
            </>
          )}

          {tab === "overview" && !isDebate && (
            <>
              <section className={card + " space-y-3"}>
                <h2 className="font-semibold">{t("rd_brief_title")}</h2>
                <ul className="space-y-1.5 text-sm">
                  {(p.brief?.lines ?? []).map((ln: any, i: number) => (
                    <li key={i} className={ln.kind === "risk" ? "text-red-700" : "text-primary-strong"}>
                      {ln.kind === "risk" ? "⚠️" : "✅"} {ln.text}
                    </li>
                  ))}
                </ul>
                <p className="text-xs text-muted-foreground">
                  {t("rd_fragility_word")} {p.brief?.fragility_index}/100 — {p.brief?.confidence_label} <InfoTip text={t("tip_fragility")} />
                </p>
              </section>
              <section className={card}>
                <h2 className="mb-3 font-semibold">{t("rd_multiverse")}</h2>
                <UniverseRangeChart universes={p.universe_estimates ?? []} fallbackRange={p.brief?.headline_range} />
              </section>
              <section className={card}>
                <h2 className="font-semibold mb-3">{t("compare_title")}</h2>
                <ScenarioComparisonChart scenarios={p.scenarios ?? []} population={p.voice_population_share ?? []} />
                {(p.tipping_points ?? []).length > 0 ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {(p.tipping_points ?? []).map((tp: any, i: number) => (
                      <span key={i} className="rounded-full border border-amber-300 bg-amber-50 px-3 py-1 text-xs text-amber-700">
                        ⚡ {tp.scenario} r{tp.round}: {tp.delta > 0 ? "+" : ""}{Math.round(tp.delta * 100)}%
                      </span>
                    ))}
                  </div>
                ) : (
                  <p className="mt-3 text-xs text-muted-foreground">{t("tipping_none")}</p>
                )}
              </section>
            </>
          )}

          {tab === "debate" && isDebate && (
            <section className={card}>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 className="font-semibold">🗣 {t("rd_feed")} — {t("rd_round")} {shownRound + 1}</h2>
                {/* Replay slider ทีละรอบ */}
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <span>▶ {t("rd_replay")}</span>
                  <input
                    type="range"
                    min={rounds[0] ?? 0}
                    max={rounds[rounds.length - 1] ?? 0}
                    value={shownRound}
                    onChange={(e) => setReplayRound(parseInt(e.target.value))}
                    className="w-40 accent-primary"
                  />
                  <span className="tabular-nums">{shownRound + 1}/{rounds.length}</span>
                </div>
              </div>
              <VirtualizedDebateList posts={data.posts.filter((post) => post.round_no === shownRound)} />
            </section>
          )}

          {/* แผนภาพสวอร์ม — จุดยืน/ความเชื่อรายกลุ่ม (P6-M6) */}
          {tab === "canvas" && (
            <section className={card + " space-y-4"}>
              <h2 className="font-semibold mb-1">🫧 {t("rd_tab_canvas")}</h2>
              <p className="text-xs text-muted-foreground mb-4">{t("rd_canvas_note")}</p>
              {isDebate && newsItems.length > 0 && <SocialSignalMap newsItems={newsItems} t={t} />}
              {isDebate ? (
                // debate: scatter จุดยืนต่อ agent รอบสุดท้าย (x=จุดยืน, y=กระจายกัน)
                <DebateScatter posts={data.posts} rounds={data.rounds} t={t} />
              ) : (
                // fabric: สัดส่วนเชื่อรายกลุ่ม baseline vs หลังคำชี้แจง
                <div className="space-y-1.5">
                  {Object.entries((p.scenarios?.[p.scenarios.length - 1]?.belief_by_segment ?? {}) as Record<string, number>).map(([seg, v]) => (
                    <div key={seg} className="flex items-center gap-2 text-xs">
                      <span className="w-44 shrink-0 truncate text-muted-foreground">{seg}</span>
                      <div className="h-3 flex-1 overflow-hidden rounded-full bg-secondary">
                        <div className="h-full bg-primary" style={{ width: `${v * 100}%` }} />
                      </div>
                      <span className="w-10 text-right tabular-nums">{pct(v)}</span>
                    </div>
                  ))}
                </div>
              )}
            </section>
          )}

          {/* เส้นทางหลักฐาน (P6-M6) — debate: เอกสารอ้างอิง; fabric: ร่องรอยกลไก */}
          {tab === "evidence" && (
            <section className={card + " space-y-3"}>
              <h2 className="font-semibold mb-1">🔍 {t("rd_tab_evidence")}</h2>
              {isDebate && (
                <div className="rounded-xl border border-border bg-background p-4">
                  <h3 className="mb-2 text-sm font-semibold">{t("rd_evidence_lineage")}</h3>
                  <EvidenceLineage
                    sources={[...(p.sources ?? []), ...(p.news?.items ?? [])]}
                    subject={data.subject}
                    posts={data.posts}
                    synthesis={p.synthesis?.summary ?? ""}
                  />
                </div>
              )}
              {/* ข่าวจากโต๊ะข่าวสด (P7) — snapshot ที่ agent เห็นจริง พร้อมเวลา+สถานะ PII */}
              {isDebate && p.news?.enabled && (
                <div className="space-y-1.5">
                  <p className="text-xs text-muted-foreground">🌐 {t("rd_news_head")} ({(p.news.items ?? []).length})</p>
                  <div className="flex flex-wrap gap-1 text-[11px] text-muted-foreground">
                    {["ready", "redacted", "blocked", "error", "skipped"].map((s) => (
                      <span key={s} className="rounded-full border border-border bg-background px-2 py-0.5">
                        <StatusIcon status={s} /> {s}: {newsCounts[s] ?? 0}
                      </span>
                    ))}
                  </div>
                  <ul className="space-y-1.5 text-sm">
                    {(p.news.items ?? []).map((n: any, i: number) => (
                      <li key={i} className="rounded-xl border border-border bg-background px-4 py-2.5">
                        <div role="button" tabIndex={0} onClick={() => setSelectedEvidence(n)} onKeyDown={(e) => e.key === "Enter" && setSelectedEvidence(n)} className="w-full text-left">
                        <div className="flex items-center justify-between gap-2">
                          <span className="min-w-0 truncate font-medium">
                            <StatusIcon status={n.status} /> {n.title || n.url}
                          </span>
                          <span className="shrink-0 text-[10px] text-muted-foreground">
                            {n.provider === "search" ? "🔎 search" : "📡 RSS"} · {String(n.fetched_at).slice(0, 16).replace("T", " ")}
                          </span>
                        </div>
                        {n.url && n.provider === "search" && (
                          <a href={n.url} target="_blank" rel="noreferrer" className="text-xs text-primary-strong hover:underline">{n.url}</a>
                        )}
                        {n.error && <div className="mt-1 text-xs text-red-700">{n.error}</div>}
                        <RedactionSummary counts={n.pii_redactions} t={t} />
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {isDebate && (p.evidence_matches ?? []).length > 0 && (
                <div className="space-y-1.5">
                  <p className="text-xs text-muted-foreground">{t("rd_retrieved_highlights")} ({(p.evidence_matches ?? []).length})</p>
                  <ul className="space-y-1.5 text-sm">
                    {(p.evidence_matches ?? []).map((m, i: number) => (
                      <li key={i} className="rounded-xl border border-border bg-background px-4 py-2.5">
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-medium">{m.source_label} #{m.seq}</span>
                          <span className="text-[10px] text-muted-foreground">{t("rd_score_word")} {Number(m.score ?? 0).toFixed(2)} · {t("rd_quality_word")} {Number(m.quality_score ?? 0).toFixed(2)}</span>
                        </div>
                        {(m.citation_spans ?? []).slice(0, 2).map((s: any, j: number) => (
                          <p key={j} className="mt-1 text-xs text-muted-foreground">{s.text}</p>
                        ))}
                        {m.note && <p className="mt-1 text-[11px] text-amber-700">{m.note}</p>}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {isDebate ? (
                (p.sources ?? []).length > 0 ? (
                  <>
                    <p className="text-xs text-muted-foreground">{t("rd_evidence_debate")}</p>
                    <div className="flex flex-wrap gap-1 text-[11px] text-muted-foreground">
                      {["ready", "redacted", "blocked", "error", "empty"].map((s) => (
                        <span key={s} className="rounded-full border border-border bg-background px-2 py-0.5">
                          <StatusIcon status={s} /> {s}: {sourceCounts[s] ?? 0}
                        </span>
                      ))}
                    </div>
                    <ul className="space-y-1.5 text-sm">
                      {(p.sources ?? []).map((s, i: number) => (
                        <li key={i} className="rounded-xl border border-border bg-background px-4 py-2.5">
                          <div role="button" tabIndex={0} onClick={() => setSelectedEvidence(s)} onKeyDown={(e) => e.key === "Enter" && setSelectedEvidence(s)} className="w-full text-left">
                          <div className="flex items-center justify-between">
                            <span className="font-medium"><StatusIcon status={s.status ?? "unknown"} /> {s.label ?? s.title ?? "evidence"}</span>
                            <span className="text-xs text-muted-foreground">{s.chunks} {t("rd_evidence_chunks")}</span>
                          </div>
                          {s.error && <div className="mt-1 text-xs text-red-700">{s.error}</div>}
                          <RedactionSummary counts={s.pii_redactions} t={t} />
                          </div>
                        </li>
                      ))}
                    </ul>
                    <p className="text-xs text-muted-foreground">{t("rd_evidence_used")}: {p.context_used ?? 0}</p>
                  </>
                ) : (
                  <p className="text-sm text-muted-foreground">{t("rd_evidence_none")}</p>
                )
              ) : (
                // fabric: ไม่มี LLM cite — แสดง tipping + ร่องรอยกลไก (ซื่อสัตย์กับ engine จริง)
                <>
                  <p className="text-xs text-muted-foreground">{t("rd_evidence_fabric")}</p>
                  {(p.tipping_points ?? []).length > 0 ? (
                    <ul className="space-y-1 text-sm">
                      {(p.tipping_points ?? []).map((tp: any, i: number) => (
                        <li key={i} className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-amber-800">
                          ⚡ {tp.scenario} · {t("rd_round_word")} {tp.round}: {pct(tp.before)} → {pct(tp.after)} ({tp.delta > 0 ? "+" : ""}{Math.round(tp.delta * 100)}%)
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-sm text-muted-foreground">{t("tipping_none")}</p>
                  )}
                  <p className="text-xs text-muted-foreground">🔗 {t("rd_evidence_trace")}</p>
                </>
              )}
            </section>
          )}

          {tab === "validation" && (
            <section className={card + " space-y-4"} aria-live="polite">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="font-semibold">{t("rd_validation_title")}</h2>
                  <p className="mt-1 text-xs text-muted-foreground">{t("rd_validation_desc")}</p>
                </div>
                <button
                  type="button"
                  disabled={contractBusy || validationQuery.isFetching}
                  onClick={startValidation}
                  className="rounded-xl border border-border px-4 py-2 text-sm hover:bg-muted disabled:opacity-50"
                >
                  {validationQuery.isFetching ? t("rd_validating") : t("rd_validate_seeds")}
                </button>
              </div>
              {!validation && !validationQuery.isFetching && (
                <p className="rounded-xl bg-muted/50 p-4 text-sm text-muted-foreground">
                  {t("rd_no_validation")}
                </p>
              )}
              {validationQuery.error && (
                <p className="rounded-xl border border-red-200 bg-red-50 p-3 text-xs text-red-700">
                  {String((validationQuery.error as Error).message ?? validationQuery.error)}
                </p>
              )}
              {validation && (
                <>
                  <div className="grid gap-2 text-xs sm:grid-cols-4">
                    <div>{t("rd_sign_agreement")} {validation.sign_agreement == null ? "—" : pct(validation.sign_agreement)}</div>
                    <div>{t("rd_dispersion")} {validation.between_run_dispersion.toFixed(3)}</div>
                    <div>{t("rd_failure_rate")} {pct(validation.failure_rate)}</div>
                    <div>{t("rd_cost")} ${validation.total_cost_usd.toFixed(4)}</div>
                  </div>
                  <StabilityMatrix report={validation} />
                </>
              )}
            </section>
          )}

          {tab === "report" && (
            <section className={card + " space-y-3 text-sm"}>
              <h2 className="font-semibold">{t("rd_meta")}</h2>
              <div className="grid grid-cols-[140px_1fr] gap-y-1.5 text-muted-foreground">
                <span>run_id</span><span className="font-mono text-xs text-foreground">{data.run_id}</span>
                <span>engine</span><span className="text-foreground">{data.engine}</span>
                <span>agents</span><span className="text-foreground">{data.agents}</span>
                <span>rounds</span><span className="text-foreground">{data.rounds}</span>
                <span>seed</span><span className="text-foreground">{data.seed} ({t("rd_seed_note")})</span>
                <span>domain</span><span className="text-foreground">{data.domain}</span>
                <span>parent</span><span className="font-mono text-xs text-foreground">{data.parent_run_id || "none"}</span>
                <span>manifest</span><span className="break-all font-mono text-xs text-foreground">{data.manifest?.manifest_hash || "legacy-incomplete"}</span>
                <span>reproducibility</span><span className="text-foreground">{data.manifest?.reproducibility || "legacy-incomplete"}</span>
              </div>
              {(data.events ?? []).length > 0 && (
                <div>
                  <div className="text-xs uppercase tracking-wider text-muted-foreground">{t("rd_audit_trail")}</div>
                  <ul className="mt-1 space-y-1 text-xs">
                    {(data.events ?? []).slice(-8).map((e, i) => (
                      <li key={i} className="rounded-lg border border-border bg-background px-3 py-2">
                        <span className="font-mono text-muted-foreground">{e.created_at.slice(0, 16).replace("T", " ")}</span>
                        <span className="mx-2 font-medium">{e.event_type}</span>
                        <span className="text-muted-foreground">{e.message}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {isDebate && (p.sources ?? []).length > 0 && (
                <div>
                  <div className="text-xs uppercase tracking-wider text-muted-foreground">{t("rd_sources")}</div>
                  <ul className="mt-1 space-y-1 text-xs">
                    {(p.sources ?? []).map((s, i: number) => (
                      <li key={i}>
                        {s.status === "ready" ? "✅" : s.status === "blocked" ? "⛔" : "⚠️"} {s.label} — {s.status}
                        {s.error && <span className="text-red-700"> ({s.error})</span>}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <p className="text-xs text-muted-foreground">📌 {t("rd_prediction_note")}</p>
              <div className="flex flex-wrap items-center gap-2">
                <a className="inline-block rounded-xl bg-primary px-5 py-2.5 text-sm font-medium text-white" href={`/runs/${encodeURIComponent(runId)}/export.pdf?lang=${lang}`}>
                  ⬇ {t("rd_pdf_snapshot")}
                </a>
                <a className="inline-block rounded-xl border border-border px-5 py-2.5 text-sm font-medium" href={`/runs/${encodeURIComponent(runId)}/export.json`}>
                  ⬇ {t("rd_json_snapshot")}
                </a>
              </div>
              <div className="rounded-xl border border-primary/20 bg-primary/5 p-3 text-xs text-primary-strong">
                {t("rd_rerun_note")}
              </div>
              <div className="flex flex-wrap gap-2">
                {data.manifest?.complete && (
                  <button type="button" disabled={!!runActionBusy} onClick={() => rerun("frozen")} className="rounded-xl border border-border px-4 py-2 text-sm disabled:opacity-50">
                    {t("rd_rerun_frozen")}
                  </button>
                )}
                <button type="button" disabled={!!runActionBusy} onClick={() => rerun("latest")} className="rounded-xl border border-border px-4 py-2 text-sm disabled:opacity-50">
                  {t("rd_run_latest")}
                </button>
              </div>
              <button
                onClick={() => { setShareErr(""); setShareOpen(true); }}
                className="inline-flex items-center gap-2 rounded-xl border border-border px-5 py-2.5 text-sm text-muted-foreground hover:bg-muted"
              >
                {data.share_token ? "🌐" : "🔒"} {t("share_btn")}
                {data.share_token && <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-medium text-primary-strong">{t("share_public")}</span>}
              </button>
            </section>
          )}
        </>
      )}

      <EvidenceDrawer item={selectedEvidence} onClose={() => setSelectedEvidence(null)} t={t} />

      {/* Share dialog (แบบ studio): toggle เปิด/ปิด + copy link — governance ADR-0004 อยู่ฝั่ง API */}
      {shareOpen && data && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4 backdrop-blur-[2px]" onClick={() => setShareOpen(false)}>
          <div role="dialog" aria-modal="true" className="w-full max-w-md rounded-2xl border border-border bg-card p-6 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="font-display text-2xl font-semibold">🌐 {t("share_title")}</h3>
            <p className="mt-1 text-sm text-muted-foreground">{t("share_desc")}</p>
            <div className="mt-4 flex items-center justify-between rounded-xl border border-border bg-background p-3 text-sm">
              <span className="flex items-center gap-2">
                {data.share_token ? "🌐" : "🔒"}
                <span>{data.share_token ? t("share_on") : t("share_off")}</span>
              </span>
              <button
                disabled={shareBusy}
                onClick={async () => {
                  setShareBusy(true);
                  setShareErr("");
                  try {
                    if (data.share_token) await unshareRun(runId);
                    else await shareRun(runId);
                    await reload();
                  } catch (e: any) {
                    setShareErr(String(e.message ?? e));
                  } finally {
                    setShareBusy(false);
                  }
                }}
                className={`rounded-lg px-3 py-1.5 text-xs font-medium disabled:opacity-50 ${
                  data.share_token
                    ? "border border-border text-muted-foreground hover:bg-muted"
                    : "bg-primary text-white hover:bg-primary-strong"
                }`}
              >
                {shareBusy ? "⏳" : data.share_token ? t("share_turn_off") : t("share_turn_on")}
              </button>
            </div>
            {shareErr && <p className="mt-2 text-xs text-red-700">{shareErr}</p>}
            {data.share_token && (
              <div className="mt-3 flex gap-2">
                <input
                  readOnly
                  value={`${window.location.origin}/app/#/gallery/${data.share_token}`}
                  className="flex-1 rounded-lg border border-border bg-background px-3 py-2 text-xs"
                />
                <button
                  onClick={() => {
                    navigator.clipboard.writeText(`${window.location.origin}/app/#/gallery/${data.share_token}`);
                    setCopied(true);
                    setTimeout(() => setCopied(false), 1500);
                  }}
                  className="rounded-lg border border-border px-3 py-2 text-xs hover:bg-muted"
                >
                  {copied ? "✅" : "📋"} {t("share_copy")}
                </button>
              </div>
            )}
            <p className="mt-3 text-[11px] text-muted-foreground">🛡️ {t("share_gov_note")}</p>
            <button onClick={() => setShareOpen(false)} className="mt-4 w-full rounded-xl border border-border py-2 text-sm text-muted-foreground hover:bg-muted">
              {t("close")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
