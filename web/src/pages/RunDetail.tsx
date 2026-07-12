import { useEffect, useMemo, useState } from "react";
import { SimRunDetail, fetchRunDetail, pct, shareToGallery } from "../api";
import { useLang } from "../i18n";
import { InfoTip, PageHeader, Tabs } from "../ui";

// Run detail (P6-M2) — หน้าเดียวรองรับทั้ง fabric (dashboard payload) และ debate (posts+replay)

type Tab = "overview" | "debate" | "report";

function StanceBar({ v }: { v: number }) {
  // จุดยืน -1..1 → แถบซ้าย(แดง)/ขวา(เขียว) จากกึ่งกลาง
  const half = Math.abs(v) * 50;
  return (
    <span className="relative inline-block h-2 w-24 rounded-full bg-secondary align-middle">
      <span
        className={`absolute top-0 h-2 ${v >= 0 ? "bg-primary" : "bg-red-400"}`}
        style={v >= 0 ? { left: "50%", width: `${half}%` } : { right: "50%", width: `${half}%` }}
      />
      <span className="absolute left-1/2 top-[-2px] h-3 w-px bg-border" />
    </span>
  );
}

export default function RunDetail({ runId, onBack }: { runId: string; onBack: () => void }) {
  const { lang, t } = useLang();
  const [data, setData] = useState<SimRunDetail | null>(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<Tab>("overview");
  const [replayRound, setReplayRound] = useState<number | null>(null);
  const [shareState, setShareState] = useState<"idle" | "busy" | "done" | string>("idle");

  useEffect(() => {
    fetchRunDetail(runId)
      .then(setData)
      .catch((e) => setError(String(e.message ?? e)));
  }, [runId]);

  const card = "bg-card border border-border rounded-2xl p-6";
  const isDebate = data?.engine === "debate";
  const p = data?.payload ?? {};
  const rounds = useMemo(
    () => (data ? [...new Set(data.posts.map((x) => x.round_no))].sort((a, b) => a - b) : []),
    [data],
  );
  const shownRound = replayRound ?? (rounds.length ? rounds[rounds.length - 1] : 0);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={`${data?.engine === "debate" ? "🗣 DEBATE" : "⚙ FABRIC"} · ${data?.created_at?.slice(0, 16).replace("T", " ") ?? ""}`}
        title={data?.subject ?? runId}
        right={
          <button onClick={onBack} className="rounded-xl border border-border px-4 py-2 text-sm text-muted-foreground hover:bg-muted">
            ← {t("rd_back")}
          </button>
        }
      />

      {error && <div className="bg-red-50 border border-red-200 text-red-700 rounded-2xl p-5 text-sm">{error}</div>}
      {data?.status === "error" && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-2xl p-5 text-sm">
          {t("rd_failed")}: {data.error}
        </div>
      )}

      {data && data.status === "complete" && (
        <>
          <Tabs<Tab>
            tabs={[
              { id: "overview", label: t("rd_tab_overview") },
              ...(isDebate ? [{ id: "debate" as Tab, label: t("rd_tab_debate") }] : []),
              { id: "report", label: t("rd_tab_report") },
            ]}
            active={tab}
            onChange={setTab}
          />

          {tab === "overview" && isDebate && (
            <>
              <section className={card + " space-y-3"}>
                <h2 className="font-semibold">{t("rd_synthesis")}</h2>
                <p className="text-sm">{p.synthesis?.summary}</p>
                <div className="flex flex-wrap items-center gap-3 text-sm">
                  <span className="rounded-full bg-primary-soft px-3 py-1 text-primary-strong">
                    {t("rd_confidence")} {(p.synthesis?.confidence * 100).toFixed(0)}% <InfoTip text={t("tip_debate_conf")} />
                  </span>
                  {p.metrics?.posts_failed > 0 && (
                    <span className="rounded-full bg-amber-50 border border-amber-200 px-3 py-1 text-amber-700">
                      ⚠️ {p.metrics.posts_failed} {t("rd_failed_posts")}
                    </span>
                  )}
                  {p.cost_usd != null && <span className="text-xs text-muted-foreground">cost ${p.cost_usd}</span>}
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
              </section>
              <section className={card}>
                <h2 className="font-semibold mb-2">
                  {t("rd_stance_trend")} <InfoTip text={t("tip_stance_series")} />
                </h2>
                <div className="flex items-end gap-2 h-24">
                  {(p.metrics?.per_round_avg_stance ?? []).map((s: number, i: number) => (
                    <div key={i} className="flex-1 text-center">
                      <div className="mx-auto w-3/4 rounded-t bg-primary/70" style={{ height: `${((s + 1) / 2) * 90 + 5}%` }} title={`รอบ ${i}: ${s.toFixed(2)}`} />
                      <div className="mt-1 text-[10px] text-muted-foreground">r{i}</div>
                    </div>
                  ))}
                </div>
                {(p.metrics?.tipping_points ?? []).length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {p.metrics.tipping_points.map((tp: any, i: number) => (
                      <span key={i} className="rounded-full border border-amber-300 bg-amber-50 px-3 py-1 text-xs text-amber-700">
                        ⚡ r{tp.round}: {(tp.delta * 100).toFixed(0)}%
                      </span>
                    ))}
                  </div>
                )}
              </section>
            </>
          )}

          {tab === "overview" && !isDebate && (
            <>
              <section className={card + " space-y-3"}>
                <h2 className="font-semibold">Executive Brief</h2>
                <ul className="space-y-1.5 text-sm">
                  {(p.brief?.lines ?? []).map((ln: any, i: number) => (
                    <li key={i} className={ln.kind === "risk" ? "text-red-700" : "text-primary-strong"}>
                      {ln.kind === "risk" ? "⚠️" : "✅"} {ln.text}
                    </li>
                  ))}
                </ul>
                <p className="text-xs text-muted-foreground">
                  Fragility {p.brief?.fragility_index}/100 — {p.brief?.confidence_label} <InfoTip text={t("tip_fragility")} />
                </p>
              </section>
              <section className={card}>
                <h2 className="font-semibold mb-3">{t("compare_title")}</h2>
                <div className="space-y-1.5">
                  {Object.entries((p.scenarios?.[p.scenarios.length - 1]?.belief_by_segment ?? {}) as Record<string, number>).map(([seg, v]) => (
                    <div key={seg} className="flex items-center gap-2 text-xs">
                      <span className="w-44 shrink-0 truncate text-muted-foreground">{seg}</span>
                      <div className="h-2 flex-1 overflow-hidden rounded-full bg-secondary">
                        <div className="h-full bg-primary" style={{ width: `${v * 100}%` }} />
                      </div>
                      <span className="w-10 text-right tabular-nums">{pct(v)}</span>
                    </div>
                  ))}
                </div>
                {(p.tipping_points ?? []).length > 0 ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {p.tipping_points.map((tp: any, i: number) => (
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
                <h2 className="font-semibold">🗣 {t("rd_feed")} — {t("rd_round")} {shownRound}</h2>
                {/* Replay slider ทีละรอบ */}
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <span>▶ Replay</span>
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
              <ul className="mt-4 space-y-2">
                {data.posts
                  .filter((x) => x.round_no === shownRound)
                  .map((x, i) => (
                    <li key={i} className={`rounded-xl border p-3 text-sm ${x.failed ? "border-dashed border-border opacity-50" : "border-border bg-background"}`}>
                      <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
                        <span className="font-medium text-foreground">{x.segment}</span>
                        <span className="flex items-center gap-2">
                          <StanceBar v={x.stance} />
                          <span className="tabular-nums w-12">{x.stance >= 0 ? "+" : ""}{x.stance.toFixed(2)}</span>
                        </span>
                      </div>
                      <p className="mt-1">{x.failed ? `(${t("rd_post_failed")})` : x.content}</p>
                    </li>
                  ))}
              </ul>
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
              </div>
              {isDebate && (p.sources ?? []).length > 0 && (
                <div>
                  <div className="text-xs uppercase tracking-wider text-muted-foreground">{t("rd_sources")}</div>
                  <ul className="mt-1 space-y-1 text-xs">
                    {p.sources.map((s: any, i: number) => (
                      <li key={i}>
                        {s.status === "ready" ? "✅" : s.status === "blocked" ? "⛔" : "⚠️"} {s.label} — {s.status}
                        {s.error && <span className="text-red-700"> ({s.error})</span>}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <p className="text-xs text-muted-foreground">📌 {t("rd_prediction_note")}</p>
              {!isDebate && (
                <div className="flex flex-wrap items-center gap-2">
                  <a
                    className="inline-block rounded-xl bg-primary px-5 py-2.5 text-sm font-medium text-white"
                    href={`/dashboard.pdf?subject=${encodeURIComponent(data.subject)}&agents=${data.agents}&lang=${lang}`}
                  >
                    ⬇ {lang === "th" ? "PDF (มี watermark)" : "PDF (watermarked)"}
                  </a>
                  <button
                    disabled={shareState === "busy"}
                    onClick={() => {
                      setShareState("busy");
                      shareToGallery(data.subject, data.agents)
                        .then(() => setShareState("done"))
                        .catch((e) => setShareState(String(e.message ?? e)));
                    }}
                    className="rounded-xl border border-border px-5 py-2.5 text-sm text-muted-foreground hover:bg-muted disabled:opacity-40"
                  >
                    {shareState === "busy" ? "⏳" : "🌐"} {t("share_gallery")}
                  </button>
                  {shareState === "done" && <span className="text-xs text-primary-strong">✅ {t("share_done")}</span>}
                  {shareState !== "idle" && shareState !== "busy" && shareState !== "done" && (
                    <span className="text-xs text-red-700">{shareState}</span>
                  )}
                </div>
              )}
            </section>
          )}
        </>
      )}
    </div>
  );
}
