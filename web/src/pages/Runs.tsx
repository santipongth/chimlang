import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clock3,
  Loader2,
  RotateCcw,
  Search,
  Square,
  Trash2,
} from "lucide-react";
import {
  RunMetrics,
  RunsData,
  SimRunSummary,
  cancelRun,
  deleteRun,
  fetchRunMetrics,
  fetchRuns,
  fetchSimRuns,
  retryRun,
} from "../api";
import { useLang } from "../i18n";
import { ConfirmDialog, PageHeader } from "../ui";

function statusIcon(status: SimRunSummary["status"]) {
  if (status === "complete") return <CheckCircle2 className="h-4 w-4 text-primary" />;
  if (status === "error") return <AlertTriangle className="h-4 w-4 text-red-600" />;
  if (status === "canceled") return <Square className="h-4 w-4 text-muted-foreground" />;
  if (status === "running") return <Loader2 className="h-4 w-4 animate-spin text-primary" />;
  return <Clock3 className="h-4 w-4 text-amber-600" />;
}

function statusClass(status: SimRunSummary["status"]) {
  if (status === "complete") return "border-primary/25 bg-primary/5 text-primary-strong";
  if (status === "error") return "border-red-200 bg-red-50 text-red-700";
  if (status === "canceled") return "border-border bg-muted text-muted-foreground";
  if (status === "running") return "border-primary/25 bg-primary/5 text-primary-strong";
  return "border-amber-200 bg-amber-50 text-amber-700";
}

const fmtSeconds = (n: number) => (n < 60 ? `${Math.round(n)}s` : `${Math.round(n / 60)}m`);

export default function Runs({ onOpen }: { onOpen: (runId: string) => void }) {
  const { t } = useLang();
  const [runs, setRuns] = useState<SimRunSummary[]>([]);
  const [metrics, setMetrics] = useState<RunMetrics | null>(null);
  const [legacy, setLegacy] = useState<RunsData | null>(null);
  const [search, setSearch] = useState("");
  const [engine, setEngine] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [runToDelete, setRunToDelete] = useState<string | null>(null);
  const [busyRun, setBusyRun] = useState("");
  const [loading, setLoading] = useState(true);

  const activeCount = useMemo(
    () => runs.filter((r) => r.status === "queued" || r.status === "running").length,
    [runs],
  );

  const load = () => {
    setLoading(true);
    return Promise.all([
      fetchSimRuns(search, engine, status),
      fetchRunMetrics().catch(() => null),
    ])
      .then(([r, m]) => {
        setRuns(r);
        setMetrics(m);
        setError("");
      })
      .catch((e) => setError(String(e.message ?? e)))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, [search, engine, status]);

  useEffect(() => {
    fetchRuns().then(setLegacy).catch(() => {});
  }, []);

  useEffect(() => {
    if (!activeCount) return;
    const timer = setInterval(load, 3500);
    return () => clearInterval(timer);
  }, [activeCount, search, engine, status]);

  async function removeConfirmed() {
    const runId = runToDelete;
    setRunToDelete(null);
    if (!runId) return;
    try {
      await deleteRun(runId);
      await load();
    } catch (e: any) {
      setError(String(e.message ?? e));
    }
  }

  async function action(runId: string, fn: () => Promise<any>) {
    setBusyRun(runId);
    setError("");
    try {
      await fn();
      await load();
    } catch (e: any) {
      setError(String(e.message ?? e));
    } finally {
      setBusyRun("");
    }
  }

  const card = "bg-card border border-border rounded-2xl p-6";
  const statusItems = ["", "queued", "running", "complete", "error", "canceled"] as const;

  return (
    <div className="space-y-6">
      <PageHeader eyebrow={t("hist_eyebrow")} title={t("runs_job_title")} desc={t("hist_sub")} />
      {error && <div className="rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-700">{error}</div>}

      <section className="grid gap-3 md:grid-cols-4">
        {[
          [t("runs_metric_active"), activeCount, <Activity className="h-4 w-4" />],
          [t("runs_metric_queue"), fmtSeconds(metrics?.avg_queue_wait_s ?? 0), <Clock3 className="h-4 w-4" />],
          [t("runs_metric_runtime"), fmtSeconds(metrics?.avg_runtime_s ?? 0), <Loader2 className="h-4 w-4" />],
          [t("runs_metric_spend"), `$${(metrics?.spent_this_month ?? 0).toFixed(2)}`, <CheckCircle2 className="h-4 w-4" />],
        ].map(([label, value, icon]) => (
          <div key={String(label)} className="rounded-2xl border border-border bg-card p-4">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>{label}</span>
              {icon}
            </div>
            <div className="mt-2 text-2xl font-semibold tabular-nums">{value}</div>
          </div>
        ))}
      </section>

      <div className="flex flex-wrap items-center gap-2">
        <label className="flex w-72 items-center gap-2 rounded-xl border border-border bg-card px-3 py-2 text-sm">
          <Search className="h-4 w-4 text-muted-foreground" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t("hist_search_ph")}
            className="min-w-0 flex-1 bg-transparent outline-none"
          />
        </label>
        <div className="inline-flex rounded-lg border border-border bg-card p-1 text-xs">
          {([["", t("ins_all")], ["fabric", "Fabric"], ["debate", "Debate"]] as const).map(([k, label]) => (
            <button
              key={k}
              onClick={() => setEngine(k)}
              className={`rounded-md px-3 py-1 ${engine === k ? "bg-primary text-white" : "text-muted-foreground hover:text-foreground"}`}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="inline-flex flex-wrap rounded-lg border border-border bg-card p-1 text-xs">
          {statusItems.map((s) => (
            <button
              key={s || "all"}
              onClick={() => setStatus(s)}
              className={`rounded-md px-3 py-1 ${status === s ? "bg-primary text-white" : "text-muted-foreground hover:text-foreground"}`}
            >
              {s || t("ins_all")}
            </button>
          ))}
        </div>
      </div>

      {loading && runs.length === 0 ? (
        <div className="space-y-2">
          {[0, 1, 2].map((i) => (
            <div key={i} className={card + " !p-4 animate-pulse"}>
              <div className="h-4 w-52 rounded bg-muted" />
              <div className="mt-3 h-5 w-2/3 rounded bg-muted" />
              <div className="mt-3 h-2 rounded bg-muted" />
            </div>
          ))}
        </div>
      ) : runs.length === 0 ? (
        <p className="py-10 text-center text-sm text-muted-foreground">{t("hist_empty")}</p>
      ) : (
        <div className="space-y-2">
          {runs.map((r) => {
            const p = r.progress ?? (r.status === "complete" ? 100 : 0);
            const canCancel = r.status === "queued" || r.status === "running";
            const canRetry = r.status === "error" || r.status === "canceled";
            return (
              <div key={r.run_id} className={card + " !p-4 transition hover:bg-muted/40"}>
                <div className="flex items-start justify-between gap-3">
                  <button onClick={() => onOpen(r.run_id)} className="min-w-0 flex-1 text-left">
                    <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                      <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 ${statusClass(r.status)}`}>
                        {statusIcon(r.status)} {r.status}
                      </span>
                      <span>{r.engine}</span>
                      <span>{r.created_at.slice(0, 16).replace("T", " ")}</span>
                      <span>{r.agents} agents</span>
                    </div>
                    <div className="mt-1 truncate font-medium">{r.subject}</div>
                    <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-secondary">
                      <div className="h-full bg-primary" style={{ width: `${Math.max(0, Math.min(100, p))}%` }} />
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      {p}% {r.progress_message ? `· ${r.progress_message}` : ""}
                    </div>
                  </button>
                  <div className="flex shrink-0 gap-1">
                    {canCancel && (
                      <button
                        disabled={busyRun === r.run_id}
                        onClick={() => action(r.run_id, () => cancelRun(r.run_id))}
                        className="rounded-lg border border-border p-2 text-muted-foreground hover:bg-amber-50 hover:text-amber-700 disabled:opacity-40"
                        title="Cancel"
                      >
                        <Square className="h-4 w-4" />
                      </button>
                    )}
                    {canRetry && (
                      <button
                        disabled={busyRun === r.run_id}
                        onClick={() => action(r.run_id, () => retryRun(r.run_id))}
                        className="rounded-lg border border-border p-2 text-muted-foreground hover:bg-primary/5 hover:text-primary-strong disabled:opacity-40"
                        title="Retry"
                      >
                        <RotateCcw className="h-4 w-4" />
                      </button>
                    )}
                    <button
                      onClick={() => setRunToDelete(r.run_id)}
                      className="rounded-lg border border-border p-2 text-muted-foreground hover:bg-red-50 hover:text-red-600"
                      title={t("hist_delete")}
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {metrics && (
        <section className={card + " space-y-3"}>
          <h2 className="font-semibold">{t("runs_evidence_health")}</h2>
          {(metrics.runs_24h ?? []).length > 0 && (
            <div>
              <div className="mb-2 text-xs text-muted-foreground">24h run trend</div>
              <div className="flex h-16 items-end gap-1 rounded-xl border border-border bg-background p-2">
                {metrics.runs_24h.slice(-24).map((x, i) => (
                  <div
                    key={`${x.hour}-${x.status}-${i}`}
                    className={`min-w-2 flex-1 rounded-t ${x.status === "error" ? "bg-red-400" : x.status === "complete" ? "bg-primary" : "bg-amber-400"}`}
                    style={{ height: `${Math.max(8, Math.min(100, x.count * 18))}%` }}
                    title={`${x.hour.slice(11, 16)} ${x.status}: ${x.count}`}
                  />
                ))}
              </div>
            </div>
          )}
          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <div className="text-xs text-muted-foreground">{t("runs_sources")}</div>
              <div className="mt-1 flex flex-wrap gap-1 text-xs">
                {Object.entries(metrics.sources_by_status).map(([k, v]) => (
                  <span key={k} className="rounded-full border border-border px-2 py-0.5">{k}: {v}</span>
                ))}
              </div>
            </div>
            <div>
              <div className="text-xs text-muted-foreground">{t("runs_newsdesk")}</div>
              <div className="mt-1 flex flex-wrap gap-1 text-xs">
                {Object.entries(metrics.news_by_status).map(([k, v]) => (
                  <span key={k} className="rounded-full border border-border px-2 py-0.5">{k}: {v}</span>
                ))}
              </div>
            </div>
          </div>
        </section>
      )}

      {legacy && legacy.due.length > 0 && (
        <section className={card}>
          <h2 className="mb-3 font-semibold">{t("runs_due_title")}</h2>
          <ul className="space-y-2 text-sm">
            {legacy.due.map((d) => (
              <li key={d.prediction_id} className="rounded-xl border border-border px-4 py-2.5">
                <span className="mr-2 rounded-full bg-muted px-2 py-0.5 text-xs">#{d.prediction_id}</span>
                <span className="mr-2 text-xs text-muted-foreground">{d.domain} · due {d.due_date}</span>
                {d.claim}
              </li>
            ))}
          </ul>
          <p className="mt-3 text-xs text-muted-foreground">→ {t("hist_due_note")}</p>
        </section>
      )}

      <ConfirmDialog
        open={runToDelete != null}
        title={t("hist_delete_title")}
        message={t("hist_delete_confirm")}
        confirmLabel={t("hist_delete_ok")}
        cancelLabel={t("confirm_cancel")}
        danger
        onCancel={() => setRunToDelete(null)}
        onConfirm={removeConfirmed}
      />
    </div>
  );
}
