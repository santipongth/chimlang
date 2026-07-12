import { useState } from "react";
import {
  PackSegment,
  PersonaPack,
  deletePack,
  fetchPool,
  generatePack,
  pct,
  savePack,
  tryAsk,
  updatePack,
} from "./api";
import { useLang } from "./i18n";
import { Slider, Tabs } from "./ui";

// Persona Pack Editor (P8 — ผู้ใช้ขอแก้กลุ่ม/media diet เองได้, มติ: modal ใน wizard เท่านั้น)
// 3 tabs แบบ studio: เลือก (Pick) / แก้ไข (Edit) / ให้ AI ร่าง — ทุกทาง save ผ่าน validate_pack
// (PII gate GOV-01 fail-closed ฝั่ง backend); สำมะโน = อ่านอย่างเดียว + ทำสำเนาไปแก้ (มติผู้ใช้)

type TabId = "pick" | "edit" | "ai";

interface Draft {
  label: string;
  prompt: string;
  segments: PackSegment[];
  editingId: number | null; // null = pack ใหม่, id = แก้ pack เดิม
  origin: "census" | "pack" | "ai" | "blank";
}

const CHANNELS = ["line_closed_group", "public_feed", "algo_feed", "offline_wom"] as const;
const PRIORS = ["kreng_jai", "say_do_gap", "sarcasm_meme"] as const;

function newSegment(n: number): PackSegment {
  return {
    id: `seg_${Date.now()}_${n}`,
    name: "",
    share: 0.1,
    voice_activity: 0.5,
    cultural_priors: { kreng_jai: 0.5, say_do_gap: 0.4, sarcasm_meme: 0.3 },
    channel_mix: { line_closed_group: 0.25, public_feed: 0.25, algo_feed: 0.25, offline_wom: 0.25 },
    traits: [],
  };
}

function normalize(values: Record<string, number>): Record<string, number> {
  const total = Object.values(values).reduce((a, b) => a + b, 0);
  if (total <= 0) return values;
  return Object.fromEntries(Object.entries(values).map(([k, v]) => [k, v / total]));
}

// stacked bar แสดงสัดส่วน (share รวม / channel_mix) — สีไล่ opacity ของ primary
function StackedBar({ parts }: { parts: { label: string; value: number }[] }) {
  const total = parts.reduce((a, p) => a + p.value, 0) || 1;
  return (
    <div className="flex h-2.5 w-full overflow-hidden rounded-full bg-secondary">
      {parts.map((p, i) => (
        <div
          key={i}
          title={`${p.label}: ${pct(p.value / total)}`}
          className="h-full bg-primary"
          style={{ width: `${(p.value / total) * 100}%`, opacity: 0.35 + 0.65 * ((i % 4) / 3) }}
        />
      ))}
    </div>
  );
}

export default function PersonaPackModal({
  open,
  onClose,
  onSaved,
  onPick,
  packs,
  selectedPackId,
  subject,
}: {
  open: boolean;
  onClose: () => void;
  onSaved: (savedId?: number) => void;
  onPick: (packId: number | null) => void;
  packs: PersonaPack[];
  selectedPackId: number | null;
  subject: string;
}) {
  const { t } = useLang();
  const [tab, setTab] = useState<TabId>("pick");
  const [draft, setDraft] = useState<Draft | null>(null);
  const [openIdx, setOpenIdx] = useState(0);
  const [busy, setBusy] = useState<"gen" | "save" | "dup" | number | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [question, setQuestion] = useState(subject);
  const [aiPrompt, setAiPrompt] = useState("");
  const [aiLabel, setAiLabel] = useState("");
  const [traitDraft, setTraitDraft] = useState("");

  if (!open) return null;

  const confirmOverwrite = () =>
    !draft || draft.segments.length === 0 || window.confirm(t("pk_overwrite_confirm"));

  function openDraft(d: Draft) {
    setDraft(d);
    setOpenIdx(0);
    setAnswers({});
    setNotice("");
    setError("");
    setTab("edit");
  }

  async function duplicateCensus() {
    if (!confirmOverwrite()) return;
    setBusy("dup");
    setError("");
    try {
      const pool = await fetchPool(null);
      openDraft({
        label: t("pk_census_copy_label"),
        prompt: "",
        editingId: null,
        origin: "census",
        segments: pool.segments.map((s) => ({
          id: s.id,
          name: s.name,
          share: s.share,
          voice_activity: s.voice_activity ?? 0.5,
          cultural_priors: { ...s.cultural_priors } as PackSegment["cultural_priors"],
          channel_mix: { ...s.channel_mix },
          traits: [...s.traits],
        })),
      });
    } catch (e: any) {
      setError(String(e.message ?? e));
    } finally {
      setBusy(null);
    }
  }

  function editPack(p: PersonaPack) {
    if (!confirmOverwrite()) return;
    openDraft({
      label: p.label,
      prompt: p.prompt,
      editingId: p.id,
      origin: "pack",
      segments: p.segments.map((s) => ({
        ...s,
        cultural_priors: { ...s.cultural_priors },
        channel_mix: { ...s.channel_mix },
        traits: [...s.traits],
      })),
    });
  }

  async function removePack(p: PersonaPack) {
    if (!window.confirm(t("pk_delete_confirm"))) return;
    try {
      await deletePack(p.id);
      if (p.id === selectedPackId) onPick(null); // pack ที่เลือกอยู่ถูกลบ → กลับ census
      if (draft?.editingId === p.id) setDraft(null);
      onSaved();
    } catch (e: any) {
      setError(String(e.message ?? e));
    }
  }

  async function generate() {
    if (aiPrompt.trim().length < 8 || !confirmOverwrite()) return;
    setBusy("gen");
    setError("");
    try {
      const segments = await generatePack(aiLabel.trim() || aiPrompt.slice(0, 40), aiPrompt.trim());
      openDraft({
        label: aiLabel.trim() || aiPrompt.slice(0, 40),
        prompt: aiPrompt.trim(),
        segments,
        editingId: null,
        origin: "ai",
      });
      setNotice(t("pk_ai_to_edit_note"));
    } catch (e: any) {
      setError(String(e.message ?? e));
    } finally {
      setBusy(null);
    }
  }

  function patchSegment(i: number, patch: Partial<PackSegment>) {
    if (!draft) return;
    const segments = draft.segments.map((s, j) => (j === i ? { ...s, ...patch } : s));
    setDraft({ ...draft, segments });
  }

  async function save() {
    if (!draft) return;
    setBusy("save");
    setError("");
    try {
      // auto-normalize ให้ผ่าน validate (tolerance 0.01) — แจ้งผู้ใช้เมื่อปรับจริง
      let adjusted = false;
      const shareTotal = draft.segments.reduce((a, s) => a + s.share, 0);
      let segments = draft.segments;
      if (Math.abs(shareTotal - 1) > 0.005 && shareTotal > 0) {
        segments = segments.map((s) => ({ ...s, share: s.share / shareTotal }));
        adjusted = true;
      }
      segments = segments.map((s) => {
        const mixTotal = Object.values(s.channel_mix).reduce((a, b) => a + b, 0);
        if (Math.abs(mixTotal - 1) > 0.005 && mixTotal > 0) {
          adjusted = true;
          return { ...s, channel_mix: normalize(s.channel_mix) };
        }
        return s;
      });
      const label = draft.label.trim() || t("pk_untitled");
      if (draft.editingId != null) {
        await updatePack(draft.editingId, label, segments, draft.prompt);
        onSaved(draft.editingId);
      } else {
        await savePack(label, segments, draft.prompt);
        onSaved();
      }
      setNotice(adjusted ? t("pk_normalized_notice") : t("pk_saved"));
      setDraft(null);
      setTab("pick");
    } catch (e: any) {
      setError(String(e.message ?? e));
    } finally {
      setBusy(null);
    }
  }

  async function ask(i: number) {
    if (!draft || question.trim().length < 4) return;
    setBusy(i);
    try {
      const ans = await tryAsk(draft.segments[i], question.trim());
      setAnswers((a) => ({ ...a, [draft.segments[i].id]: ans }));
    } catch (e: any) {
      setError(String(e.message ?? e));
    } finally {
      setBusy(null);
    }
  }

  const shareTotal = draft?.segments.reduce((a, s) => a + s.share, 0) ?? 0;
  const card = "rounded-xl border border-border bg-background";

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/30 p-4" onClick={onClose}>
      <div
        className="max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-2xl border border-border bg-card p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h3 className="font-display text-2xl font-semibold">👥 {t("pk_title")}</h3>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">✕</button>
        </div>
        <p className="mt-1 text-sm text-muted-foreground">{t("pk_desc")}</p>

        <div className="mt-4">
          <Tabs<TabId>
            tabs={[
              { id: "pick", label: `📚 ${t("pk_tab_pick")}` },
              { id: "edit", label: `🎛 ${t("pk_tab_edit")}${draft ? " •" : ""}` },
              { id: "ai", label: `✨ ${t("pk_tab_ai")}` },
            ]}
            active={tab}
            onChange={setTab}
          />
        </div>

        {error && (
          <div className="mt-3 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>
        )}
        {notice && !error && (
          <div className="mt-3 rounded-xl border border-primary/30 bg-primary/5 p-3 text-sm text-primary-strong">
            ✅ {notice}
          </div>
        )}

        {/* ---------- Tab เลือก ---------- */}
        {tab === "pick" && (
          <div className="mt-4 space-y-2">
            <div
              className={`${card} flex flex-wrap items-center justify-between gap-2 p-4 ${selectedPackId == null ? "border-primary bg-primary/5" : ""}`}
            >
              <div className="min-w-0">
                <div className="font-medium">⭐ {t("wiz_persona_default")}</div>
                <div className="text-xs text-muted-foreground">🔒 {t("pk_census_readonly")}</div>
              </div>
              <div className="flex shrink-0 gap-2">
                <button
                  onClick={() => { onPick(null); onClose(); }}
                  className="rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-white hover:bg-primary-strong"
                >
                  {t("pk_use_in_run")}
                </button>
                <button
                  onClick={duplicateCensus}
                  disabled={busy === "dup"}
                  className="rounded-lg border border-border px-3 py-1.5 text-xs text-primary-strong hover:bg-primary/5 disabled:opacity-40"
                >
                  {busy === "dup" ? "⏳" : `📋 ${t("pk_duplicate")}`}
                </button>
              </div>
            </div>
            {packs.map((p) => (
              <div
                key={p.id}
                className={`${card} flex flex-wrap items-center justify-between gap-2 p-4 ${selectedPackId === p.id ? "border-primary bg-primary/5" : ""}`}
              >
                <div className="min-w-0">
                  <div className="font-medium">★ {p.label}</div>
                  <div className="truncate text-xs text-muted-foreground">
                    {p.segments.length} {t("wiz_pool_unit")} · {p.segments.map((s) => s.name).join(", ")}
                  </div>
                </div>
                <div className="flex shrink-0 gap-2">
                  <button
                    onClick={() => { onPick(p.id); onClose(); }}
                    className="rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-white hover:bg-primary-strong"
                  >
                    {t("pk_use_in_run")}
                  </button>
                  <button
                    onClick={() => editPack(p)}
                    className="rounded-lg border border-border px-3 py-1.5 text-xs text-primary-strong hover:bg-primary/5"
                  >
                    ✏️ {t("pk_edit_btn")}
                  </button>
                  <button
                    onClick={() => removePack(p)}
                    className="rounded-lg border border-border px-3 py-1.5 text-xs text-muted-foreground hover:text-red-600"
                  >
                    🗑
                  </button>
                </div>
              </div>
            ))}
            {packs.length === 0 && (
              <p className="px-1 text-xs text-muted-foreground">{t("pk_no_packs_hint")}</p>
            )}
          </div>
        )}

        {/* ---------- Tab แก้ไข ---------- */}
        {tab === "edit" && !draft && (
          <div className="mt-6 rounded-xl border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
            {t("pk_no_draft")}
          </div>
        )}
        {tab === "edit" && draft && (
          <div className="mt-4 space-y-3">
            <div className="flex items-center gap-2">
              <input
                value={draft.label}
                onChange={(e) => setDraft({ ...draft, label: e.target.value })}
                placeholder={t("pk_label_ph")}
                className="flex-1 rounded-xl border border-border bg-background px-4 py-2.5 text-sm"
              />
              {draft.editingId != null && (
                <span className="shrink-0 rounded-full bg-muted px-2.5 py-1 text-[10px] text-muted-foreground">
                  ✏️ {t("pk_editing_existing")} #{draft.editingId}
                </span>
              )}
            </div>

            {/* สัดส่วนรวมของทุกกลุ่ม */}
            <div className={`${card} p-3`}>
              <div className="flex items-center justify-between text-xs">
                <span className="font-semibold uppercase tracking-wider text-muted-foreground">
                  {t("pk_share_total")}
                </span>
                <span className="flex items-center gap-2">
                  <span className={`tabular-nums font-medium ${Math.abs(shareTotal - 1) > 0.01 ? "text-amber-600" : "text-primary-strong"}`}>
                    {pct(shareTotal)}
                  </span>
                  {Math.abs(shareTotal - 1) > 0.01 && (
                    <button
                      onClick={() => {
                        const norm = normalize(Object.fromEntries(draft.segments.map((s, i) => [i, s.share])));
                        setDraft({ ...draft, segments: draft.segments.map((s, i) => ({ ...s, share: norm[i] })) });
                      }}
                      className="rounded-lg border border-border px-2 py-1 text-[10px] text-primary-strong hover:bg-primary/5"
                    >
                      ⚖️ {t("pk_normalize")}
                    </button>
                  )}
                </span>
              </div>
              <div className="mt-2">
                <StackedBar parts={draft.segments.map((s) => ({ label: s.name || "?", value: s.share }))} />
              </div>
            </div>

            {/* ลองถาม — คำถามเดียวใช้ทุกกลุ่ม */}
            <input
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder={t("pk_ask_ph")}
              className="w-full rounded-xl border border-border bg-background px-3 py-2 text-xs"
            />

            {/* การ์ดต่อกลุ่ม (พับได้) */}
            {draft.segments.map((s, i) => (
              <div key={s.id} className={`${card}`}>
                <button
                  onClick={() => setOpenIdx(openIdx === i ? -1 : i)}
                  className="flex w-full items-center justify-between px-4 py-3 text-left text-sm"
                >
                  <span className="min-w-0 truncate font-medium">
                    {s.name || `(${t("pk_unnamed")})`}
                    <span className="ml-2 text-xs text-muted-foreground">{pct(s.share)}</span>
                  </span>
                  <span className="text-muted-foreground">{openIdx === i ? "▲" : "▼"}</span>
                </button>
                {openIdx === i && (
                  <div className="space-y-3 border-t border-border px-4 py-3">
                    <input
                      value={s.name}
                      onChange={(e) => patchSegment(i, { name: e.target.value })}
                      placeholder={t("pk_seg_name_ph")}
                      className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
                    />
                    <Slider
                      label={t("pk_share")}
                      value={s.share}
                      min={0.01}
                      max={0.8}
                      step={0.01}
                      display={pct(s.share)}
                      onChange={(v) => patchSegment(i, { share: v })}
                    />
                    <div className="grid gap-3 sm:grid-cols-2">
                      <Slider
                        label={t("pk_voice")}
                        value={s.voice_activity}
                        onChange={(v) => patchSegment(i, { voice_activity: v })}
                      />
                      {PRIORS.map((k) => (
                        <Slider
                          key={k}
                          label={t(`pk_prior_${k}`)}
                          value={s.cultural_priors[k] ?? 0.5}
                          onChange={(v) =>
                            patchSegment(i, { cultural_priors: { ...s.cultural_priors, [k]: v } })
                          }
                        />
                      ))}
                    </div>

                    {/* media diet — คุมทั้ง fabric engine และข่าวจากโต๊ะข่าวสด */}
                    <div className="rounded-lg border border-border bg-card p-3">
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-semibold uppercase tracking-wider text-muted-foreground">
                          📡 {t("pk_media_diet")}
                        </span>
                        {Math.abs(Object.values(s.channel_mix).reduce((a, b) => a + b, 0) - 1) > 0.01 && (
                          <button
                            onClick={() => patchSegment(i, { channel_mix: normalize(s.channel_mix) })}
                            className="rounded-lg border border-border px-2 py-1 text-[10px] text-primary-strong hover:bg-primary/5"
                          >
                            ⚖️ {t("pk_normalize")}
                          </button>
                        )}
                      </div>
                      <p className="mt-1 text-[11px] text-muted-foreground">{t("pk_media_diet_note")}</p>
                      <div className="mt-2">
                        <StackedBar
                          parts={CHANNELS.map((ch) => ({ label: t(`pk_ch_${ch}`), value: s.channel_mix[ch] ?? 0 }))}
                        />
                      </div>
                      <div className="mt-2 grid gap-3 sm:grid-cols-2">
                        {CHANNELS.map((ch) => (
                          <Slider
                            key={ch}
                            label={t(`pk_ch_${ch}`)}
                            value={s.channel_mix[ch] ?? 0}
                            step={0.05}
                            display={pct(s.channel_mix[ch] ?? 0)}
                            onChange={(v) =>
                              patchSegment(i, { channel_mix: { ...s.channel_mix, [ch]: v } })
                            }
                          />
                        ))}
                      </div>
                    </div>

                    {/* traits chips */}
                    <div>
                      <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                        {t("pk_traits")}
                      </div>
                      <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                        {s.traits.map((tr, j) => (
                          <span key={j} className="flex items-center gap-1 rounded-full bg-muted px-2.5 py-1 text-[11px]">
                            {tr}
                            <button
                              onClick={() => patchSegment(i, { traits: s.traits.filter((_, x) => x !== j) })}
                              className="text-muted-foreground hover:text-red-600"
                            >
                              ✕
                            </button>
                          </span>
                        ))}
                        <input
                          value={openIdx === i ? traitDraft : ""}
                          onChange={(e) => setTraitDraft(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" && traitDraft.trim()) {
                              patchSegment(i, { traits: [...s.traits, traitDraft.trim()] });
                              setTraitDraft("");
                            }
                          }}
                          placeholder={t("pk_trait_add_ph")}
                          className="min-w-[160px] flex-1 rounded-lg border border-border bg-background px-2.5 py-1 text-[11px]"
                        />
                      </div>
                    </div>

                    <div className="flex items-center justify-between">
                      <button
                        onClick={() => ask(i)}
                        disabled={busy === i}
                        className="rounded-lg border border-border px-3 py-1.5 text-xs text-primary-strong hover:bg-primary/5 disabled:opacity-40"
                      >
                        {busy === i ? "⏳" : `💬 ${t("pk_try_ask")}`}
                      </button>
                      <button
                        onClick={() => {
                          setDraft({ ...draft, segments: draft.segments.filter((_, x) => x !== i) });
                          setOpenIdx(-1);
                        }}
                        disabled={draft.segments.length <= 2}
                        className="text-xs text-muted-foreground hover:text-red-600 disabled:opacity-30"
                      >
                        🗑 {t("pk_remove_segment")}
                      </button>
                    </div>
                    {answers[s.id] && (
                      <div className="rounded-lg border border-primary/20 bg-primary/5 px-3 py-2 text-xs">
                        💬 “{answers[s.id]}”
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}

            <div className="flex flex-wrap items-center gap-2">
              <button
                onClick={() => {
                  setDraft({ ...draft, segments: [...draft.segments, newSegment(draft.segments.length)] });
                  setOpenIdx(draft.segments.length);
                }}
                disabled={draft.segments.length >= 8}
                className="rounded-xl border border-border px-4 py-2 text-sm text-primary-strong hover:bg-primary/5 disabled:opacity-40"
              >
                + {t("pk_add_segment")} ({draft.segments.length}/8)
              </button>
              <div className="flex-1" />
              <button
                onClick={() => { setDraft(null); setTab("pick"); }}
                className="rounded-xl border border-border px-4 py-2 text-sm text-muted-foreground hover:bg-muted"
              >
                {t("pk_discard")}
              </button>
              <button
                onClick={save}
                disabled={busy === "save"}
                className="rounded-xl bg-primary px-5 py-2 text-sm font-medium text-white hover:bg-primary-strong disabled:opacity-40"
              >
                {busy === "save" ? "⏳" : `💾 ${draft.editingId != null ? t("pk_save_update") : t("pk_save")}`}
              </button>
            </div>
          </div>
        )}

        {/* ---------- Tab ให้ AI ร่าง ---------- */}
        {tab === "ai" && (
          <div className="mt-4 space-y-2">
            <p className="text-xs text-muted-foreground">🛡️ {t("pk_gov_note")}</p>
            <input
              value={aiLabel}
              onChange={(e) => setAiLabel(e.target.value)}
              placeholder={t("pk_label_ph")}
              className="w-full rounded-xl border border-border bg-background px-4 py-2.5 text-sm"
            />
            <textarea
              value={aiPrompt}
              onChange={(e) => setAiPrompt(e.target.value)}
              placeholder={t("pk_prompt_ph")}
              rows={3}
              className="w-full rounded-xl border border-border bg-background px-4 py-2.5 text-sm"
            />
            <button
              onClick={generate}
              disabled={busy === "gen" || aiPrompt.trim().length < 8}
              className="rounded-xl bg-primary px-5 py-2 text-sm font-medium text-white disabled:opacity-40"
            >
              {busy === "gen" ? `⏳ ${t("pk_generating")}` : `✨ ${t("pk_generate")}`}
            </button>
            <p className="text-[11px] text-muted-foreground">💡 {t("pk_ai_to_edit_note")}</p>
          </div>
        )}
      </div>
    </div>
  );
}
