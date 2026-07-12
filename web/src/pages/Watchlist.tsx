import { useEffect, useState } from "react";
import {
  WatchlistData,
  createWatchlist,
  fetchWatchlists,
  markAlertsRead,
  runWatchlistNow,
  toggleWatchlist,
} from "../api";
import { useLang } from "../i18n";
import { InfoTip, PageHeader } from "../ui";

// หน้า Watchlist (P5-M5) — subscribe หัวข้อ → re-run ตาม cadence → alert เมื่อกระแสพลิก

export default function Watchlist({ onChanged }: { onChanged?: () => void }) {
  const { t } = useLang();
  const [data, setData] = useState<WatchlistData | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<number | null>(null);
  const [form, setForm] = useState<{
    label: string;
    subject: string;
    agents: number;
    cadence: "daily" | "weekly";
  }>({ label: "", subject: "", agents: 100, cadence: "daily" });

  const load = () =>
    fetchWatchlists()
      .then((d) => {
        setData(d);
        setError("");
        onChanged?.();
      })
      .catch((e) => setError(String(e.message ?? e)));
  useEffect(() => {
    load();
  }, []);

  const card = "bg-card border border-border rounded-2xl p-6";

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (form.subject.trim().length < 4) return;
    try {
      await createWatchlist({ ...form, label: form.label.trim(), subject: form.subject.trim() });
      setForm({ label: "", subject: "", agents: 100, cadence: "daily" });
      await load();
    } catch (er: any) {
      setError(String(er.message ?? er));
    }
  }

  async function runNow(id: number) {
    setBusy(id);
    try {
      await runWatchlistNow(id);
      await load();
    } catch (er: any) {
      setError(String(er.message ?? er));
    } finally {
      setBusy(null);
    }
  }

  const kindLabel: Record<string, string> = {
    tipping_point: t("wl_kind_tipping"),
    consensus_shift: t("wl_kind_shift"),
  };

  return (
    <div className="space-y-6">
      <PageHeader eyebrow={t("wl_eyebrow")} title={t("wl_title")} desc={t("wl_sub")} />

      {error && <div className="bg-red-50 border border-red-200 text-red-700 rounded-2xl p-5 text-sm">{error}</div>}

      {/* สร้างใหม่ */}
      <form onSubmit={submit} className={card + " space-y-3"}>
        <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t("wl_new")}</div>
        <div className="grid gap-2 sm:grid-cols-[1fr_180px]">
          <input
            value={form.subject}
            onChange={(e) => setForm({ ...form, subject: e.target.value })}
            placeholder={t("wl_subject_ph")}
            className="rounded-xl border border-border bg-background px-4 py-2.5 text-sm"
          />
          <input
            value={form.label}
            onChange={(e) => setForm({ ...form, label: e.target.value })}
            placeholder={t("wl_label_ph")}
            className="rounded-xl border border-border bg-background px-4 py-2.5 text-sm"
          />
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {(["daily", "weekly"] as const).map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => setForm({ ...form, cadence: c })}
              className={`rounded-full border px-3 py-1 text-xs ${
                form.cadence === c ? "border-primary bg-primary/5 text-primary-strong font-medium" : "border-border text-muted-foreground"
              }`}
            >
              {c === "daily" ? t("wl_daily") : t("wl_weekly")}
            </button>
          ))}
          <span className="text-xs text-muted-foreground">· {form.agents} agents</span>
          <button
            type="submit"
            disabled={form.subject.trim().length < 4}
            className="ml-auto rounded-xl bg-primary px-5 py-2 text-sm font-medium text-white disabled:opacity-40"
          >
            + {t("wl_add")}
          </button>
        </div>
        <p className="text-xs text-muted-foreground">
          {data?.webhook_configured ? `🔗 ${t("wl_webhook_on")}` : `⚙️ ${t("wl_webhook_off")}`}
        </p>
      </form>

      {/* รายการ */}
      {data && (
        <div className={card}>
          <h2 className="font-semibold mb-3">
            {t("wl_list")} <InfoTip text={t("tip_shift")} />
          </h2>
          {data.items.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("wl_empty")}</p>
          ) : (
            <ul className="space-y-2">
              {data.items.map((w) => (
                <li key={w.id} className="rounded-xl border border-border bg-background p-4 text-sm">
                  <div className="flex items-center justify-between gap-3 flex-wrap">
                    <div className="min-w-0 flex-1">
                      <div className="font-medium">{w.label}</div>
                      <div className="mt-0.5 text-xs text-muted-foreground truncate">{w.subject}</div>
                      <div className="mt-1 text-xs text-muted-foreground">
                        {w.cadence === "daily" ? t("wl_daily") : t("wl_weekly")} · {w.agents} agents ·{" "}
                        {w.last_run_at
                          ? `${t("wl_last_run")} ${w.last_run_at.slice(0, 16).replace("T", " ")} · Δ ${
                              w.last_delta == null ? "—" : (w.last_delta * 100).toFixed(1) + "%"
                            }`
                          : t("wl_never_run")}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => runNow(w.id)}
                        disabled={busy === w.id || !w.active}
                        className="rounded-lg border border-border px-3 py-1.5 text-xs hover:bg-muted disabled:opacity-40"
                      >
                        {busy === w.id ? "⏳" : `▶ ${t("wl_run_now")}`}
                      </button>
                      <button
                        onClick={() => toggleWatchlist(w.id, !w.active).then(load)}
                        className={`rounded-full border px-3 py-1.5 text-xs ${
                          w.active ? "border-primary/40 bg-primary/5 text-primary-strong" : "border-border text-muted-foreground"
                        }`}
                      >
                        {w.active ? t("wl_active") : t("wl_paused")}
                      </button>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Alerts feed */}
      {data && (
        <div className={card}>
          <div className="flex items-center justify-between">
            <h2 className="font-semibold">
              🔔 {t("wl_alerts")} {data.unread > 0 && <span className="text-xs text-primary-strong">({data.unread} {t("wl_unread")})</span>}
            </h2>
            {data.unread > 0 && (
              <button onClick={() => markAlertsRead().then(load)} className="text-xs text-muted-foreground hover:text-foreground">
                {t("wl_mark_all")}
              </button>
            )}
          </div>
          {data.alerts.length === 0 ? (
            <p className="mt-3 text-sm text-muted-foreground">{t("wl_no_alerts")}</p>
          ) : (
            <ul className="mt-3 space-y-1.5 text-sm">
              {data.alerts.map((a) => (
                <li
                  key={a.id}
                  className={`flex items-start gap-2 rounded-lg border px-3 py-2 ${
                    a.read ? "border-border/50 text-muted-foreground" : "border-primary/30 bg-primary/5"
                  }`}
                >
                  <span className="shrink-0">{a.kind === "tipping_point" ? "⚡" : "📈"}</span>
                  <span className="min-w-0 flex-1">
                    <b>{kindLabel[a.kind] ?? a.kind}</b> — {a.payload?.subject ?? ""}
                    {a.kind === "consensus_shift" && a.payload?.shift != null && (
                      <span className="tabular-nums"> ({a.payload.shift > 0 ? "+" : ""}{(a.payload.shift * 100).toFixed(1)} {t("cmp_points")})</span>
                    )}
                    <span className="block text-xs opacity-70">{a.ts.slice(0, 16).replace("T", " ")}</span>
                  </span>
                  {!a.read && (
                    <button onClick={() => markAlertsRead(a.id).then(load)} className="shrink-0 text-xs text-muted-foreground hover:text-foreground">
                      ✓
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
