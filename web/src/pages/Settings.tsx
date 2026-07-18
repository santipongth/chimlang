import { useEffect, useState } from "react";
import { Save } from "lucide-react";
import {
  AppSettings,
  DeepHealth,
  ProductPolicy,
  RunMetrics,
  fetchDeepHealth,
  fetchProductPolicy,
  fetchRunMetrics,
  fetchSettings,
  saveLlmKey,
  saveSettings,
  saveTavilyKey,
} from "../api";
import { useLang } from "../i18n";
import { ConfirmDialog, PageHeader, SelectCard } from "../ui";

// Settings (P6-M4) — ค่า default + จัดการ persona packs + สถานะระบบ (secrets อยู่ .env เท่านั้น)

export default function Settings() {
  const { t, formatCurrency } = useLang();
  const usd = (value: number) =>
    formatCurrency(value, { minimumFractionDigits: 2, maximumFractionDigits: 4 });
  const [data, setData] = useState<AppSettings | null>(null);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [health, setHealth] = useState<DeepHealth | null>(null);
  const [metrics, setMetrics] = useState<RunMetrics | null>(null);
  const [policy, setPolicy] = useState<ProductPolicy | null>(null);
  const [keyDraft, setKeyDraft] = useState("");
  const [keyBusy, setKeyBusy] = useState(false);
  const [prices, setPrices] = useState<Record<string, { input_usd_per_m: number; output_usd_per_m: number }>>({});
  const [newModel, setNewModel] = useState("");
  const [tavilyDraft, setTavilyDraft] = useState("");
  const [tavilyBusy, setTavilyBusy] = useState(false);
  const [budgetDraft, setBudgetDraft] = useState({ run: "", monthly: "" });
  const [budgetBusy, setBudgetBusy] = useState(false);
  // ล้าง key ที่เก็บใน DB — ยืนยันผ่าน dialog ของเราเองก่อนเสมอ (มติผู้ใช้ 13 ก.ค.)
  const [keyToClear, setKeyToClear] = useState<"llm" | "tavily" | null>(null);

  const load = () => {
    fetchSettings()
      .then((d) => {
        setData(d);
        setBudgetDraft({
          run: String(d.run_budget_usd_cap),
          monthly: String(d.monthly_budget_usd_cap),
        });
        // ราคาที่แสดง = yaml (มาตรฐาน) ทับด้วยที่ผู้ใช้แก้ไว้
        setPrices({ ...(d.llm?.yaml_prices ?? {}), ...(d.llm_prices ?? {}) });
      })
      .catch((e) => setError(String(e.message ?? e)));
    fetchDeepHealth().then(setHealth).catch(() => setHealth(null));
    fetchRunMetrics().then(setMetrics).catch(() => setMetrics(null));
    fetchProductPolicy().then(setPolicy).catch(() => setPolicy(null));
  };
  useEffect(load, []);

  async function saveKey() {
    setKeyBusy(true);
    setError("");
    try {
      await saveLlmKey(keyDraft.trim());
      setKeyDraft("");
      await load();
      setMsg(t("set_saved"));
      setTimeout(() => setMsg(""), 1500);
    } catch (e: any) {
      setError(String(e.message ?? e));
    } finally {
      setKeyBusy(false);
    }
  }

  const card = "bg-card border border-border rounded-2xl p-6";

  async function patch(p: Partial<AppSettings>) {
    if (!data) return;
    setError("");
    try {
      const saved = await saveSettings(p);
      setData(saved);
      setMsg(t("set_saved"));
      setTimeout(() => setMsg(""), 1500);
    } catch (e: any) {
      setError(String(e.message ?? e));
    }
  }

  async function saveBudget() {
    const run = Number(budgetDraft.run);
    const monthly = Number(budgetDraft.monthly);
    if (
      budgetDraft.run.trim() === "" ||
      budgetDraft.monthly.trim() === "" ||
      !Number.isFinite(run) ||
      !Number.isFinite(monthly) ||
      run < 0 ||
      monthly < 0 ||
      run > 100000 ||
      monthly > 100000
    ) {
      setError(t("set_budget_invalid"));
      return;
    }

    setBudgetBusy(true);
    setError("");
    try {
      const saved = await saveSettings({
        run_budget_usd_cap: run,
        monthly_budget_usd_cap: monthly,
      });
      setData(saved);
      setBudgetDraft({
        run: String(saved.run_budget_usd_cap),
        monthly: String(saved.monthly_budget_usd_cap),
      });
      setMsg(t("set_budget_saved"));
      setTimeout(() => setMsg(""), 2000);
    } catch (e: any) {
      setError(String(e.message ?? e));
    } finally {
      setBudgetBusy(false);
    }
  }

  const draftRun = Number(budgetDraft.run);
  const draftMonthly = Number(budgetDraft.monthly);
  const budgetDraftValid =
    budgetDraft.run.trim() !== "" &&
    budgetDraft.monthly.trim() !== "" &&
    Number.isFinite(draftRun) &&
    Number.isFinite(draftMonthly) &&
    draftRun >= 0 &&
    draftMonthly >= 0 &&
    draftRun <= 100000 &&
    draftMonthly <= 100000;
  const budgetChanged = Boolean(
    data &&
      (draftRun !== data.run_budget_usd_cap || draftMonthly !== data.monthly_budget_usd_cap),
  );

  return (
    <div className="space-y-6">
      <PageHeader eyebrow={t("set_eyebrow")} title={t("set_title")} desc={t("set_sub")} />
      {error && <div className="bg-red-50 border border-red-200 text-red-700 rounded-2xl p-4 text-sm">{error}</div>}
      {msg && <div className="bg-primary-soft border border-primary/30 text-primary-strong rounded-2xl p-3 text-sm">✅ {msg}</div>}

      {data && (
        <>
          <section className={card + " space-y-4"}>
            <h2 className="font-semibold">{t("set_defaults")}</h2>
            <div>
              <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">Engine</div>
              <div className="grid sm:grid-cols-2 gap-2">
                <SelectCard active={data.default_engine === "fabric"} onClick={() => patch({ default_engine: "fabric" })}>
                  <span className="text-sm">⚙ Fabric — $0 · cap {data.caps.fabric}</span>
                </SelectCard>
                <SelectCard active={data.default_engine === "debate"} onClick={() => patch({ default_engine: "debate" })}>
                  <span className="text-sm">🗣 Debate — LLM · cap {data.caps.debate}</span>
                </SelectCard>
              </div>
            </div>
            <div className="grid sm:grid-cols-2 gap-4">
              <label className="text-sm">
                <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Agents (default)</span>
                <input
                  type="number"
                  min={10}
                  max={1000}
                  value={data.default_agents}
                  onChange={(e) => setData({ ...data, default_agents: parseInt(e.target.value) || 100 })}
                  onBlur={() => patch({ default_agents: data.default_agents })}
                  className="mt-1 w-full rounded-xl border border-border bg-background px-4 py-2"
                />
              </label>
              <label className="text-sm">
                <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Debate rounds (default)</span>
                <input
                  type="number"
                  min={1}
                  max={10}
                  value={data.default_rounds}
                  onChange={(e) => setData({ ...data, default_rounds: parseInt(e.target.value) || 3 })}
                  onBlur={() => patch({ default_rounds: data.default_rounds })}
                  className="mt-1 w-full rounded-xl border border-border bg-background px-4 py-2"
                />
              </label>
            </div>
          </section>

          {/* LLM ปรับเองได้ (ADR-0006) — API key ยังตั้งใน .env เท่านั้น
              guard: server เวอร์ชันเก่าไม่มี field llm → ซ่อน section แทน crash ทั้งหน้า */}
          {data.llm && (
          <section className={card + " space-y-4"}>
            <h2 className="font-semibold">🧠 {t("set_llm_title")}</h2>
            <p className="text-xs text-muted-foreground">{t("set_llm_desc")}</p>
            <div className="grid gap-2 sm:grid-cols-3">
              {(data.llm.providers ?? []).map((p) => (
                <SelectCard
                  key={p.key}
                  active={(data.llm_provider || "openrouter") === p.key}
                  onClick={() =>
                    patch({ llm_provider: p.key, llm_base_url: p.base_url } as any)
                  }
                >
                  <div className="text-sm font-medium">{p.label}</div>
                  <div className="mt-0.5 text-[11px] text-muted-foreground">{p.hint_th}</div>
                </SelectCard>
              ))}
            </div>
            <label className="block text-sm">
              <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                {t("set_llm_base_url")}
              </span>
              <input
                value={data.llm_base_url}
                onChange={(e) => setData({ ...data, llm_base_url: e.target.value })}
                onBlur={() => patch({ llm_base_url: data.llm_base_url } as any)}
                placeholder={data.llm.active_base_url || "https://openrouter.ai/api/v1"}
                className="mt-1 w-full rounded-xl border border-border bg-background px-4 py-2 font-mono text-xs"
              />
            </label>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <label className="text-sm">
                <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  {t("set_llm_crowd")}
                </span>
                <input
                  value={data.llm_model_crowd}
                  onChange={(e) => setData({ ...data, llm_model_crowd: e.target.value })}
                  onBlur={() => patch({ llm_model_crowd: data.llm_model_crowd } as any)}
                  placeholder={data.llm.env_model_crowd}
                  className="mt-1 w-full rounded-xl border border-border bg-background px-4 py-2 font-mono text-xs"
                />
              </label>
              <label className="text-sm">
                <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  {t("set_llm_analyst")}
                </span>
                <input
                  value={data.llm_model_analyst}
                  onChange={(e) => setData({ ...data, llm_model_analyst: e.target.value })}
                  onBlur={() => patch({ llm_model_analyst: data.llm_model_analyst } as any)}
                  placeholder={data.llm.env_model_analyst}
                  className="mt-1 w-full rounded-xl border border-border bg-background px-4 py-2 font-mono text-xs"
                />
              </label>
              <label className="text-sm">
                <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Embedding model
                </span>
                <input
                  value={data.llm_model_embedding}
                  onChange={(e) => setData({ ...data, llm_model_embedding: e.target.value })}
                  onBlur={() => patch({ llm_model_embedding: data.llm_model_embedding } as any)}
                  placeholder={data.llm.env_model_embedding || "ไม่ตั้ง = BM25 fallback"}
                  className="mt-1 w-full rounded-xl border border-border bg-background px-4 py-2 font-mono text-xs"
                />
              </label>
              <label className="text-sm">
                <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Vector dimension
                </span>
                <input
                  type="number"
                  min={128}
                  max={4096}
                  value={data.llm_embedding_dimension}
                  onChange={(e) => setData({ ...data, llm_embedding_dimension: parseInt(e.target.value) || 1536 })}
                  onBlur={() => patch({ llm_embedding_dimension: data.llm_embedding_dimension } as any)}
                  className="mt-1 w-full rounded-xl border border-border bg-background px-4 py-2 font-mono text-xs"
                />
              </label>
              <label className="text-sm">
                <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  {t("set_synth_tokens")}
                </span>
                <input
                  type="number"
                  min={0}
                  max={16000}
                  step={500}
                  value={data.llm_synthesis_max_tokens ?? 0}
                  onChange={(e) => setData({ ...data, llm_synthesis_max_tokens: parseInt(e.target.value) || 0 })}
                  onBlur={() => patch({ llm_synthesis_max_tokens: data.llm_synthesis_max_tokens ?? 0 } as any)}
                  placeholder="0"
                  className="mt-1 w-full rounded-xl border border-border bg-background px-4 py-2 font-mono text-xs"
                />
                <span className="mt-1 block text-[11px] text-muted-foreground">{t("set_synth_tokens_note")}</span>
              </label>
            </div>
            {/* API key — เก็บเข้ารหัสใน DB (ADR-0007), แสดงแค่มาสก์ */}
            <div className="rounded-xl border border-border bg-background p-3 space-y-2">
              <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                🔑 {t("set_llm_key")}
              </div>
              <div className="text-xs">
                {data.llm.key_source === "db"
                  ? `✅ ${t("set_key_db")} (${data.llm.key_masked})`
                  : data.llm.key_source === "env"
                    ? `✅ ${t("set_key_env")} (${data.llm.key_masked})`
                    : `⚠️ ${t("set_key_none")}`}
              </div>
              {!data.llm.master_key_present && (
                <div className="rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 text-[11px] text-amber-800">
                  ⚠️ {t("set_key_no_master")}
                </div>
              )}
              <div className="flex flex-wrap gap-2">
                <input
                  type="password"
                  value={keyDraft}
                  onChange={(e) => setKeyDraft(e.target.value)}
                  placeholder={t("set_key_ph")}
                  disabled={!data.llm.master_key_present}
                  className="min-w-40 flex-1 rounded-lg border border-border bg-background px-3 py-2 font-mono text-xs disabled:opacity-50"
                />
                <button
                  onClick={saveKey}
                  disabled={keyBusy || !keyDraft.trim() || !data.llm.master_key_present}
                  className="rounded-lg bg-primary px-4 py-2 text-xs font-medium text-white disabled:opacity-40"
                >
                  {keyBusy ? "⏳" : t("set_key_save")}
                </button>
                {data.llm.key_source === "db" && (
                  <button
                    onClick={() => setKeyToClear("llm")}
                    className="rounded-lg border border-border px-3 py-2 text-xs text-muted-foreground hover:bg-red-50 hover:text-red-600"
                  >
                    🗑 {t("set_key_clear")}
                  </button>
                )}
              </div>
              <p className="text-[11px] text-muted-foreground">🔒 {t("set_key_note")}</p>
            </div>

            <div className="rounded-xl border border-border bg-background p-3 text-xs text-muted-foreground">
              {t("set_llm_active")}: crowd = <code>{data.llm.active_model_crowd || "—"}</code> ·
              analyst = <code>{data.llm.active_model_analyst || "—"}</code>
              {" · "}embedding = <code>{data.llm.active_model_embedding || "BM25 fallback"}</code>
              {data.llm.active_model_embedding ? ` (${data.llm.embedding_dimension}d)` : ""}
            </div>
            <button
              onClick={() =>
                patch({
                  llm_provider: "",
                  llm_base_url: "",
                  llm_model_crowd: "",
                  llm_model_analyst: "",
                  llm_model_embedding: "",
                  llm_embedding_dimension: 1536,
                  llm_synthesis_max_tokens: 0,
                } as any)
              }
              className="rounded-xl border border-border px-4 py-2 text-xs text-muted-foreground hover:bg-muted"
            >
              ↺ {t("set_llm_reset")}
            </button>
          </section>
          )}

          {/* ราคาโมเดล — แก้ราคามาตรฐาน/เพิ่มใหม่ (P6-M5) */}
          {data.llm && (
          <section className={card + " space-y-3"}>
            <h2 className="font-semibold">💵 {t("set_prices_title")}</h2>
            <p className="text-xs text-muted-foreground">{t("set_prices_desc")}</p>
            <div className="space-y-1.5">
              <div className="grid grid-cols-[1fr_90px_90px_28px] gap-2 text-[10px] uppercase tracking-wider text-muted-foreground">
                <span>{t("set_price_model")}</span>
                <span>input /1M</span>
                <span>output /1M</span>
                <span></span>
              </div>
              {Object.entries(prices).map(([model, pr]) => (
                <div key={model} className="grid grid-cols-[1fr_90px_90px_28px] gap-2 items-center">
                  <code className="truncate text-xs">{model}</code>
                  <input
                    type="number"
                    step="0.001"
                    value={pr.input_usd_per_m}
                    onChange={(e) => setPrices({ ...prices, [model]: { ...pr, input_usd_per_m: parseFloat(e.target.value) || 0 } })}
                    onBlur={() => patch({ llm_prices: { ...data.llm_prices, [model]: prices[model] } } as any)}
                    className="rounded border border-border bg-background px-2 py-1 text-xs"
                  />
                  <input
                    type="number"
                    step="0.001"
                    value={pr.output_usd_per_m}
                    onChange={(e) => setPrices({ ...prices, [model]: { ...pr, output_usd_per_m: parseFloat(e.target.value) || 0 } })}
                    onBlur={() => patch({ llm_prices: { ...data.llm_prices, [model]: prices[model] } } as any)}
                    className="rounded border border-border bg-background px-2 py-1 text-xs"
                  />
                  <span className="text-center text-[10px] text-muted-foreground" title={data.llm_prices[model] ? t("set_price_custom") : t("set_price_std")}>
                    {data.llm_prices[model] ? "✎" : ""}
                  </span>
                </div>
              ))}
            </div>
            <div className="flex gap-2">
              <input
                value={newModel}
                onChange={(e) => setNewModel(e.target.value)}
                placeholder={t("set_price_add_ph")}
                className="flex-1 rounded-lg border border-border bg-background px-3 py-2 font-mono text-xs"
              />
              <button
                onClick={() => {
                  const m = newModel.trim();
                  if (!m || prices[m]) return;
                  const next = { ...prices, [m]: { input_usd_per_m: 0, output_usd_per_m: 0 } };
                  setPrices(next);
                  patch({ llm_prices: { ...data.llm_prices, [m]: next[m] } } as any);
                  setNewModel("");
                }}
                className="rounded-lg border border-border px-4 py-2 text-xs text-primary-strong hover:bg-primary/5"
              >
                + {t("set_price_add")}
              </button>
            </div>
          </section>
          )}

          {/* งบประมาณ (P6-M5) */}
          {data.budget && (
            <section className={card + " space-y-4"}>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 className="font-semibold">💰 {t("set_budget_title")}</h2>
                <button
                  type="button"
                  onClick={saveBudget}
                  disabled={budgetBusy || !budgetDraftValid || !budgetChanged}
                  className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-xs font-medium text-white disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <Save size={15} aria-hidden="true" />
                  {budgetBusy ? t("set_budget_saving") : t("set_budget_save")}
                </button>
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <label className="text-sm">
                  <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    {t("set_budget_run")}
                  </span>
                  <input
                    type="number"
                    min="0"
                    max="100000"
                    step="0.5"
                    value={budgetDraft.run}
                    onChange={(e) => setBudgetDraft({ ...budgetDraft, run: e.target.value })}
                    className="mt-1 w-full rounded-xl border border-border bg-background px-4 py-2 tabular-nums"
                  />
                  <span className="mt-1 block text-[11px] text-muted-foreground">
                    {t("set_budget_active")}: {usd(data.budget.run_cap_effective)} · {t("set_budget_env_default")}: {usd(data.budget.env_run_cap)}
                  </span>
                </label>
                <label className="text-sm">
                  <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    {t("set_budget_month")}
                  </span>
                  <input
                    type="number"
                    min="0"
                    max="100000"
                    step="5"
                    value={budgetDraft.monthly}
                    onChange={(e) => setBudgetDraft({ ...budgetDraft, monthly: e.target.value })}
                    className="mt-1 w-full rounded-xl border border-border bg-background px-4 py-2 tabular-nums"
                  />
                  <span className="mt-1 block text-[11px] text-muted-foreground">
                    {t("set_budget_active")}: {usd(data.budget.monthly_cap_effective)} · {t("set_budget_env_default")}: {usd(data.budget.env_monthly_cap)}
                  </span>
                </label>
              </div>
              <div className="border-t border-border pt-4">
                <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                  <span className="text-muted-foreground">{t("set_budget_spent")}</span>
                  <span className="tabular-nums font-medium">
                    {usd(data.budget.spent_this_month)} spent + {usd(data.budget.reserved_this_month)} reserved / {usd(data.budget.monthly_cap_effective)}
                  </span>
                </div>
                <div className="mt-2 h-2 overflow-hidden rounded-full bg-secondary">
                  <div
                    className={`h-full ${(data.budget.spent_this_month + data.budget.reserved_this_month) / Math.max(1, data.budget.monthly_cap_effective) > 0.9 ? "bg-red-500" : "bg-primary"}`}
                    style={{ width: `${Math.min(100, ((data.budget.spent_this_month + data.budget.reserved_this_month) / Math.max(1, data.budget.monthly_cap_effective)) * 100)}%` }}
                  />
                </div>
                <div className={`mt-2 text-xs font-medium ${data.budget.available_this_month <= 0 ? "text-red-600" : "text-emerald-700"}`}>
                  {data.budget.available_this_month <= 0
                    ? `${t("set_budget_over")}: committed budget reached cap`
                    : `${t("set_budget_remaining")}: ${usd(data.budget.available_this_month)}`}
                </div>
                {(data.run_budget_usd_cap === 0 || data.monthly_budget_usd_cap === 0) && (
                  <div className="mt-2 text-[11px] text-muted-foreground">0 = {t("set_budget_from_env")}</div>
                )}
              </div>
            </section>
          )}

          {/* News Desk (P7) — feeds + Tavily key ตั้งจากหน้านี้ (DB ทับ .env) */}
          {data.news && (
          <section className={card + " space-y-3"}>
            <h2 className="font-semibold">🌐 {t("set_news_title")}</h2>
            <p className="text-xs text-muted-foreground">{t("set_news_desc")}</p>
            <label className="block text-sm">
              <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                {t("set_news_feeds")}
              </span>
              <textarea
                value={data.news_rss_feeds}
                onChange={(e) => setData({ ...data, news_rss_feeds: e.target.value })}
                onBlur={() => patch({ news_rss_feeds: data.news_rss_feeds } as any)}
                placeholder="https://www.thairath.co.th/rss/news, https://..."
                rows={2}
                className="mt-1 w-full rounded-xl border border-border bg-background px-4 py-2 font-mono text-xs"
              />
              <span className="text-[11px] text-muted-foreground">
                {t("set_news_feeds_active")}: {data.news.feeds.length} feeds ({data.news.feeds_source === "db" ? t("set_key_db_short") : data.news.feeds_source === "env" ? t("set_key_env_short") : "—"})
              </span>
            </label>
            <div className="rounded-xl border border-border bg-background p-3 space-y-2">
              <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                🔎 Tavily Search API key
              </div>
              <div className="text-xs">
                {data.news.tavily_source === "db"
                  ? `✅ ${t("set_key_db")} (${data.news.tavily_masked})`
                  : data.news.tavily_source === "env"
                    ? `✅ ${t("set_key_env")} (${data.news.tavily_masked})`
                    : `⚠️ ${t("set_tavily_none")}`}
              </div>
              <div className="flex flex-wrap gap-2">
                <input
                  type="password"
                  value={tavilyDraft}
                  onChange={(e) => setTavilyDraft(e.target.value)}
                  placeholder={t("set_key_ph")}
                  disabled={!data.llm?.master_key_present}
                  className="min-w-40 flex-1 rounded-lg border border-border bg-background px-3 py-2 font-mono text-xs disabled:opacity-50"
                />
                <button
                  onClick={async () => {
                    setTavilyBusy(true);
                    try { await saveTavilyKey(tavilyDraft.trim()); setTavilyDraft(""); await load(); }
                    catch (e: any) { setError(String(e.message ?? e)); }
                    finally { setTavilyBusy(false); }
                  }}
                  disabled={tavilyBusy || !tavilyDraft.trim() || !data.llm?.master_key_present}
                  className="rounded-lg bg-primary px-4 py-2 text-xs font-medium text-white disabled:opacity-40"
                >
                  {tavilyBusy ? "⏳" : t("set_key_save")}
                </button>
                {data.news.tavily_source === "db" && (
                  <button
                    onClick={() => setKeyToClear("tavily")}
                    className="rounded-lg border border-border px-3 py-2 text-xs text-muted-foreground hover:bg-red-50 hover:text-red-600"
                  >
                    🗑 {t("set_key_clear")}
                  </button>
                )}
              </div>
              {!data.llm?.master_key_present && (
                <p className="text-[11px] text-amber-700">⚠️ {t("set_key_no_master")}</p>
              )}
            </div>
          </section>
          )}

          {policy && (
            <section className={card + " space-y-4"} aria-labelledby="active-policy-title">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <h2 id="active-policy-title" className="font-semibold">
                    {t("set_policy_title")}
                  </h2>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {t("set_policy_note")}
                  </p>
                </div>
                <code className="rounded-lg bg-muted px-2 py-1 text-[11px]">{policy.version}</code>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                {policy.items.map((item) => (
                  <article key={item.key} className="rounded-xl border border-border bg-background p-4">
                    <div className="flex items-center justify-between gap-2">
                      <h3 className="text-sm font-semibold">
                        {{
                          pricing_metering: "Pricing / metering",
                          source_strategy: "Open-source strategy",
                          election_eligibility: "Election Mode eligibility",
                          semantic_memory: "Semantic memory",
                        }[item.key]}
                      </h3>
                      <span className="rounded-full bg-primary-soft px-2 py-0.5 text-[10px] font-medium text-primary-strong">
                        {item.status}
                      </span>
                    </div>
                    <code className="mt-2 block break-words text-[11px] text-foreground">
                      {item.active_default}
                    </code>
                    <p className="mt-2 text-xs text-muted-foreground">{item.rationale}</p>
                    <p className="mt-2 border-t border-border pt-2 text-[11px] text-muted-foreground">
                      <strong className="text-foreground">เกณฑ์ก่อนเปลี่ยน:</strong> {item.change_gate}
                    </p>
                  </article>
                ))}
              </div>
            </section>
          )}

          <section className={card + " text-sm space-y-2"}>
            <h2 className="font-semibold">{t("set_system")}</h2>
            {health && (
              <div className="rounded-xl border border-border bg-background p-3">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-medium">{t("set_health")}</span>
                  <span className={health.status === "ok" ? "text-primary-strong" : "text-amber-700"}>
                    {health.status === "ok" ? "✅ ok" : `⚠️ ${health.status}`}
                  </span>
                </div>
                <div className="mt-2 grid gap-1 sm:grid-cols-3">
                  {Object.entries(health.components).map(([name, status]) => (
                    <span key={name} className="rounded-lg border border-border px-2 py-1 text-xs">
                      {status === "ok" ? "✅" : "⚠️"} {name}: {status}
                    </span>
                  ))}
                </div>
              </div>
            )}
            {metrics && (
              <div className="rounded-xl border border-border bg-background p-3">
                <div className="text-xs font-medium">Operational metrics</div>
                <div className="mt-2 grid gap-1 sm:grid-cols-4">
                  <span className="rounded-lg border border-border px-2 py-1 text-xs">
                    queue: {Math.round(metrics.avg_queue_wait_s)}s
                  </span>
                  <span className="rounded-lg border border-border px-2 py-1 text-xs">
                    runtime: {Math.round(metrics.avg_runtime_s)}s
                  </span>
                  <span className="rounded-lg border border-border px-2 py-1 text-xs">
                    errors 24h: {metrics.errors_24h}
                  </span>
                  <span className="rounded-lg border border-border px-2 py-1 text-xs">
                    spend: ${metrics.spent_this_month.toFixed(2)}
                  </span>
                </div>
              </div>
            )}
            <div className="grid grid-cols-[180px_1fr] gap-y-1.5 text-muted-foreground">
              <span>Webhook (Slack/Discord)</span>
              <span className="text-foreground">{data.webhook_configured ? `✅ ${t("set_webhook_on")}` : `— ${t("set_webhook_off")}`}</span>
              <span>Auth (X-API-Key)</span>
              <span className="text-foreground">{data.auth_enabled ? "✅ เปิด" : `⚠️ ${t("set_auth_dev")}`}</span>
            </div>
            <p className="text-xs text-muted-foreground">🔒 {t("set_secret_note")}</p>
          </section>
        </>
      )}

      <ConfirmDialog
        open={keyToClear != null}
        title={t("set_key_clear_title")}
        message={t("set_key_clear_confirm")}
        confirmLabel={t("set_key_clear")}
        cancelLabel={t("confirm_cancel")}
        danger
        onCancel={() => setKeyToClear(null)}
        onConfirm={async () => {
          const which = keyToClear;
          setKeyToClear(null);
          if (!which) return;
          try {
            if (which === "llm") await saveLlmKey("");
            else await saveTavilyKey("");
            await load();
          } catch (e: any) {
            setError(String(e.message ?? e));
          }
        }}
      />
    </div>
  );
}
