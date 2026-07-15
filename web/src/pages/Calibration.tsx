import { useEffect, useState } from "react";
import { CalibrationData, fetchCalibration, resolvePrediction } from "../api";
import { useLang } from "../i18n";
import { InfoTip, PageHeader } from "../ui";

// หน้า Calibration (P5-M3) — ตาม UI studio: stat cards + sparkline (เส้นอ้างอิง 0/0.25)
// + per-domain ✓/~/✗ + คิว resolve | ต่างจาก SwarmSight: resolve แล้วแก้ไม่ได้ (TRUST-01)

function ratingOf(brier: number | null, lang: "th" | "en"): { label: string; cls: string } | null {
  if (brier == null) return null;
  if (brier < 0.1) return { label: lang === "th" ? "ยอดเยี่ยม" : "Excellent", cls: "text-primary-strong" };
  if (brier < 0.2) return { label: lang === "th" ? "ดี" : "Good", cls: "text-primary-strong" };
  if (brier < 0.25) return { label: lang === "th" ? "พอใช้" : "Okay", cls: "text-amber-600" };
  return { label: lang === "th" ? "มั่นใจเกินจริง" : "Overconfident", cls: "text-red-600" };
}

function BrierSparkline({ points, lang }: { points: CalibrationData["trend"]; lang: "th" | "en" }) {
  const W = 640, H = 100, P = 8;
  const maxB = Math.max(0.25, ...points.map((p) => p.brier));
  const minB = Math.min(0, ...points.map((p) => p.brier));
  const xs = (i: number) => P + (i * (W - P * 2)) / Math.max(1, points.length - 1);
  const ys = (b: number) => H - P - ((b - minB) / Math.max(0.001, maxB - minB)) * (H - P * 2);
  const path = points.map((p, i) => `${i === 0 ? "M" : "L"} ${xs(i).toFixed(1)} ${ys(p.brier).toFixed(1)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="mt-3 h-24 w-full overflow-visible">
      {/* เส้นอ้างอิง 0 = สมบูรณ์แบบ */}
      <line x1={P} x2={W - P} y1={ys(0)} y2={ys(0)} stroke="var(--color-chart-1)" strokeOpacity={0.4} strokeDasharray="2,3" />
      {/* เส้นอ้างอิง 0.25 = สุ่มเดา (โยนเหรียญ) */}
      <line x1={P} x2={W - P} y1={ys(0.25)} y2={ys(0.25)} stroke="var(--color-chart-3)" strokeOpacity={0.7} strokeDasharray="3,3" />
      <text x={W - P} y={ys(0.25) - 3} textAnchor="end" fontSize="9" fill="var(--color-chart-3)">
        {lang === "th" ? "0.25 · สุ่มเดา" : "0.25 · coin flip"}
      </text>
      <path d={`${path} L ${xs(points.length - 1)} ${H - P} L ${xs(0)} ${H - P} Z`} fill="var(--color-primary)" fillOpacity={0.08} />
      <path d={path} stroke="var(--color-primary)" strokeWidth={2} fill="none" strokeLinecap="round" strokeLinejoin="round" />
      {points.map((p, i) => (
        <circle key={i} cx={xs(i)} cy={ys(p.brier)} r={3} fill="var(--color-primary)">
          <title>{`${new Date(p.t * 1000).toLocaleDateString()} — Brier ${p.brier.toFixed(3)} · n=${p.n}`}</title>
        </circle>
      ))}
    </svg>
  );
}

function ReliabilityDiagram({ bins }: { bins: CalibrationData["reliability"] }) {
  return (
    <div className="mt-4 grid gap-3 sm:grid-cols-5" role="img" aria-label="Reliability diagram 5 bins">
      {bins.map((bin) => (
        <div key={bin.lower} className="rounded-xl border border-border bg-background p-3 text-center">
          <div className="flex h-24 items-end justify-center gap-2" aria-hidden="true">
            <span className="w-4 rounded-t bg-muted" style={{ height: `${(bin.mean_confidence ?? 0) * 100}%` }} />
            <span className="w-4 rounded-t bg-primary" style={{ height: `${(bin.observed_rate ?? 0) * 100}%` }} />
          </div>
          <div className="mt-2 text-[11px] tabular-nums">
            {(bin.lower * 100).toFixed(0)}–{(bin.upper * 100).toFixed(0)}% · n={bin.n}
          </div>
          <div className="text-[10px] text-muted-foreground">
            forecast {bin.mean_confidence == null ? "—" : `${(bin.mean_confidence * 100).toFixed(0)}%`} / observed {bin.observed_rate == null ? "—" : `${(bin.observed_rate * 100).toFixed(0)}%`}
          </div>
        </div>
      ))}
    </div>
  );
}

export default function Calibration() {
  const { lang, t } = useLang();
  const [data, setData] = useState<CalibrationData | null>(null);
  const [error, setError] = useState("");
  const [pending, setPending] = useState<{ id: number; outcome: "true" | "false" } | null>(null);
  const [note, setNote] = useState("");
  const [evidenceUrl, setEvidenceUrl] = useState("");
  const [evidenceName, setEvidenceName] = useState("");
  const [observedAt, setObservedAt] = useState(new Date().toISOString().slice(0, 16));
  const [busy, setBusy] = useState(false);

  const load = () =>
    fetchCalibration()
      .then((d) => {
        setData(d);
        setError("");
      })
      .catch((e) => setError(String(e.message ?? e)));
  useEffect(() => {
    load();
  }, []);

  const card = "bg-card border border-border rounded-2xl p-5";
  const rating = ratingOf(data?.overall_brier ?? null, lang);

  async function submitResolve() {
    if (!pending) return;
    setBusy(true);
    try {
      await resolvePrediction(pending.id, pending.outcome, note.trim(), {
        observed_at: new Date(observedAt).toISOString(),
        evidence_url: evidenceUrl.trim(),
        evidence_name: evidenceName.trim(),
      });
      setPending(null);
      setNote("");
      setEvidenceUrl("");
      setEvidenceName("");
      await load();
    } catch (e: any) {
      setError(String(e.message ?? e));
    } finally {
      setBusy(false);
    }
  }

  const outcomeLabel: Record<string, string> = {
    true: t("cal_happened"),
    false: t("cal_didnt"),
  };

  return (
    <div className="space-y-6">
      <PageHeader eyebrow={t("cal_eyebrow")} title={t("cal_title")} desc={t("cal_sub")} />

      {error && <div className="bg-red-50 border border-red-200 text-red-700 rounded-2xl p-5 text-sm">{error}</div>}

      {data && (
        <>
          {/* Stat cards */}
          <div className="grid gap-4 sm:grid-cols-3">
            <div className={card}>
              <div className="text-xs uppercase tracking-wider text-muted-foreground">
                Brier score <InfoTip text={t("tip_brier")} />
              </div>
              <div className="mt-1 flex items-baseline gap-2">
                <span className="font-display text-4xl font-semibold">
                  {data.overall_brier == null ? "—" : data.overall_brier.toFixed(3)}
                </span>
                {rating && <span className={`text-sm font-medium ${rating.cls}`}>{rating.label}</span>}
              </div>
              <p className="mt-1 text-xs text-muted-foreground">{t("cal_scale_note")}</p>
            </div>
            <div className={card}>
              <div className="text-xs uppercase tracking-wider text-muted-foreground">{t("cal_resolved")}</div>
              <div className="mt-1 font-display text-4xl font-semibold">{data.resolved_total}</div>
            </div>
            <div className={card}>
              <div className="text-xs uppercase tracking-wider text-muted-foreground">{t("cal_best_domain")}</div>
              {data.domains.length ? (
                (() => {
                  const best = [...data.domains].sort((a, b) => a.brier - b.brier)[0];
                  return (
                    <div className="mt-1">
                      <div className="text-xl">{best.domain}</div>
                      <div className="text-xs text-muted-foreground">
                        Brier {best.brier.toFixed(3)} · n={best.n}
                      </div>
                    </div>
                  );
                })()
              ) : (
                <div className="mt-1 text-sm text-muted-foreground">{t("cal_no_data")}</div>
              )}
            </div>
          </div>

          {/* Weekly trend */}
          <div className={card}>
            <div className="text-xs uppercase tracking-wider text-muted-foreground">
              Reliability · 5 bins · n={data.sample_size}
            </div>
            <ReliabilityDiagram bins={data.reliability} />
          </div>

          {data.trend.length >= 2 && (
            <div className={card}>
              <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-muted-foreground">
                {t("cal_trend")} <InfoTip text={t("tip_brier")} />
                <span className="ml-auto normal-case opacity-70">{t("cal_lower_better")}</span>
              </div>
              <BrierSparkline points={data.trend} lang={lang} />
            </div>
          )}

          {/* Per-domain */}
          {data.domains.length > 0 && (
            <div className={card}>
              <div className="text-xs uppercase tracking-wider text-muted-foreground mb-3">{t("cal_by_domain")}</div>
              <div className="space-y-3">
                {data.domains.map((d) => {
                  const total = Math.max(1, d.happened + d.partial + d.didnt);
                  return (
                    <div key={d.domain}>
                      <div className="flex items-center gap-3">
                        <div className="w-32 shrink-0 text-sm">{d.domain}</div>
                        <div className="relative h-2 flex-1 overflow-hidden rounded-full bg-secondary">
                          <div
                            className="h-full bg-primary"
                            style={{ width: `${Math.max(0, Math.min(1, 1 - d.brier * 2)) * 100}%` }}
                          />
                        </div>
                        <div className="w-24 shrink-0 text-right text-xs text-muted-foreground tabular-nums">
                          {d.brier.toFixed(3)} · n={d.n}
                        </div>
                      </div>
                      <div className="mt-1 ml-32 flex gap-3 text-[11px] text-muted-foreground">
                        <span>✓ {d.happened}</span>
                        <span>~ {d.partial}</span>
                        <span>✗ {d.didnt}</span>
                        <span
                          className="flex h-1.5 flex-1 self-center overflow-hidden rounded-full bg-secondary/50"
                          title={`✓${d.happened} ~${d.partial} ✗${d.didnt}`}
                        >
                          <span className="bg-primary" style={{ width: `${(d.happened / total) * 100}%` }} />
                          <span className="bg-amber-400" style={{ width: `${(d.partial / total) * 100}%` }} />
                          <span className="bg-red-400" style={{ width: `${(d.didnt / total) * 100}%` }} />
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* คิวครบกำหนด — จุด resolve */}
          <div className={card}>
            <h2 className="font-semibold">{t("cal_due_title")}</h2>
            <p className="mt-1 text-xs text-muted-foreground">⚠️ {t("cal_immutable_note")}</p>
            {data.due.length === 0 ? (
              <p className="mt-3 text-sm text-muted-foreground">{t("runs_due_empty")}</p>
            ) : (
              <ul className="mt-3 space-y-2">
                {data.due.map((p) => (
                  <li key={p.prediction_id} className="rounded-xl border border-border bg-background p-4 text-sm">
                    <div className="flex items-start justify-between gap-3 flex-wrap">
                      <div className="min-w-0 flex-1">
                        <span className="text-xs bg-muted rounded-full px-2 py-0.5 mr-2">#{p.prediction_id}</span>
                        <span className="text-xs text-muted-foreground mr-2">
                          {p.domain} · due {p.due_date} · conf {(p.confidence * 100).toFixed(0)}%
                        </span>
                        <div className="mt-1">{p.claim}</div>
                      </div>
                      <div className="flex items-center gap-1.5">
                        {(["true", "false"] as const).map((o) => (
                          <button
                            key={o}
                            onClick={() => setPending({ id: p.prediction_id, outcome: o })}
                            className={`rounded-full border px-3 py-1 text-xs transition ${
                              o === "true"
                                ? "border-primary/40 text-primary-strong hover:bg-primary/5"
                                : "border-red-200 text-red-700 hover:bg-red-50"
                            }`}
                          >
                            {outcomeLabel[o]}
                          </button>
                        ))}
                      </div>
                    </div>
                    {pending?.id === p.prediction_id && (
                      <div className="mt-3 rounded-lg border border-primary/30 bg-primary/5 p-3 space-y-2">
                        <div className="text-xs font-medium">
                          {t("cal_confirm_prefix")} <b>{outcomeLabel[pending.outcome]}</b> — {t("cal_confirm_suffix")}
                        </div>
                        <input
                          value={evidenceName}
                          onChange={(e) => setEvidenceName(e.target.value)}
                          placeholder="ชื่อหลักฐาน"
                          className="w-full rounded-lg border border-border bg-background px-3 py-1.5 text-xs"
                        />
                        <input
                          value={evidenceUrl}
                          onChange={(e) => setEvidenceUrl(e.target.value)}
                          placeholder="https://แหล่งหลักฐาน"
                          className="w-full rounded-lg border border-border bg-background px-3 py-1.5 text-xs"
                        />
                        <input
                          type="datetime-local"
                          value={observedAt}
                          onChange={(e) => setObservedAt(e.target.value)}
                          className="w-full rounded-lg border border-border bg-background px-3 py-1.5 text-xs"
                        />
                        <input
                          value={note}
                          onChange={(e) => setNote(e.target.value)}
                          placeholder={t("cal_note_ph")}
                          className="w-full rounded-lg border border-border bg-background px-3 py-1.5 text-xs"
                        />
                        <div className="flex gap-2">
                          <button
                            disabled={busy || !evidenceName.trim() || !evidenceUrl.trim()}
                            onClick={submitResolve}
                            className="rounded-lg bg-primary px-4 py-1.5 text-xs font-medium text-white disabled:opacity-50"
                          >
                            {t("cal_confirm_btn")}
                          </button>
                          <button
                            disabled={busy}
                            onClick={() => setPending(null)}
                            className="rounded-lg border border-border px-4 py-1.5 text-xs text-muted-foreground"
                          >
                            {t("cal_cancel")}
                          </button>
                        </div>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Resolved แล้ว (อ่านอย่างเดียว) + ยังไม่ถึงกำหนด */}
          {data.items.length > 0 && (
            <div className={card}>
              <h2 className="font-semibold mb-3">{t("cal_resolved_list")}</h2>
              <ul className="space-y-1.5 text-sm">
                {data.items.slice(0, 15).map((i) => (
                  <li key={i.prediction_id} className="flex items-center gap-2 text-muted-foreground">
                    <span className="shrink-0">
                      {i.outcome_value === 1 ? "✅" : i.outcome_value === 0.5 ? "🟡" : "❌"}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-foreground">{i.claim}</span>
                    <span className="shrink-0 text-xs tabular-nums">
                      conf {(i.confidence * 100).toFixed(0)}% · Brier {i.brier.toFixed(3)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {data.upcoming.length > 0 && (
            <p className="text-xs text-muted-foreground">
              ⏳ {t("cal_upcoming")}: {data.upcoming.length} — {data.upcoming.map((u) => `#${u.prediction_id} (${u.due_date})`).join(", ")}
            </p>
          )}
        </>
      )}
    </div>
  );
}
