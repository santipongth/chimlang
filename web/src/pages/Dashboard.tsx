import { useEffect, useState } from "react";
import { DashboardData, fetchDashboard, pct, shareToGallery } from "../api";
import { useLang } from "../i18n";
import { InfoTip, PageHeader, Tabs } from "../ui";
import type { RunRequest } from "../App";

type Tab = "overview" | "voices" | "report";

// Opinion canvas ระดับ segment (SIM-09: ห้ามลึกกว่า segment): x = เชื่อใน baseline,
// y = เชื่อหลังมีคำชี้แจง, ขนาดฟอง = สัดส่วนประชากร — ใต้เส้นทแยง = คำชี้แจงได้ผล
function SegmentCanvas({
  scenarios,
  popShare,
  labels,
}: {
  scenarios: DashboardData["scenarios"];
  popShare: DashboardData["voice_population_share"];
  labels: { title: string; note: string; x: string; y: string };
}) {
  if (scenarios.length < 2) return null;
  const [base, variant] = scenarios;
  const segs = Object.keys(base.belief_by_segment);
  const W = 560;
  const H = 320;
  const P = 44;
  const sx = (v: number) => P + v * (W - P * 2);
  const sy = (v: number) => H - P - v * (H - P * 2);
  const share = (seg: string) => popShare.find((p) => p.segment === seg)?.population_share ?? 0.1;
  const colors = ["var(--color-chart-1)", "var(--color-chart-2)", "var(--color-chart-3)", "var(--color-chart-4)", "var(--color-chart-5)"];
  return (
    <div className="bg-card border border-border rounded-2xl p-6">
      <h2 className="font-semibold mb-1">{labels.title}</h2>
      <p className="text-xs text-muted-foreground mb-3">{labels.note}</p>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto">
        {/* กรอบ + เส้นทแยง (ไม่เปลี่ยน) */}
        <rect x={P} y={P} width={W - P * 2} height={H - P * 2} fill="none" stroke="var(--color-border)" />
        <line x1={sx(0)} y1={sy(0)} x2={sx(1)} y2={sy(1)} stroke="var(--color-border)" strokeDasharray="4,4" />
        <text x={W / 2} y={H - 10} textAnchor="middle" fontSize="10" fill="var(--color-muted-foreground)">
          {labels.x} →
        </text>
        <text x={14} y={H / 2} textAnchor="middle" fontSize="10" fill="var(--color-muted-foreground)" transform={`rotate(-90 14 ${H / 2})`}>
          {labels.y} →
        </text>
        {[0, 0.5, 1].map((v) => (
          <g key={v}>
            <text x={sx(v)} y={H - P + 14} textAnchor="middle" fontSize="9" fill="var(--color-muted-foreground)">
              {Math.round(v * 100)}%
            </text>
            <text x={P - 8} y={sy(v) + 3} textAnchor="end" fontSize="9" fill="var(--color-muted-foreground)">
              {Math.round(v * 100)}%
            </text>
          </g>
        ))}
        {segs.map((seg, i) => {
          const x = base.belief_by_segment[seg] ?? 0;
          const y = variant.belief_by_segment[seg] ?? 0;
          const r = 8 + share(seg) * 40;
          return (
            <g key={seg}>
              <circle cx={sx(x)} cy={sy(y)} r={r} fill={colors[i % colors.length]} fillOpacity={0.55} stroke="white" strokeWidth={1.5}>
                <title>{`${seg}\n${labels.x}: ${Math.round(x * 100)}% → ${labels.y}: ${Math.round(y * 100)}%`}</title>
              </circle>
              <text x={sx(x)} y={sy(y) - r - 4} textAnchor="middle" fontSize="10" fill="var(--color-foreground)">
                {seg}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function FragilityBadge({ index, label, tip }: { index: number; label: string; tip: string }) {
  const cls =
    index > 70
      ? "bg-red-50 text-red-700 border-red-200"
      : index > 40
        ? "bg-amber-50 text-amber-700 border-amber-200"
        : "bg-primary-soft text-primary-strong border-primary/30";
  return (
    <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium border ${cls}`} title={tip}>
      Fragility {index}/100 — {label} <span className="opacity-60">ⓘ</span>
    </span>
  );
}

export default function Dashboard({
  request,
  result,
  setResult,
  onNew,
}: {
  request: RunRequest | null;
  result: DashboardData | null;
  setResult: (d: DashboardData | null) => void;
  onNew: () => void;
}) {
  const { t } = useLang();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState<Tab>("overview");
  const [shareState, setShareState] = useState<"idle" | "busy" | "done" | string>("idle");

  useEffect(() => {
    if (request && !result) {
      setLoading(true);
      setError("");
      fetchDashboard(request.subject, request.agents, request.packId)
        .then(setResult)
        .catch((e) => setError(String(e.message ?? e)))
        .finally(() => setLoading(false));
    }
  }, [request]);

  const card = "bg-card border border-border rounded-2xl p-6";

  if (!request && !result)
    return (
      <div className="text-center py-24">
        <p className="text-muted-foreground mb-4">{t("dash_empty")}</p>
        <button onClick={onNew} className="bg-primary text-white px-5 py-2.5 rounded-xl text-sm">
          {t("nav_new_run")} →
        </button>
      </div>
    );

  const segments = result ? Object.keys(result.scenarios[0]?.belief_by_segment ?? {}) : [];
  const [lo, hi] = result?.brief.headline_range ?? [0, 0];
  const subject = request?.subject ?? result?.subject ?? "";
  const agents = request?.agents ?? 100;

  return (
    <div className="space-y-6">
      <PageHeader eyebrow={t("dash_eyebrow")} title={subject} />

      {loading && (
        <div className={card + " text-center text-muted-foreground animate-pulse"}>⏳ {t("running")}</div>
      )}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-2xl p-5 text-sm">
          {error.includes("election") ? `🗳️ ${error}` : error}
        </div>
      )}

      {result && (
        <>
          <section className={card + " space-y-3"}>
            <div className="flex items-center justify-between flex-wrap gap-2">
              <h2 className="font-semibold">{t("brief_title")}</h2>
              <FragilityBadge
                index={result.brief.fragility_index}
                label={result.brief.confidence_label}
                tip={t("tip_fragility")}
              />
            </div>
            <ul className="space-y-1.5 text-sm">
              {result.brief.lines.map((ln, i) => (
                <li key={i} className={ln.kind === "risk" ? "text-red-700" : "text-primary-strong"}>
                  {ln.kind === "risk" ? "⚠️" : "✅"} {ln.text}
                </li>
              ))}
            </ul>
            <p className="text-xs text-muted-foreground">
              {t("headline_range")}: <b>[{pct(lo)}, {pct(hi)}]</b> — {t("range_note")}{" "}
              <InfoTip text={t("tip_range")} />
            </p>
          </section>

          <Tabs<Tab>
            tabs={[
              { id: "overview", label: t("dash_tab_overview") },
              { id: "voices", label: t("dash_tab_voices") },
              { id: "report", label: t("dash_tab_report") },
            ]}
            active={tab}
            onChange={setTab}
          />

          {tab === "overview" && (
            <>
            <section className={card}>
              <h2 className="font-semibold mb-4">{t("compare_title")}</h2>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-muted-foreground border-b border-border">
                    <th className="py-2 font-medium">·</th>
                    {result.scenarios.map((s) => (
                      <th key={s.name} className="py-2 font-medium">
                        {s.name}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {segments.map((seg) => (
                    <tr key={seg} className="border-b border-border/60">
                      <td className="py-2.5 pr-3 text-muted-foreground">{seg}</td>
                      {result.scenarios.map((s) => {
                        const v = s.belief_by_segment[seg] ?? 0;
                        return (
                          <td key={s.name} className="py-2.5 pr-4">
                            <div className="flex items-center gap-2">
                              <div className="h-2 rounded-full bg-primary" style={{ width: `${Math.max(3, v * 90)}px` }} />
                              <span className="tabular-nums">{pct(v)}</span>
                            </div>
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>

            {/* Tipping points — PRD บังคับแสดงทุกรายงาน แม้ไม่พบ */}
            <section className={card}>
              <h2 className="font-semibold mb-1">
                ⚡ {t("tipping_title")} <InfoTip text={t("tip_tipping")} />
              </h2>
              {result.tipping_points.length === 0 ? (
                <p className="text-sm text-muted-foreground">{t("tipping_none")}</p>
              ) : (
                <div className="flex flex-wrap gap-2 mt-2">
                  {result.tipping_points.map((tp, i) => (
                    <span
                      key={i}
                      className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs ${
                        tp.delta > 0 ? "border-red-200 bg-red-50 text-red-700" : "border-primary/30 bg-primary-soft text-primary-strong"
                      }`}
                      title={`${tp.scenario} · round ${tp.round}: ${pct(tp.before)} → ${pct(tp.after)}`}
                    >
                      {tp.scenario} · r{tp.round}
                      <b className="tabular-nums">{tp.delta > 0 ? "+" : ""}{Math.round(tp.delta * 100)}%</b>
                    </span>
                  ))}
                </div>
              )}
            </section>

            <SegmentCanvas
              scenarios={result.scenarios}
              popShare={result.voice_population_share}
              labels={{ title: t("canvas_title"), note: t("canvas_note"), x: t("canvas_x"), y: t("canvas_y") }}
            />
            </>
          )}

          {tab === "voices" && (
            <>
              <section className={card}>
                <h2 className="font-semibold mb-1">{t("voices_title")}</h2>
                <p className="text-xs text-muted-foreground mb-4">{t("voices_note")}</p>
                {result.voices.length === 0 ? (
                  <p className="text-sm text-muted-foreground">—</p>
                ) : (
                  <div className="grid sm:grid-cols-2 gap-3">
                    {result.voices.map((v, i) => (
                      <div key={i} className="rounded-xl border border-border bg-background p-4 text-sm space-y-2">
                        {v.segment && (
                          <span className="inline-block rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">
                            {v.segment}
                          </span>
                        )}
                        {v.public && (
                          <p>
                            <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{t("voice_public")}</span>
                            <br />“{v.public}”
                          </p>
                        )}
                        {v.private && (
                          <p className="text-muted-foreground">
                            <span className="text-[11px] font-semibold uppercase tracking-wider">{t("voice_private")}</span>
                            <br />“{v.private}”
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </section>
              <section className={card}>
                <h2 className="font-semibold mb-3">
                  {t("pop_share")} <InfoTip text={t("pop_note")} />
                </h2>
                <div className="flex flex-wrap gap-2">
                  {result.voice_population_share.map((v) => (
                    <span key={v.segment} className="bg-muted rounded-full px-3 py-1 text-xs text-muted-foreground">
                      {v.segment}: {pct(v.population_share)}
                    </span>
                  ))}
                </div>
                <p className="text-xs text-muted-foreground mt-3">{t("pop_note")}</p>
              </section>
            </>
          )}

          {tab === "report" && (
            <section className={card + " space-y-4"}>
              <h2 className="font-semibold">{t("report_title")}</h2>
              <div className="grid sm:grid-cols-2 gap-3 text-sm">
                <div className="rounded-xl border border-border bg-background p-4">
                  <div className="text-xs uppercase tracking-wider text-muted-foreground">
                    {t("headline_range")} <InfoTip text={t("tip_range")} />
                  </div>
                  <div className="mt-1 font-display text-3xl font-semibold">
                    [{pct(lo)}, {pct(hi)}]
                  </div>
                </div>
                <div className="rounded-xl border border-border bg-background p-4">
                  <div className="text-xs uppercase tracking-wider text-muted-foreground">
                    Fragility <InfoTip text={t("tip_fragility")} />
                  </div>
                  <div className="mt-1 font-display text-3xl font-semibold">{result.brief.fragility_index}/100</div>
                  <div className="text-xs text-muted-foreground">{result.brief.confidence_label}</div>
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                <a
                  className="bg-primary hover:bg-primary-strong text-white px-5 py-2.5 rounded-xl text-sm font-medium"
                  href={`/dashboard.pdf?subject=${encodeURIComponent(subject)}&agents=${agents}&lang=th`}
                >
                  ⬇ {t("pdf_th")}
                </a>
                <a
                  className="border border-border px-5 py-2.5 rounded-xl text-sm text-muted-foreground hover:bg-muted"
                  href={`/dashboard.pdf?subject=${encodeURIComponent(subject)}&agents=${agents}&lang=en`}
                >
                  ⬇ {t("pdf_en")}
                </a>
              </div>
              <p className="text-xs text-muted-foreground">{t("pdf_note")}</p>

              {/* แชร์สู่ gallery สาธารณะ (P5-M8) — ต้องสิทธิ์ EXPORT; election ถูก block ที่ API */}
              <div className="border-t border-border pt-4">
                <button
                  disabled={shareState === "busy"}
                  onClick={() => {
                    setShareState("busy");
                    shareToGallery(subject, agents)
                      .then(() => setShareState("done"))
                      .catch((e) => setShareState(String(e.message ?? e)));
                  }}
                  className="rounded-xl border border-border px-5 py-2.5 text-sm text-muted-foreground hover:bg-muted disabled:opacity-40"
                >
                  {shareState === "busy" ? "⏳" : "🌐"} {t("share_gallery")}
                </button>
                {shareState === "done" && <p className="mt-2 text-xs text-primary-strong">✅ {t("share_done")}</p>}
                {shareState !== "idle" && shareState !== "busy" && shareState !== "done" && (
                  <p className="mt-2 text-xs text-red-700">{shareState}</p>
                )}
                <p className="mt-2 text-xs text-muted-foreground">{t("share_note")}</p>
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}
