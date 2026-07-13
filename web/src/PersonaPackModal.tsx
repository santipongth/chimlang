import { useEffect, useState } from "react";
import {
  FALLBACK_PACK_LIMITS,
  PackLimits,
  PackSegment,
  PersonaPack,
  fetchPool,
  generatePack,
  pct,
  savePack,
  tryAsk,
  updatePack,
} from "./api";
import { useLang } from "./i18n";
import { ConfirmDialog, Slider, Tabs } from "./ui";

// Persona Pack Editor (P8) — redesign 13 ก.ค.: รายการ pack + เพิ่ม/ลบ อยู่หน้า wizard โดยตรง
// modal นี้ = "ตัวแก้ไข" อย่างเดียว (แก้ไข / ให้ AI ร่าง) — เปิดด้วย intent จาก parent
// ทุกทาง save ผ่าน validate_pack (PII gate GOV-01 fail-closed ฝั่ง backend)

export type PackModalIntent =
  | { kind: "edit"; pack: PersonaPack } // แก้ pack เดิม
  | { kind: "census" } // ทำสำเนาสำมะโนไปแก้ (สำมะโนจริงอ่านอย่างเดียว — มติผู้ใช้)
  | { kind: "blank" } // สร้าง pack เปล่าเอง
  | { kind: "ai" }; // ให้ AI ร่างจากคำบรรยาย

type TabId = "edit" | "ai";

interface Draft {
  label: string;
  prompt: string;
  segments: PackSegment[];
  editingId: number | null; // null = pack ใหม่, id = แก้ pack เดิม
}

const CHANNELS = ["line_closed_group", "public_feed", "algo_feed", "offline_wom"] as const;
const PRIORS = ["kreng_jai", "say_do_gap", "sarcasm_meme"] as const;

function newSegment(n: number, share = 0.5): PackSegment {
  return {
    id: `seg_${Date.now()}_${n}`,
    name: "",
    share,
    voice_activity: 0.5,
    cultural_priors: { kreng_jai: 0.5, say_do_gap: 0.4, sarcasm_meme: 0.3 },
    channel_mix: { line_closed_group: 0.25, public_feed: 0.25, algo_feed: 0.25, offline_wom: 0.25 },
    traits: [],
  };
}

function cloneSegment(s: PackSegment): PackSegment {
  return {
    ...s,
    cultural_priors: { ...s.cultural_priors },
    channel_mix: { ...s.channel_mix },
    traits: [...s.traits],
  };
}

function normalize(values: Record<string, number>): Record<string, number> {
  const total = Object.values(values).reduce((a, b) => a + b, 0);
  if (total <= 0) return values;
  return Object.fromEntries(Object.entries(values).map(([k, v]) => [k, v / total]));
}

// stacked bar แสดงสัดส่วน (share รวม / channel_mix) — สีไล่ opacity ของ primary
export function StackedBar({ parts }: { parts: { label: string; value: number }[] }) {
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
  intent,
  onClose,
  onSaved,
  subject,
  limits = FALLBACK_PACK_LIMITS,
  agents,
}: {
  intent: PackModalIntent | null;
  onClose: () => void;
  onSaved: (savedId?: number) => void;
  subject: string;
  limits?: PackLimits;
  agents?: number; // จำนวน agent ของรันปัจจุบัน — ใช้เตือนกลุ่มที่ n ต่ำเกิน (< 30)
}) {
  const { t } = useLang();
  const open = intent != null;
  const [tab, setTab] = useState<TabId>("edit");
  const [draft, setDraft] = useState<Draft | null>(null);
  const [openIdx, setOpenIdx] = useState(0);
  const [busy, setBusy] = useState<"gen" | "save" | "census" | number | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [question, setQuestion] = useState("");
  const [aiPrompt, setAiPrompt] = useState("");
  const [aiLabel, setAiLabel] = useState("");
  const [traitDraft, setTraitDraft] = useState("");
  const [confirmGen, setConfirmGen] = useState(false); // AI ร่างทับร่างที่แก้ค้าง

  // เริ่มร่างใหม่ตาม intent ทุกครั้งที่เปิด
  useEffect(() => {
    if (!intent) return;
    setError("");
    setNotice("");
    setAnswers({});
    setOpenIdx(0);
    setTraitDraft("");
    setConfirmGen(false);
    setQuestion(subject);
    if (intent.kind === "edit") {
      setDraft({
        label: intent.pack.label,
        prompt: intent.pack.prompt,
        editingId: intent.pack.id,
        segments: intent.pack.segments.map(cloneSegment),
      });
      setTab("edit");
    } else if (intent.kind === "blank") {
      setDraft({
        label: "",
        prompt: "",
        editingId: null,
        segments: [newSegment(0), newSegment(1)],
      });
      setTab("edit");
    } else if (intent.kind === "ai") {
      setDraft(null);
      setAiPrompt("");
      setAiLabel("");
      setTab("ai");
    } else {
      setDraft(null);
      setTab("edit");
      void loadCensusCopy();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intent]);

  // Escape = ปิด modal (ยกเว้นตอน confirm dialog เปิดอยู่ — ให้ dialog จัดการเอง)
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !confirmGen) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, confirmGen, onClose]);

  if (!open) return null;

  async function loadCensusCopy() {
    setBusy("census");
    setError("");
    try {
      const pool = await fetchPool(null);
      setDraft({
        label: t("pk_census_copy_label"),
        prompt: "",
        editingId: null,
        segments: pool.segments.map((s) =>
          cloneSegment({
            id: s.id,
            name: s.name,
            share: s.share,
            voice_activity: s.voice_activity ?? 0.5,
            cultural_priors: s.cultural_priors,
            channel_mix: s.channel_mix,
            traits: s.traits,
          })
        ),
      });
    } catch (e: any) {
      setError(String(e.message ?? e));
    } finally {
      setBusy(null);
    }
  }

  function requestGenerate() {
    if (aiPrompt.trim().length < 8) return;
    if (draft && draft.segments.length > 0) {
      setConfirmGen(true);
      return;
    }
    void generate();
  }

  async function generate() {
    setBusy("gen");
    setError("");
    try {
      const label = aiLabel.trim() || aiPrompt.slice(0, 40);
      const segments = await generatePack(label, aiPrompt.trim());
      setDraft({ label, prompt: aiPrompt.trim(), segments, editingId: null });
      setOpenIdx(0);
      setAnswers({});
      setNotice(t("pk_ai_to_edit_note"));
      setTab("edit");
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
      // auto-normalize ให้ผ่าน validate (tolerance 0.01) — แถบสัดส่วนใน UI โชว์ค่าจริงตลอด
      const shareTotal = draft.segments.reduce((a, s) => a + s.share, 0);
      let segments = draft.segments;
      if (Math.abs(shareTotal - 1) > 0.005 && shareTotal > 0) {
        segments = segments.map((s) => ({ ...s, share: s.share / shareTotal }));
      }
      segments = segments.map((s) => {
        const mixTotal = Object.values(s.channel_mix).reduce((a, b) => a + b, 0);
        if (Math.abs(mixTotal - 1) > 0.005 && mixTotal > 0) {
          return { ...s, channel_mix: normalize(s.channel_mix) };
        }
        return s;
      });
      const label = draft.label.trim() || t("pk_untitled");
      let savedId: number;
      if (draft.editingId != null) {
        await updatePack(draft.editingId, label, segments, draft.prompt);
        savedId = draft.editingId;
      } else {
        savedId = await savePack(label, segments, draft.prompt);
      }
      onSaved(savedId);
      onClose();
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
    <>
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4 backdrop-blur-[2px]"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        className="flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* header คงที่ */}
        <div className="border-b border-border px-6 pb-3 pt-5">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h3 className="font-display text-xl font-semibold leading-tight">
                {draft?.editingId != null ? `✏️ ${t("pk_title_edit")}` : `👥 ${t("pk_title_new")}`}
              </h3>
              <p className="mt-0.5 text-xs text-muted-foreground">{t("pk_desc")}</p>
            </div>
            <button
              onClick={onClose}
              aria-label="close"
              className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              ✕
            </button>
          </div>
          <div className="mt-3">
            <Tabs<TabId>
              tabs={[
                { id: "edit", label: `🎛 ${t("pk_tab_edit")}` },
                { id: "ai", label: `✨ ${t("pk_tab_ai")}` },
              ]}
              active={tab}
              onChange={setTab}
            />
          </div>
        </div>

        {/* เนื้อหา scroll ได้ */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {error && (
            <div className="mb-3 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">
              {error}
            </div>
          )}
          {notice && !error && (
            <div className="mb-3 rounded-xl border border-primary/30 bg-primary/5 p-3 text-sm text-primary-strong">
              ✅ {notice}
            </div>
          )}

          {/* ---------- Tab แก้ไข ---------- */}
          {tab === "edit" && !draft && (
            <div className="rounded-xl border border-dashed border-border p-10 text-center text-sm text-muted-foreground">
              {busy === "census" ? `⏳ ${t("pk_loading_census")}` : t("pk_no_draft")}
            </div>
          )}
          {tab === "edit" && draft && (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <input
                  value={draft.label}
                  onChange={(e) => setDraft({ ...draft, label: e.target.value })}
                  placeholder={t("pk_label_ph")}
                  className="flex-1 rounded-xl border border-border bg-background px-4 py-2.5 text-sm"
                />
              </div>

              {/* สัดส่วนรวมของทุกกลุ่ม */}
              <div className={`${card} p-3`}>
                <div className="flex items-center justify-between text-xs">
                  <span className="font-semibold uppercase tracking-wider text-muted-foreground">
                    {t("pk_share_total")}
                  </span>
                  <span className="flex items-center gap-2">
                    <span
                      className={`tabular-nums font-medium ${Math.abs(shareTotal - 1) > 0.01 ? "text-amber-600" : "text-primary-strong"}`}
                    >
                      {pct(shareTotal)}
                    </span>
                    {Math.abs(shareTotal - 1) > 0.01 && (
                      <button
                        onClick={() => {
                          const norm = normalize(
                            Object.fromEntries(draft.segments.map((s, i) => [i, s.share]))
                          );
                          setDraft({
                            ...draft,
                            segments: draft.segments.map((s, i) => ({ ...s, share: norm[i] })),
                          });
                        }}
                        className="rounded-lg border border-border px-2 py-1 text-[10px] text-primary-strong hover:bg-primary/5"
                      >
                        ⚖️ {t("pk_normalize")}
                      </button>
                    )}
                  </span>
                </div>
                <div className="mt-2">
                  <StackedBar
                    parts={draft.segments.map((s) => ({ label: s.name || "?", value: s.share }))}
                  />
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
                      {agents != null && Math.round(s.share * agents) < 30 && (
                        <p className="text-[11px] text-amber-700">
                          ⚠️ {t("pk_low_n_warning")
                            .replace("{n}", String(Math.round(s.share * agents)))
                            .replace("{total}", String(agents))}
                        </p>
                      )}
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
                          {Math.abs(Object.values(s.channel_mix).reduce((a, b) => a + b, 0) - 1) >
                            0.01 && (
                            <button
                              onClick={() => patchSegment(i, { channel_mix: normalize(s.channel_mix) })}
                              className="rounded-lg border border-border px-2 py-1 text-[10px] text-primary-strong hover:bg-primary/5"
                            >
                              ⚖️ {t("pk_normalize")}
                            </button>
                          )}
                        </div>
                        <p className="mt-1 text-[11px] text-muted-foreground">
                          {t("pk_media_diet_note")}
                        </p>
                        <div className="mt-2">
                          <StackedBar
                            parts={CHANNELS.map((ch) => ({
                              label: t(`pk_ch_${ch}`),
                              value: s.channel_mix[ch] ?? 0,
                            }))}
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
                            <span
                              key={j}
                              className="flex items-center gap-1 rounded-full bg-muted px-2.5 py-1 text-[11px]"
                            >
                              {tr}
                              <button
                                onClick={() =>
                                  patchSegment(i, { traits: s.traits.filter((_, x) => x !== j) })
                                }
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
                          disabled={draft.segments.length <= limits.min_segments}
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

              <button
                onClick={() => {
                  setDraft({
                    ...draft,
                    segments: [...draft.segments, newSegment(draft.segments.length, 0.1)],
                  });
                  setOpenIdx(draft.segments.length);
                }}
                disabled={draft.segments.length >= limits.max_segments}
                className="w-full rounded-xl border border-dashed border-border px-4 py-2.5 text-sm text-primary-strong hover:bg-primary/5 disabled:opacity-40"
              >
                + {t("pk_add_segment")} ({draft.segments.length}/{limits.max_segments})
              </button>
            </div>
          )}

          {/* ---------- Tab ให้ AI ร่าง ---------- */}
          {tab === "ai" && (
            <div className="space-y-2">
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
                rows={4}
                className="w-full rounded-xl border border-border bg-background px-4 py-2.5 text-sm"
              />
              <button
                onClick={requestGenerate}
                disabled={busy === "gen" || aiPrompt.trim().length < 8}
                className="rounded-xl bg-primary px-5 py-2 text-sm font-medium text-white hover:bg-primary-strong disabled:opacity-40"
              >
                {busy === "gen" ? `⏳ ${t("pk_generating")}` : `✨ ${t("pk_generate")}`}
              </button>
              <p className="text-[11px] text-muted-foreground">💡 {t("pk_ai_to_edit_note")}</p>
            </div>
          )}
        </div>

        {/* footer action คงที่ (เฉพาะตอนมีร่างให้บันทึก) */}
        {tab === "edit" && draft && (
          <div className="flex items-center justify-end gap-2 border-t border-border bg-card px-6 py-3.5">
            <button
              onClick={onClose}
              className="rounded-xl border border-border px-4 py-2 text-sm text-muted-foreground hover:bg-muted"
            >
              {t("pk_discard")}
            </button>
            <button
              onClick={save}
              disabled={busy === "save"}
              className="rounded-xl bg-primary px-5 py-2 text-sm font-medium text-white hover:bg-primary-strong disabled:opacity-40"
            >
              {busy === "save"
                ? "⏳"
                : `💾 ${draft.editingId != null ? t("pk_save_update") : t("pk_save")}`}
            </button>
          </div>
        )}
      </div>
    </div>

    {/* ยืนยันทับร่างเดิมเมื่อสั่ง AI ร่างซ้ำ — dialog ของเราเอง ไม่ใช่ popup ระบบ */}
    <ConfirmDialog
      open={confirmGen}
      title={t("pk_overwrite_title")}
      message={t("pk_overwrite_confirm")}
      confirmLabel={t("pk_overwrite_ok")}
      cancelLabel={t("confirm_cancel")}
      onCancel={() => setConfirmGen(false)}
      onConfirm={() => {
        setConfirmGen(false);
        void generate();
      }}
    />
    </>
  );
}
