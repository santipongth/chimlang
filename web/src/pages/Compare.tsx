import { useEffect, useState } from "react";
import { CompareData, fetchCompare, pct } from "../api";
import { useLang } from "../i18n";
import { InfoTip, PageHeader } from "../ui";
import type { RunRequest } from "../App";

// หน้า Compare (P5-M4) ตาม studio: delta banner + 2 panes + CalculationModal
// baseline vs +Red Team ด้วย seed เดียวกัน — ความต่างอธิบายได้จาก red team เท่านั้น

function Pane({
  title,
  side,
  tone,
  t,
}: {
  title: string;
  side: CompareData["baseline"];
  tone: "base" | "rt";
  t: (k: string) => string;
}) {
  const [lo, hi] = side.ci95;
  return (
    <div className={`rounded-2xl border p-5 ${tone === "rt" ? "border-red-200 bg-red-50/40" : "border-border bg-card"}`}>
      <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{title}</div>
      <div className="mt-2 font-display text-3xl font-semibold tabular-nums">
        {(side.mean_delta * 100).toFixed(1)}%
      </div>
      <div className="text-xs text-muted-foreground">
        {t("cmp_delta_label")} · CI95 [{(lo * 100).toFixed(1)}%, {(hi * 100).toFixed(1)}%]
      </div>
      <div className="mt-1 text-sm">
        {t("cmp_conclusion")}: <b>{side.conclusion}</b>
      </div>
      <div className="mt-4 space-y-1.5">
        {Object.entries(side.belief_by_segment).map(([seg, v]) => (
          <div key={seg} className="flex items-center gap-2 text-xs">
            <span className={`w-40 shrink-0 truncate ${seg.includes("Red Team") ? "text-red-700 font-medium" : "text-muted-foreground"}`}>
              {seg}
            </span>
            <div className="h-2 flex-1 overflow-hidden rounded-full bg-secondary">
              <div
                className={`h-full ${seg.includes("Red Team") ? "bg-red-400" : "bg-primary"}`}
                style={{ width: `${v * 100}%` }}
              />
            </div>
            <span className="w-10 shrink-0 text-right tabular-nums">{pct(v)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function Compare({ request }: { request: RunRequest | null }) {
  const { t } = useLang();
  const [data, setData] = useState<CompareData | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [calcOpen, setCalcOpen] = useState(false);

  useEffect(() => {
    if (!request) return;
    setLoading(true);
    setError("");
    fetchCompare(request.subject, request.agents)
      .then(setData)
      .catch((e) => setError(String(e.message ?? e)))
      .finally(() => setLoading(false));
  }, [request]);

  if (!request)
    return <p className="py-24 text-center text-muted-foreground">{t("cmp_empty")}</p>;

  const dd = data?.delta_of_delta ?? 0;
  const icon = data ? (Math.abs(dd) < 0.02 ? "→" : dd > 0 ? "▲" : "▼") : "";

  return (
    <div className="space-y-6">
      <PageHeader eyebrow={t("cmp_eyebrow")} title={request.subject} desc={t("cmp_sub")} />

      {loading && (
        <div className="bg-card border border-border rounded-2xl p-6 text-center text-muted-foreground animate-pulse">
          ⏳ {t("running")}
        </div>
      )}
      {error && <div className="bg-red-50 border border-red-200 text-red-700 rounded-2xl p-5 text-sm">{error}</div>}

      {data && (
        <>
          {/* Delta banner */}
          <section
            className={`rounded-2xl border p-5 ${
              data.robust ? "border-primary/30 bg-primary-soft" : "border-red-200 bg-red-50"
            }`}
          >
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <div>
                <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  {t("cmp_banner_label")} <InfoTip text={t("tip_dd")} />
                </div>
                <div className="mt-1 font-display text-3xl font-semibold tabular-nums">
                  {icon} {dd > 0 ? "+" : ""}
                  {(dd * 100).toFixed(1)} {t("cmp_points")}
                </div>
                <p className="mt-1 text-sm">
                  {data.robust ? `✅ ${t("cmp_robust")}` : `⚠️ ${t("cmp_flipped")}`}
                </p>
              </div>
              <button
                onClick={() => setCalcOpen(true)}
                className="rounded-xl border border-border bg-card px-4 py-2 text-sm text-muted-foreground hover:bg-muted"
              >
                🧮 {t("cmp_calc_btn")}
              </button>
            </div>
          </section>

          <div className="grid gap-4 md:grid-cols-2">
            <Pane title={t("cmp_pane_base")} side={data.baseline} tone="base" t={t} />
            <Pane title={t("cmp_pane_rt")} side={data.red_team} tone="rt" t={t} />
          </div>

          <p className="text-xs text-muted-foreground">🛡️ {data.note}</p>

          {/* CalculationModal — คณิตโปร่งใสทุกขั้น (TRUST-09/NFR-08) */}
          {calcOpen && (
            <div className="fixed inset-0 z-50 grid place-items-center bg-black/30 p-4" onClick={() => setCalcOpen(false)}>
              <div
                className="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-border bg-card p-6"
                onClick={(e) => e.stopPropagation()}
              >
                <div className="flex items-center justify-between">
                  <h3 className="font-display text-2xl font-semibold">{t("cmp_calc_title")}</h3>
                  <button onClick={() => setCalcOpen(false)} className="text-muted-foreground hover:text-foreground">✕</button>
                </div>
                <div className="mt-3 space-y-2 text-sm">
                  <p className="text-muted-foreground">{t("cmp_calc_how")}</p>
                  <ul className="list-disc pl-5 text-xs text-muted-foreground space-y-1">
                    <li>seeds: {data.seeds.join(", ")} ({t("cmp_same_seed")})</li>
                    <li>agents: {data.agents} · rounds: {data.rounds}</li>
                    <li>{t("cmp_formula")}</li>
                  </ul>
                  <table className="w-full text-xs mt-3">
                    <thead>
                      <tr className="text-left text-muted-foreground border-b border-border">
                        <th className="py-1.5 font-medium">{t("cmp_col_seg")}</th>
                        <th className="py-1.5 font-medium">baseline</th>
                        <th className="py-1.5 font-medium">+Red Team</th>
                        <th className="py-1.5 font-medium">Δ</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.keys({ ...data.baseline.belief_by_segment, ...data.red_team.belief_by_segment }).map(
                        (seg) => {
                          const a = data.baseline.belief_by_segment[seg];
                          const b = data.red_team.belief_by_segment[seg];
                          const d = a != null && b != null ? b - a : null;
                          return (
                            <tr key={seg} className="border-b border-border/50">
                              <td className="py-1.5 pr-2">{seg}</td>
                              <td className="py-1.5 tabular-nums">{a == null ? "—" : pct(a)}</td>
                              <td className="py-1.5 tabular-nums">{b == null ? "—" : pct(b)}</td>
                              <td className={`py-1.5 tabular-nums ${d != null && d > 0.02 ? "text-red-700" : d != null && d < -0.02 ? "text-primary-strong" : ""}`}>
                                {d == null ? "—" : `${d > 0 ? "+" : ""}${Math.round(d * 100)}%`}
                              </td>
                            </tr>
                          );
                        },
                      )}
                    </tbody>
                  </table>
                  <div className="rounded-lg bg-muted p-3 text-xs text-muted-foreground">
                    delta_of_delta = mean_delta(+RedTeam) − mean_delta(baseline) ={" "}
                    {(data.red_team.mean_delta * 100).toFixed(1)}% − {(data.baseline.mean_delta * 100).toFixed(1)}% ={" "}
                    <b>{(dd * 100).toFixed(1)} {t("cmp_points")}</b>
                  </div>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
