import { useEffect, useState } from "react";
import { useLang } from "../i18n";
import { ConfirmDialog, PageHeader, SelectCard } from "../ui";
import {
  EngineInfo,
  FALLBACK_PACK_LIMITS,
  PackLimits,
  PersonaPack,
  PoolSegment,
  SourceInput,
  createRunAsync,
  deletePack,
  fetchEngines,
  fetchPacks,
  fetchPool,
  fetchRunReadiness,
  fetchSettings,
  pct,
  RunReadiness,
} from "../api";
import PersonaPackModal, { StackedBar, type PackModalIntent } from "../PersonaPackModal";
import type { RunRequest } from "../App";

// Wizard (P6-M1/M3): คำถาม → เครื่องยนต์ → [แหล่งข้อมูล ถ้า debate] → agents → ยืนยัน
// ทุก run ถูกเก็บถาวร (P6-M2) → เปิดหน้า Run detail; fabric + Red Team A/B → หน้า Compare เดิม

// หมวดหมู่ 6 อันตาม studio ต้นทาง (finance/product/social/policy/science/general)
// เก็บลง DB เป็นภาษาไทย canonical เสมอ (calibration จัดกลุ่มตาม string) — UI แสดงตามภาษา
const DOMAIN_KEYS = ["finance", "product", "social", "policy", "science", "general"] as const;
const DOMAIN_TH: Record<(typeof DOMAIN_KEYS)[number], string> = {
  finance: "การเงิน/ตลาดทุน",
  product: "สินค้า/ผลิตภัณฑ์",
  social: "กระแสสังคม",
  policy: "นโยบายสาธารณะ",
  science: "วิทยาศาสตร์/เทคโนโลยี",
  general: "ทั่วไป",
};

// template สองภาษา — label โชว์บนปุ่ม, q เป็น scenario ที่จะกลายเป็น subject จริง, domain เป็น key
type DomainKey = (typeof DOMAIN_KEYS)[number];
const TEMPLATES: { label: { th: string; en: string }; q: { th: string; en: string }; domain: DomainKey }[] = [
  { label: { th: "ค่าธรรมเนียมรถติด", en: "Congestion charge" }, q: { th: "มาตรการค่าธรรมเนียมรถติด กทม.", en: "Bangkok congestion charge scheme" }, domain: "policy" },
  { label: { th: "ขึ้นราคา 15%", en: "15% price hike" }, q: { th: "แคมเปญขึ้นราคาสินค้า 15% พร้อมข้อความสื่อสารใหม่", en: "A 15% price increase with new messaging" }, domain: "product" },
  { label: { th: "เวลาขายแอลกอฮอล์", en: "Alcohol sale hours" }, q: { th: "นโยบายจำกัดเวลาขายแอลกอฮอล์รอบใหม่", en: "New restrictions on alcohol sale hours" }, domain: "policy" },
  { label: { th: "ซ้อมแถลงดราม่า", en: "Crisis statement" }, q: { th: "แบรนด์ถูกกล่าวหาเรื่องคุณภาพสินค้า — ควรแถลงด้วยข้อความแบบไหน", en: "A brand accused over product quality — what statement works best?" }, domain: "social" },
  { label: { th: "เปลี่ยนโมเดลราคา", en: "New pricing model" }, q: { th: "เปิดตัวบริการสมัครสมาชิกรายเดือนแทนการซื้อขาด", en: "Launching a monthly subscription instead of one-time purchase" }, domain: "product" },
  { label: { th: "ข่าวลือน้ำประปา", en: "Tap water rumor" }, q: { th: "ข่าวลือเรื่องคุณภาพน้ำประปาในเขตเมืองกำลังแพร่ในกลุ่มปิด", en: "A rumor about tap water quality spreading in closed groups" }, domain: "social" },
];
const DOMAINS = DOMAIN_KEYS.map((k) => DOMAIN_TH[k]);

function Steps({ step, labels, onJump }: { step: number; labels: string[]; onJump: (i: number) => void }) {
  return (
    <div className="flex items-center gap-2 flex-wrap text-sm">
      {labels.map((l, i) => (
        <div key={l} className="flex items-center gap-2">
          <button
            onClick={() => onJump(i)}
            className={`w-6 h-6 rounded-full border flex items-center justify-center text-xs font-semibold transition ${
              i === step
                ? "border-primary bg-primary text-white"
                : i < step
                  ? "border-primary/40 bg-primary/10 text-primary"
                  : "border-border bg-background text-muted-foreground"
            }`}
          >
            {i + 1}
          </button>
          <span className={i === step ? "font-medium" : "text-muted-foreground"}>{l}</span>
          {i < labels.length - 1 && <span className="text-muted-foreground">›</span>}
        </div>
      ))}
    </div>
  );
}

export default function NewRun({
  onCompare,
  onCreated,
}: {
  onCompare: (r: RunRequest) => void; // fabric + Red Team A/B → หน้า Compare เดิม
  onCreated: (runId: string) => void; // run ถาวร → หน้า Run detail
}) {
  const { lang, t, formatCurrency, formatNumber } = useLang();
  const [step, setStep] = useState(0);
  const [subject, setSubject] = useState("");
  const [domain, setDomain] = useState(DOMAINS[0]);
  const [agents, setAgents] = useState(100);
  const [rounds, setRounds] = useState(3);
  const [engine, setEngine] = useState<"fabric" | "debate">("fabric");
  const [engines, setEngines] = useState<EngineInfo[]>([]);
  const [redTeam, setRedTeam] = useState(false);
  const [packs, setPacks] = useState<PersonaPack[]>([]);
  const [packId, setPackId] = useState<number | null>(null);
  const [packIntent, setPackIntent] = useState<PackModalIntent | null>(null);
  const [packToDelete, setPackToDelete] = useState<PersonaPack | null>(null);
  const [sources, setSources] = useState<SourceInput[]>([]);
  const [pool, setPool] = useState<PoolSegment[]>([]);
  const [poolOpen, setPoolOpen] = useState(false);
  const [packLimits, setPackLimits] = useState<PackLimits>(FALLBACK_PACK_LIMITS);
  const [views, setViews] = useState<string[]>(["overview", "debate", "canvas", "evidence"]);
  const [liveNews, setLiveNews] = useState(false);
  const [readiness, setReadiness] = useState<RunReadiness | null>(null);
  const [srcDraft, setSrcDraft] = useState<{ kind: "url" | "rss" | "text"; label: string; value: string }>({ kind: "url", label: "", value: "" });
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState("");
  const [error, setError] = useState("");

  const loadPacks = () => fetchPacks().then(setPacks).catch(() => {});
  // โหลดพูลของ persona ทุกครั้งที่เปลี่ยน pack (P6-M6)
  useEffect(() => {
    fetchPool(packId)
      .then((d) => {
        setPool(d.segments);
        if (d.limits) setPackLimits(d.limits); // ขอบเขตจำนวนกลุ่มจาก backend — ไม่ hardcode (ADR-0009)
      })
      .catch(() => setPool([]));
  }, [packId]);
  useEffect(() => {
    loadPacks();
    fetchEngines().then(setEngines).catch(() => {});
    fetchSettings()
      .then((s) => {
        setEngine(s.default_engine);
        setAgents(s.default_agents);
        setRounds(s.default_rounds);
        if (DOMAINS.includes(s.default_domain)) setDomain(s.default_domain);
      })
      .catch(() => {});
  }, []);

  const isDebate = engine === "debate";
  const cap = engines.find((e) => e.key === engine)?.max_agents ?? (isDebate ? 40 : 1000);
  const agentChoices = isDebate ? [10, 20, 40] : [100, 500, 1000];
  const labels = [
    t("wiz_step1"),
    t("wiz_step_engine"),
    ...(isDebate ? [t("wiz_step_sources")] : []),
    t("wiz_step_agents"),
    t("wiz_step3"),
  ];
  const stepKey = (isDebate
    ? ["question", "engine", "sources", "agents", "review"]
    : ["question", "engine", "agents", "review"])[step];
  const lastStep = labels.length - 1;
  const card = "bg-card border border-border rounded-2xl p-6";

  useEffect(() => {
    if (stepKey !== "review" || subject.trim().length < 4) {
      setReadiness(null);
      return;
    }
    const body = {
      engine,
      subject: subject.trim(),
      domain,
      agents: Math.min(agents, cap),
      rounds,
      pack_id: packId,
      red_team: redTeam,
      sources: isDebate ? sources : [],
      views,
      live_news: isDebate && liveNews,
    };
    fetchRunReadiness(body)
      .then(setReadiness)
      .catch(() => setReadiness(null));
  }, [stepKey, subject, engine, domain, agents, cap, rounds, packId, redTeam, sources, views, isDebate, liveNews]);

  function addSource() {
    if (sources.length >= 10) return;
    const v = srcDraft.value.trim();
    if (!v) return;
    if (srcDraft.kind !== "text" && !/^https?:\/\//.test(v)) {
      setError(t("wiz_src_need_url"));
      return;
    }
    setError("");
    setSources((s) => [
      ...s,
      srcDraft.kind === "text"
        ? { kind: "text", label: srcDraft.label.trim() || `${t("wiz_src_text")} ${s.length + 1}`, text: v }
        : { kind: srcDraft.kind, label: srcDraft.label.trim() || v.slice(0, 60), url: v },
    ]);
    setSrcDraft({ ...srcDraft, label: "", value: "" });
  }

  async function submit() {
    if (redTeam && engine === "fabric") {
      onCompare({ subject: subject.trim(), agents, redTeam: true, packId });
      return;
    }
    setBusy(true);
    setError("");
    setProgress(t("run_queued"));
    try {
      const idempotencyKey = globalThis.crypto?.randomUUID?.() ?? `run-${Date.now()}-${Math.random()}`;
      const job = await createRunAsync({
        engine,
        subject: subject.trim(),
        domain,
        agents: Math.min(agents, cap),
        rounds,
        pack_id: packId,
        red_team: redTeam,
        sources: isDebate ? sources : [],
        views,
        live_news: isDebate && liveNews,
      }, idempotencyKey);
      onCreated(job.run_id);
    } catch (e: any) {
      setError(String(e.message ?? e));
    } finally {
      setBusy(false);
      setProgress("");
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader eyebrow={t("wiz_eyebrow")} title={t("wiz_title")} />
      <Steps step={step} labels={labels} onJump={setStep} />
      {error && <div className="bg-red-50 border border-red-200 text-red-700 rounded-2xl p-4 text-sm">{error}</div>}
      {progress && <div className="rounded-2xl border border-primary/20 bg-primary/5 p-4 text-sm text-primary-strong">{progress}</div>}

      {stepKey === "question" && (
        <div className={card + " space-y-5"}>
          <div>
            <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">{t("wiz_q_label")}</div>
            <textarea
              className="w-full border border-border rounded-xl px-4 py-3 text-sm bg-background min-h-24 outline-none focus:ring-2 focus:ring-ring/30"
              placeholder={t("wiz_q_ph")}
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
            />
          </div>
          <div>
            <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t("wiz_templates_title")}</div>
            <p className="text-xs text-muted-foreground mt-1 mb-2">{t("wiz_templates_hint")}</p>
            <div className="grid sm:grid-cols-2 gap-2">
              {TEMPLATES.map((tpl) => {
                const q = tpl.q[lang];
                return (
                  <SelectCard key={tpl.label.en} active={subject === q} onClick={() => { setSubject(q); setDomain(DOMAIN_TH[tpl.domain]); }}>
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-medium">{tpl.label[lang]}</span>
                      <span className="rounded-full border border-border bg-background px-2 py-0.5 text-[10px] text-muted-foreground">{t(`domain_${tpl.domain}`)}</span>
                    </div>
                    <div className="mt-1 line-clamp-2 text-xs text-muted-foreground">{q}</div>
                  </SelectCard>
                );
              })}
            </div>
          </div>
          <div>
            <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">{t("wiz_domain")}</div>
            {/* grid 2/3 คอลัมน์แบบ studio — แสดง label ตามภาษา, เก็บค่า canonical ไทย */}
            <div className="grid grid-cols-2 gap-2 md:grid-cols-3">
              {DOMAIN_KEYS.map((k) => (
                <SelectCard key={k} active={domain === DOMAIN_TH[k]} onClick={() => setDomain(DOMAIN_TH[k])}>
                  <span className="text-sm">{t(`domain_${k}`)}</span>
                </SelectCard>
              ))}
            </div>
            <p className="text-xs text-muted-foreground mt-3">🗳️ {t("wiz_election_warn")}</p>
          </div>
        </div>
      )}

      {stepKey === "engine" && (
        <div className={card + " space-y-4"}>
          <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">⚙ {t("wiz_engine_title")}</div>
          <p className="text-xs text-muted-foreground">{t("wiz_engine_desc")}</p>
          <div className="grid sm:grid-cols-2 gap-2">
            {engines.map((e) => (
              <SelectCard
                key={e.key}
                active={engine === e.key}
                onClick={() => {
                  setEngine(e.key);
                  setAgents(e.key === "debate" ? 20 : 100);
                  setStep(1);
                }}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium">{e.key === "debate" ? "🗣 " : "⚙ "}{lang === "th" ? e.label_th : e.label_en}</span>
                  {e.uses_llm && <span className="rounded-full bg-amber-50 border border-amber-200 px-2 py-0.5 text-[10px] text-amber-700">LLM·$</span>}
                </div>
                <div className="mt-1 text-xs text-muted-foreground">{lang === "th" ? e.desc_th : e.desc_en}</div>
              </SelectCard>
            ))}
          </div>
        </div>
      )}

      {stepKey === "sources" && (
        <div className={card + " space-y-4"}>
          <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">📎 {t("wiz_src_title")}</div>
          <p className="text-xs text-muted-foreground">{t("wiz_src_desc")}</p>
          {/* โต๊ะข่าวสด (P7, SIM-11) — โต๊ะข่าวกลางดึงข่าวให้ agent ตาม media diet ของกลุ่ม */}
          <button
            type="button"
            onClick={() => setLiveNews(!liveNews)}
            className={`flex w-full items-center justify-between rounded-xl border p-3 text-left text-sm transition ${
              liveNews ? "border-primary bg-primary/5" : "border-border bg-card hover:bg-muted"
            }`}
          >
            <span>
              <span className="font-medium">🌐 {t("wiz_news_title")}</span>
              <span className="mt-0.5 block text-xs text-muted-foreground">{t("wiz_news_desc")}</span>
            </span>
            <span className={`ml-3 shrink-0 rounded-full px-2.5 py-0.5 text-xs font-medium ${liveNews ? "bg-primary text-white" : "bg-muted text-muted-foreground"}`}>
              {liveNews ? "ON" : "OFF"}
            </span>
          </button>
          <div className="flex flex-wrap gap-2">
            {(["url", "rss", "text"] as const).map((k) => (
              <button
                key={k}
                onClick={() => setSrcDraft({ ...srcDraft, kind: k })}
                className={`rounded-full border px-3 py-1 text-xs ${srcDraft.kind === k ? "border-primary bg-primary/5 text-primary-strong font-medium" : "border-border text-muted-foreground"}`}
              >
                {k === "url" ? "🔗 URL" : k === "rss" ? "📰 RSS" : `📄 ${t("wiz_src_text")}`}
              </button>
            ))}
          </div>
          <div className="space-y-2">
            <input
              value={srcDraft.label}
              onChange={(e) => setSrcDraft({ ...srcDraft, label: e.target.value })}
              placeholder={t("wiz_src_label_ph")}
              className="w-full rounded-xl border border-border bg-background px-4 py-2 text-sm"
            />
            {srcDraft.kind === "text" ? (
              <textarea
                value={srcDraft.value}
                onChange={(e) => setSrcDraft({ ...srcDraft, value: e.target.value })}
                placeholder={t("wiz_src_text_ph")}
                rows={4}
                className="w-full rounded-xl border border-border bg-background px-4 py-2 text-sm"
              />
            ) : (
              <input
                value={srcDraft.value}
                onChange={(e) => setSrcDraft({ ...srcDraft, value: e.target.value })}
                placeholder="https://…"
                className="w-full rounded-xl border border-border bg-background px-4 py-2 text-sm"
              />
            )}
            <button
              onClick={addSource}
              disabled={!srcDraft.value.trim()}
              title={!srcDraft.value.trim() ? t("wiz_src_need_value") : ""}
              className="rounded-xl border border-border px-4 py-2 text-sm text-primary-strong hover:bg-primary/5 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              + {t("wiz_src_add")}
            </button>
            {!srcDraft.value.trim() && (
              <p className="text-[11px] text-muted-foreground">💡 {t("wiz_src_need_value")}</p>
            )}
          </div>
          {sources.length > 0 && (
            <ul className="space-y-1 text-sm">
              {sources.map((s, i) => (
                <li key={i} className="flex items-center justify-between rounded-lg border border-border bg-background px-3 py-2">
                  <span className="truncate">{s.kind === "url" ? "🔗" : s.kind === "rss" ? "📰" : "📄"} {s.label}</span>
                  <button onClick={() => setSources(sources.filter((_, j) => j !== i))} className="text-muted-foreground hover:text-red-600">✕</button>
                </li>
              ))}
            </ul>
          )}
          <p className="text-xs text-muted-foreground">🛡️ {t("wiz_src_pii_note")}</p>
        </div>
      )}

      {stepKey === "agents" && (
        <div className={card + " space-y-4"}>
          <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t("wiz_agents")} (cap {cap})</div>
          <div className="grid sm:grid-cols-3 gap-2">
            {agentChoices.map((n) => (
              <SelectCard key={n} active={agents === n} onClick={() => setAgents(n)}>
                <span className="text-sm font-medium">{formatNumber(n)} agents</span>
              </SelectCard>
            ))}
          </div>
          {isDebate && (
            <div>
              <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                {t("wiz_rounds")}: <span className="text-foreground">{rounds}</span>
              </div>
              <input type="range" min={1} max={6} value={rounds} onChange={(e) => setRounds(parseInt(e.target.value))} className="mt-2 w-full accent-primary" />
            </div>
          )}
          {!isDebate && <p className="text-xs text-muted-foreground">🌌 {t("wiz_universes")}</p>}

          <div>
            <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t("wiz_persona_title")}</div>
            {/* จัดการ pack ตรงนี้เลย (redesign 13 ก.ค. — มติผู้ใช้): แก้ไข/ลบ inline ไม่ต้องเข้า modal ก่อน */}
            <div className="mt-2 grid sm:grid-cols-2 gap-2">
              <div
                role="button"
                tabIndex={0}
                onClick={() => setPackId(null)}
                onKeyDown={(e) => e.key === "Enter" && setPackId(null)}
                className={`cursor-pointer rounded-xl border p-3 text-left transition ${
                  packId === null ? "border-primary bg-primary/5" : "border-border bg-card hover:bg-muted"
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="text-sm font-medium">⭐ {t("wiz_persona_default")}</div>
                    <div className="mt-0.5 text-xs text-muted-foreground">{t("wiz_persona_default_desc")}</div>
                  </div>
                  <button
                    type="button"
                    title={t("pk_duplicate")}
                    onClick={(e) => { e.stopPropagation(); setPackIntent({ kind: "census" }); }}
                    className="shrink-0 rounded-lg p-1.5 text-muted-foreground hover:bg-primary/10 hover:text-primary-strong"
                  >
                    📋
                  </button>
                </div>
                <div className="mt-1.5 text-[10px] text-muted-foreground">🔒 {t("pk_census_readonly")}</div>
              </div>
              {packs.map((p) => (
                <div
                  key={p.id}
                  role="button"
                  tabIndex={0}
                  onClick={() => setPackId(p.id)}
                  onKeyDown={(e) => e.key === "Enter" && setPackId(p.id)}
                  className={`cursor-pointer rounded-xl border p-3 text-left transition ${
                    packId === p.id ? "border-primary bg-primary/5" : "border-border bg-card hover:bg-muted"
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium">★ {p.label}</div>
                      <div className="mt-0.5 line-clamp-1 text-xs text-muted-foreground">
                        {p.segments.length} {t("wiz_pool_unit")} · {p.segments.map((s) => s.name).join(", ")}
                      </div>
                    </div>
                    <div className="flex shrink-0 gap-0.5">
                      <button
                        type="button"
                        title={t("pk_edit_btn")}
                        onClick={(e) => { e.stopPropagation(); setPackIntent({ kind: "edit", pack: p }); }}
                        className="rounded-lg p-1.5 text-muted-foreground hover:bg-primary/10 hover:text-primary-strong"
                      >
                        ✏️
                      </button>
                      <button
                        type="button"
                        title={t("pk_delete_ok")}
                        onClick={(e) => { e.stopPropagation(); setPackToDelete(p); }}
                        className="rounded-lg p-1.5 text-muted-foreground hover:bg-red-50 hover:text-red-600"
                      >
                        🗑
                      </button>
                    </div>
                  </div>
                  <div className="mt-2">
                    <StackedBar parts={p.segments.map((s) => ({ label: s.name, value: s.share }))} />
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-2 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setPackIntent({ kind: "blank" })}
                className="inline-flex items-center gap-1 rounded-lg border border-border bg-card px-3 py-1.5 text-xs text-primary-strong hover:bg-primary/5"
              >
                + {t("pk_new_blank")}
              </button>
              <button
                type="button"
                onClick={() => setPackIntent({ kind: "ai" })}
                className="inline-flex items-center gap-1 rounded-lg border border-border bg-card px-3 py-1.5 text-xs text-primary-strong hover:bg-primary/5"
              >
                ✨ {t("pk_new_ai")}
              </button>
            </div>

            {/* พูลของ persona — เห็นองค์ประกอบก่อนรัน (P6-M6) */}
            {pool.length > 0 && (
              <div className="mt-3 rounded-xl border border-border bg-background p-3">
                <button type="button" onClick={() => setPoolOpen(!poolOpen)} className="flex w-full items-center justify-between text-xs font-medium text-muted-foreground">
                  <span>👥 {t("wiz_pool_title")} ({pool.length} {t("wiz_pool_unit")})</span>
                  <span>{poolOpen ? "▲" : "▼"}</span>
                </button>
                {poolOpen && (
                  <div className="mt-2 space-y-1.5">
                    {pool.map((s) => {
                      const est = Math.round(s.share * Math.min(agents, cap));
                      return (
                        <div key={s.id} className="flex items-center gap-2 text-xs">
                          <span className="w-40 shrink-0 truncate">{s.name}</span>
                          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-secondary">
                            <div className="h-full bg-primary" style={{ width: `${s.share * 100}%` }} />
                          </div>
                          <span className="w-9 shrink-0 text-right tabular-nums text-muted-foreground">{pct(s.share)}</span>
                          {est < 30 && <span title={t("pk_low_n_warning").replace("{n}", String(est)).replace("{total}", String(Math.min(agents, cap)))}>⚠️</span>}
                        </div>
                      );
                    })}
                    {pool.some((s) => Math.round(s.share * Math.min(agents, cap)) < 30) && (
                      <p className="pt-1 text-[11px] text-amber-700">⚠️ {t("pk_low_n_note")}</p>
                    )}
                    <p className="pt-1 text-[11px] text-muted-foreground">{t("wiz_pool_note")}</p>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* มุมมองผลลัพธ์ที่จะเปิดใช้ (P6-M6) */}
          <div>
            <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t("wiz_views_title")}</div>
            <p className="mt-1 text-xs text-muted-foreground">{t("wiz_views_desc")}</p>
            <div className="mt-2 grid grid-cols-2 gap-2">
              {([
                ["overview", "📊", t("wiz_view_overview")],
                ["debate", "🗣", t("wiz_view_debate")],
                ["canvas", "🫧", t("wiz_view_canvas")],
                ["evidence", "🔍", t("wiz_view_evidence")],
              ] as const)
                .filter(([id]) => id !== "debate" || isDebate) // การถกเถียงเฉพาะ debate engine
                .map(([id, icon, label]) => {
                  const on = views.includes(id) || id === "overview";
                  return (
                    <button
                      key={id}
                      type="button"
                      disabled={id === "overview"}
                      onClick={() => setViews(on ? views.filter((v) => v !== id) : [...views, id])}
                      className={`flex items-center gap-2 rounded-xl border p-2.5 text-left text-sm transition disabled:opacity-100 ${
                        on ? "border-primary bg-primary/5" : "border-border bg-card hover:bg-muted"
                      }`}
                    >
                      <span>{icon}</span>
                      <span className="flex-1">{label}</span>
                      {on && <span className="text-xs text-primary-strong">✓</span>}
                    </button>
                  );
                })}
            </div>
          </div>

          {/* เลือก ON = โทนเขียว primary (มติผู้ใช้ 12 ก.ค. — สถานะ "เปิดใช้" ควรสื่อเชิงบวก) */}
          <button
            type="button"
            onClick={() => setRedTeam(!redTeam)}
            className={`flex w-full items-start gap-3 rounded-xl border p-3 text-left transition ${redTeam ? "border-primary bg-primary/5" : "border-border bg-card hover:bg-muted"}`}
          >
            <span className="mt-0.5 text-lg">🛡️</span>
            <span className="flex-1">
              <span className="flex items-center gap-2 text-sm font-medium">
                {isDebate ? t("wiz_redteam_debate_title") : t("wiz_redteam_title")}
                {redTeam && <span className="rounded-full bg-primary/15 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-primary-strong">ON</span>}
              </span>
              <span className="mt-0.5 block text-xs text-muted-foreground">
                {isDebate ? t("wiz_redteam_debate_desc") : t("wiz_redteam_desc")}
              </span>
            </span>
          </button>
        </div>
      )}

      {stepKey === "review" && (
        <div className={card + " space-y-3 text-sm"}>
          <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t("wiz_review")}</div>
          <div className="rounded-xl border border-border bg-background p-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t("wiz_readiness")}</div>
                <div className="mt-1 text-sm font-medium">{readiness ? (readiness.can_run ? t("wiz_ready") : t("wiz_needs_review")) : t("wiz_checking")}</div>
              </div>
              <div className="text-right text-xs text-muted-foreground">
                <div>{t("wiz_estimated_cost")}</div>
                <div className="text-base font-semibold text-foreground">{formatCurrency(readiness?.cost?.estimated_usd ?? 0, { minimumFractionDigits: 4, maximumFractionDigits: 4 })}</div>
              </div>
            </div>
            {readiness && (
              <div className="mt-3 grid gap-1.5 md:grid-cols-2">
                {readiness.checks.map((c) => (
                  <div key={c.id} className={`rounded-lg border px-3 py-2 text-xs ${c.status === "block" ? "border-red-200 bg-red-50 text-red-700" : c.status === "warn" ? "border-amber-200 bg-amber-50 text-amber-700" : "border-primary/20 bg-primary/5 text-primary-strong"}`}>
                    <span className="font-medium">{c.label}</span>
                    <span className="ml-2 text-muted-foreground">{c.detail}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
          <div className="grid grid-cols-[130px_1fr] gap-y-2">
            <span className="text-muted-foreground">{t("wiz_step1")}</span><span className="font-medium">{subject || "—"}</span>
            <span className="text-muted-foreground">{t("wiz_step_engine")}</span><span>{isDebate ? "🗣 Debate" : "⚙ Fabric"}{isDebate ? ` · ${rounds} ${t("wiz_rounds_unit")}` : ` · ${t("wiz_universes_short")}`}</span>
            <span className="text-muted-foreground">{t("wiz_agents")}</span><span>{formatNumber(Math.min(agents, cap))}</span>
            <span className="text-muted-foreground">{t("wiz_persona_title")}</span><span>{packId == null ? t("wiz_persona_default") : `★ ${packs.find((p) => p.id === packId)?.label ?? packId}`}</span>
            {isDebate && sources.length > 0 && (<><span className="text-muted-foreground">{t("wiz_src_title")}</span><span>{sources.length} {t("wiz_src_unit")}</span></>)}
            <span className="text-muted-foreground">{t("wiz_redteam_label")}</span><span>{redTeam ? (engine === "fabric" ? `🛡️ ${t("wiz_redteam_on")}` : `🛡️ ON`) : "—"}</span>
          </div>
          {isDebate && <p className="text-xs text-amber-700">💰 {t("wiz_cost_note")}</p>}

          <p className="text-xs text-muted-foreground">🔒 {t("wiz_persist_note")}</p>
        </div>
      )}

      <div className="flex justify-between">
        <button className="px-5 py-2.5 rounded-xl text-sm border border-border text-muted-foreground disabled:opacity-40" disabled={step === 0} onClick={() => setStep(step - 1)}>
          {t("back")}
        </button>
        {step < lastStep ? (
          <button
            className="bg-primary hover:bg-primary-strong text-white px-6 py-2.5 rounded-xl text-sm font-medium disabled:opacity-40"
            disabled={step === 0 && subject.trim().length < 4}
            onClick={() => setStep(step + 1)}
          >
            {t("next")}
          </button>
        ) : (
          <button className="bg-primary hover:bg-primary-strong text-white px-6 py-2.5 rounded-xl text-sm font-medium disabled:opacity-60" disabled={busy || readiness?.can_run === false} onClick={submit}>
            {busy ? `⏳ ${t("running")}` : t("run_now")}
          </button>
        )}
      </div>
      <PersonaPackModal
        intent={packIntent}
        limits={packLimits}
        agents={Math.min(agents, cap)}
        onClose={() => setPackIntent(null)}
        onSaved={(id) => {
          loadPacks();
          if (id == null) return;
          if (id === packId) {
            // แก้ pack ที่เลือกอยู่ — effect [packId] ไม่ยิงเอง ต้อง refetch pool ตรงๆ
            fetchPool(packId).then((d) => setPool(d.segments)).catch(() => {});
          } else {
            setPackId(id); // pack ใหม่/pack อื่นที่เพิ่งบันทึก → เลือกใช้ให้เลย
          }
        }}
        subject={subject}
      />
      <ConfirmDialog
        open={packToDelete != null}
        title={t("pk_delete_title")}
        message={packToDelete ? `"${packToDelete.label}" — ${t("pk_delete_confirm")}` : ""}
        confirmLabel={t("pk_delete_ok")}
        cancelLabel={t("confirm_cancel")}
        danger
        onCancel={() => setPackToDelete(null)}
        onConfirm={async () => {
          const p = packToDelete;
          setPackToDelete(null);
          if (!p) return;
          try {
            await deletePack(p.id);
            if (p.id === packId) setPackId(null); // pack ที่เลือกอยู่ถูกลบ → กลับสำมะโน
            loadPacks();
          } catch (e: any) {
            setError(String(e.message ?? e));
          }
        }}
      />
    </div>
  );
}
