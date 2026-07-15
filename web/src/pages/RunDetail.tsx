import { useEffect, useMemo, useState } from "react";
import { SimRunDetail, fetchRunDetail, pct, shareRun, unshareRun } from "../api";
import { useLang } from "../i18n";
import { InfoTip, PageHeader, Tabs } from "../ui";

// Run detail (P6-M2) — หน้าเดียวรองรับทั้ง fabric (dashboard payload) และ debate (posts+replay)

type Tab = "overview" | "debate" | "canvas" | "evidence" | "report";

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

function StatusIcon({ status }: { status: string }) {
  if (status === "ready") return <>✅</>;
  if (status === "blocked") return <>⛔</>;
  if (status === "skipped") return <>⏭</>;
  return <>⚠️</>;
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

export default function RunDetail({ runId, onBack }: { runId: string; onBack: () => void }) {
  const { lang, t } = useLang();
  const [data, setData] = useState<SimRunDetail | null>(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<Tab>("overview");
  const [replayRound, setReplayRound] = useState<number | null>(null);
  const [shareOpen, setShareOpen] = useState(false);
  const [shareBusy, setShareBusy] = useState(false);
  const [shareErr, setShareErr] = useState("");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    fetchRunDetail(runId)
      .then(setData)
      .catch((e) => setError(String(e.message ?? e)));
  }, [runId]);

  const card = "bg-card border border-border rounded-2xl p-6";
  const isDebate = data?.engine === "debate";
  const p = data?.payload ?? {};
  // มุมมองที่ผู้ใช้เลือกเปิดตอนสั่งรัน (P6-M6) — ว่าง = ครบทุกมุม
  const enabledViews: string[] = data?.config?.views ?? ["overview", "debate", "canvas", "evidence"];
  const showView = (v: string) => v === "report" || enabledViews.includes(v);
  const rounds = useMemo(
    () => (data ? [...new Set(data.posts.map((x) => x.round_no))].sort((a, b) => a - b) : []),
    [data],
  );
  const newsItems: any[] = p.news?.items ?? [];
  const newsCounts = newsItems.reduce(
    (acc: Record<string, number>, item: any) => {
      acc[item.status || "unknown"] = (acc[item.status || "unknown"] ?? 0) + 1;
      return acc;
    },
    {},
  );
  const sourceCounts = (p.sources ?? []).reduce(
    (acc: Record<string, number>, item: any) => {
      acc[item.status || "unknown"] = (acc[item.status || "unknown"] ?? 0) + 1;
      return acc;
    },
    {},
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
              { id: "overview" as Tab, label: t("rd_tab_overview") },
              ...(isDebate && showView("debate") ? [{ id: "debate" as Tab, label: t("rd_tab_debate") }] : []),
              ...(showView("canvas") ? [{ id: "canvas" as Tab, label: t("rd_tab_canvas") }] : []),
              ...(showView("evidence") ? [{ id: "evidence" as Tab, label: t("rd_tab_evidence") }] : []),
              { id: "report" as Tab, label: t("rd_tab_report") },
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
              </section>
              <section className={card}>
                <h2 className="font-semibold mb-2">
                  {t("rd_stance_trend")} <InfoTip text={t("tip_stance_series")} />
                </h2>
                <div className="flex items-end gap-2 h-24">
                  {(p.metrics?.per_round_avg_stance ?? []).map((s: number, i: number) => (
                    <div key={i} className="flex-1 text-center">
                      <div className="mx-auto w-3/4 rounded-t bg-primary/70" style={{ height: `${((s + 1) / 2) * 90 + 5}%` }} title={`${t("rd_round_word")} ${i}: ${s.toFixed(2)}`} />
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
                <h2 className="font-semibold">{t("rd_brief_title")}</h2>
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

          {/* แผนภาพสวอร์ม — จุดยืน/ความเชื่อรายกลุ่ม (P6-M6) */}
          {tab === "canvas" && (
            <section className={card}>
              <h2 className="font-semibold mb-1">🫧 {t("rd_tab_canvas")}</h2>
              <p className="text-xs text-muted-foreground mb-4">{t("rd_canvas_note")}</p>
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
              {/* ข่าวจากโต๊ะข่าวสด (P7) — snapshot ที่ agent เห็นจริง พร้อมเวลา+สถานะ PII */}
              {isDebate && p.news?.enabled && (
                <div className="space-y-1.5">
                  <p className="text-xs text-muted-foreground">🌐 {t("rd_news_head")} ({(p.news.items ?? []).length})</p>
                  <div className="flex flex-wrap gap-1 text-[11px] text-muted-foreground">
                    {["ready", "blocked", "error", "skipped"].map((s) => (
                      <span key={s} className="rounded-full border border-border bg-background px-2 py-0.5">
                        <StatusIcon status={s} /> {s}: {newsCounts[s] ?? 0}
                      </span>
                    ))}
                  </div>
                  <ul className="space-y-1.5 text-sm">
                    {(p.news.items ?? []).map((n: any, i: number) => (
                      <li key={i} className="rounded-xl border border-border bg-background px-4 py-2.5">
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
                      {["ready", "blocked", "error", "empty"].map((s) => (
                        <span key={s} className="rounded-full border border-border bg-background px-2 py-0.5">
                          <StatusIcon status={s} /> {s}: {sourceCounts[s] ?? 0}
                        </span>
                      ))}
                    </div>
                    <ul className="space-y-1.5 text-sm">
                      {p.sources.map((s: any, i: number) => (
                        <li key={i} className="rounded-xl border border-border bg-background px-4 py-2.5">
                          <div className="flex items-center justify-between">
                            <span className="font-medium"><StatusIcon status={s.status} /> {s.label}</span>
                            <span className="text-xs text-muted-foreground">{s.chunks} {t("rd_evidence_chunks")}</span>
                          </div>
                          {s.error && <div className="mt-1 text-xs text-red-700">{s.error}</div>}
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
                      {p.tipping_points.map((tp: any, i: number) => (
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
                </div>
              )}
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
                    const fresh = await fetchRunDetail(runId);
                    setData(fresh);
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
                  value={`${window.location.origin}/app/#gallery/${data.share_token}`}
                  className="flex-1 rounded-lg border border-border bg-background px-3 py-2 text-xs"
                />
                <button
                  onClick={() => {
                    navigator.clipboard.writeText(`${window.location.origin}/app/#gallery/${data.share_token}`);
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
