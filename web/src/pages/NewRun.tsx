import { useEffect, useState } from "react";
import { useLang } from "../i18n";
import { PageHeader, SelectCard } from "../ui";
import {
  EngineInfo,
  PersonaPack,
  PoolSegment,
  SourceInput,
  createRun,
  fetchEngines,
  fetchPacks,
  fetchPool,
  fetchSettings,
  pct,
} from "../api";
import PersonaPackModal from "../PersonaPackModal";
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
  const { lang, t } = useLang();
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
  const [packModalOpen, setPackModalOpen] = useState(false);
  const [sources, setSources] = useState<SourceInput[]>([]);
  const [claim, setClaim] = useState("");
  const [measurement, setMeasurement] = useState("");
  const [dueDays, setDueDays] = useState(30);
  const [pool, setPool] = useState<PoolSegment[]>([]);
  const [poolOpen, setPoolOpen] = useState(false);
  const [views, setViews] = useState<string[]>(["overview", "debate", "canvas", "evidence"]);
  const [srcDraft, setSrcDraft] = useState<{ kind: "url" | "rss" | "text"; label: string; value: string }>({ kind: "url", label: "", value: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const loadPacks = () => fetchPacks().then(setPacks).catch(() => {});
  // โหลดพูลของ persona ทุกครั้งที่เปลี่ยน pack (P6-M6)
  useEffect(() => {
    fetchPool(packId).then((d) => setPool(d.segments)).catch(() => setPool([]));
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
    try {
      const runId = await createRun({
        engine,
        subject: subject.trim(),
        domain,
        agents: Math.min(agents, cap),
        rounds,
        pack_id: packId,
        red_team: redTeam,
        sources: isDebate ? sources : [],
        claim: claim.trim(),
        measurement: measurement.trim(),
        due_days: dueDays,
        views,
      });
      onCreated(runId);
    } catch (e: any) {
      setError(String(e.message ?? e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader eyebrow={t("wiz_eyebrow")} title={t("wiz_title")} />
      <Steps step={step} labels={labels} onJump={setStep} />
      {error && <div className="bg-red-50 border border-red-200 text-red-700 rounded-2xl p-4 text-sm">{error}</div>}

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
          <p className="text-xs text-muted-foreground">🔮 {t("wiz_engine_future")}</p>
        </div>
      )}

      {stepKey === "sources" && (
        <div className={card + " space-y-4"}>
          <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">📎 {t("wiz_src_title")}</div>
          <p className="text-xs text-muted-foreground">{t("wiz_src_desc")}</p>
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
            <button onClick={addSource} className="rounded-xl border border-border px-4 py-2 text-sm text-primary-strong hover:bg-primary/5">
              + {t("wiz_src_add")}
            </button>
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
                <span className="text-sm font-medium">{n.toLocaleString()} agents</span>
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
            <div className="mt-2 grid sm:grid-cols-2 gap-2">
              <SelectCard active={packId === null} onClick={() => setPackId(null)}>
                <div className="text-sm font-medium">{t("wiz_persona_default")}</div>
                <div className="mt-0.5 text-xs text-muted-foreground">{t("wiz_persona_default_desc")}</div>
              </SelectCard>
              {packs.map((p) => (
                <SelectCard key={p.id} active={packId === p.id} onClick={() => setPackId(p.id)}>
                  <div className="text-sm font-medium">★ {p.label}</div>
                  <div className="mt-0.5 line-clamp-1 text-xs text-muted-foreground">{p.segments.map((s) => s.name).join(", ")}</div>
                </SelectCard>
              ))}
            </div>
            <button type="button" onClick={() => setPackModalOpen(true)} className="mt-2 inline-flex items-center gap-1 rounded-lg border border-border bg-card px-3 py-1.5 text-xs text-primary-strong hover:bg-primary/5">
              ✨ {t("wiz_persona_create")}
            </button>

            {/* พูลของ persona — เห็นองค์ประกอบก่อนรัน (P6-M6) */}
            {pool.length > 0 && (
              <div className="mt-3 rounded-xl border border-border bg-background p-3">
                <button type="button" onClick={() => setPoolOpen(!poolOpen)} className="flex w-full items-center justify-between text-xs font-medium text-muted-foreground">
                  <span>👥 {t("wiz_pool_title")} ({pool.length} {t("wiz_pool_unit")})</span>
                  <span>{poolOpen ? "▲" : "▼"}</span>
                </button>
                {poolOpen && (
                  <div className="mt-2 space-y-1.5">
                    {pool.map((s) => (
                      <div key={s.id} className="flex items-center gap-2 text-xs">
                        <span className="w-40 shrink-0 truncate">{s.name}</span>
                        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-secondary">
                          <div className="h-full bg-primary" style={{ width: `${s.share * 100}%` }} />
                        </div>
                        <span className="w-9 shrink-0 text-right tabular-nums text-muted-foreground">{pct(s.share)}</span>
                      </div>
                    ))}
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
          <div className="grid grid-cols-[130px_1fr] gap-y-2">
            <span className="text-muted-foreground">{t("wiz_step1")}</span><span className="font-medium">{subject || "—"}</span>
            <span className="text-muted-foreground">Engine</span><span>{isDebate ? "🗣 Debate" : "⚙ Fabric"}{isDebate ? ` · ${rounds} ${t("wiz_rounds_unit")}` : ` · ${t("wiz_universes_short")}`}</span>
            <span className="text-muted-foreground">{t("wiz_agents")}</span><span>{Math.min(agents, cap).toLocaleString()}</span>
            <span className="text-muted-foreground">Personas</span><span>{packId == null ? t("wiz_persona_default") : `★ ${packs.find((p) => p.id === packId)?.label ?? packId}`}</span>
            {isDebate && sources.length > 0 && (<><span className="text-muted-foreground">{t("wiz_src_title")}</span><span>{sources.length} {t("wiz_src_unit")}</span></>)}
            <span className="text-muted-foreground">Red Team</span><span>{redTeam ? (engine === "fabric" ? `🛡️ ${t("wiz_redteam_on")}` : `🛡️ ON`) : "—"}</span>
          </div>
          {isDebate && <p className="text-xs text-amber-700">💰 {t("wiz_cost_note")}</p>}

          {/* เหตุการณ์จริง (จุดปลดล็อก calibration): ตั้งคำทำนายที่วัดผลได้เอง */}
          <div className="rounded-xl border border-primary/30 bg-primary/5 p-4 space-y-2">
            <div className="text-xs font-semibold uppercase tracking-wider text-primary-strong">
              🎯 {t("wiz_real_title")}
            </div>
            <p className="text-xs text-muted-foreground">{t("wiz_real_desc")}</p>
            <textarea
              value={claim}
              onChange={(e) => setClaim(e.target.value)}
              placeholder={t("wiz_claim_ph")}
              rows={2}
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
            />
            <div className="grid gap-2 sm:grid-cols-[1fr_150px]">
              <input
                value={measurement}
                onChange={(e) => setMeasurement(e.target.value)}
                placeholder={t("wiz_measure_ph")}
                className="rounded-lg border border-border bg-background px-3 py-2 text-sm"
              />
              <label className="flex items-center gap-2 text-xs text-muted-foreground">
                {t("wiz_due_days")}
                <input
                  type="number"
                  min={1}
                  max={365}
                  value={dueDays}
                  onChange={(e) => setDueDays(parseInt(e.target.value) || 30)}
                  className="w-16 rounded-lg border border-border bg-background px-2 py-2 text-sm text-foreground"
                />
              </label>
            </div>
          </div>
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
          <button className="bg-primary hover:bg-primary-strong text-white px-6 py-2.5 rounded-xl text-sm font-medium disabled:opacity-60" disabled={busy} onClick={submit}>
            {busy ? `⏳ ${t("running")}` : t("run_now")}
          </button>
        )}
      </div>
      <PersonaPackModal open={packModalOpen} onClose={() => setPackModalOpen(false)} onSaved={loadPacks} subject={subject} />
    </div>
  );
}
