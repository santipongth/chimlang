import { useEffect, useState } from "react";
import { AppSettings, PersonaPack, deletePack, fetchPacks, fetchSettings, saveSettings } from "../api";
import { useLang } from "../i18n";
import { PageHeader, SelectCard } from "../ui";

// Settings (P6-M4) — ค่า default + จัดการ persona packs + สถานะระบบ (secrets อยู่ .env เท่านั้น)

export default function Settings() {
  const { t } = useLang();
  const [data, setData] = useState<AppSettings | null>(null);
  const [packs, setPacks] = useState<PersonaPack[]>([]);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  const load = () => {
    fetchSettings().then(setData).catch((e) => setError(String(e.message ?? e)));
    fetchPacks().then(setPacks).catch(() => {});
  };
  useEffect(load, []);

  const card = "bg-card border border-border rounded-2xl p-6";

  async function patch(p: Partial<AppSettings>) {
    if (!data) return;
    setError("");
    try {
      await saveSettings(p);
      setData({ ...data, ...p });
      setMsg(t("set_saved"));
      setTimeout(() => setMsg(""), 1500);
    } catch (e: any) {
      setError(String(e.message ?? e));
    }
  }

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

          <section className={card}>
            <h2 className="font-semibold mb-3">★ Persona packs</h2>
            {packs.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t("set_no_packs")}</p>
            ) : (
              <ul className="space-y-2 text-sm">
                {packs.map((p) => (
                  <li key={p.id} className="flex items-center justify-between rounded-xl border border-border bg-background px-4 py-2.5">
                    <div className="min-w-0">
                      <div className="font-medium">{p.label}</div>
                      <div className="truncate text-xs text-muted-foreground">{p.segments.map((s) => s.name).join(", ")}</div>
                    </div>
                    <button
                      onClick={() => deletePack(p.id).then(load)}
                      className="shrink-0 text-xs text-muted-foreground hover:text-red-600"
                    >
                      🗑 {t("set_delete")}
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <p className="mt-3 text-xs text-muted-foreground">{t("set_packs_note")}</p>
          </section>

          <section className={card + " text-sm space-y-2"}>
            <h2 className="font-semibold">{t("set_system")}</h2>
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
    </div>
  );
}
