import { useState } from "react";
import { PackSegment, generatePack, savePack, tryAsk } from "./api";
import { useLang } from "./i18n";
import { pct } from "./api";

// Persona Pack Modal (P5-M7 — pattern จาก studio): AI-generate จาก prompt → preview
// → "ลอง ask" ราย segment → บันทึก (มนุษย์ตรวจก่อนบันทึกเสมอ — ไม่ auto-save)

export default function PersonaPackModal({
  open,
  onClose,
  onSaved,
  subject,
}: {
  open: boolean;
  onClose: () => void;
  onSaved: () => void;
  subject: string;
}) {
  const { t } = useLang();
  const [label, setLabel] = useState("");
  const [prompt, setPrompt] = useState("");
  const [segments, setSegments] = useState<PackSegment[] | null>(null);
  const [busy, setBusy] = useState<"gen" | "save" | number | null>(null);
  const [error, setError] = useState("");
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [question, setQuestion] = useState(subject);

  if (!open) return null;

  async function generate() {
    if (prompt.trim().length < 8) return;
    setBusy("gen");
    setError("");
    setAnswers({});
    try {
      setSegments(await generatePack(label.trim() || prompt.slice(0, 40), prompt.trim()));
    } catch (e: any) {
      setError(String(e.message ?? e));
    } finally {
      setBusy(null);
    }
  }

  async function save() {
    if (!segments) return;
    setBusy("save");
    setError("");
    try {
      await savePack(label.trim() || prompt.slice(0, 40), segments, prompt.trim());
      onSaved();
      onClose();
      setSegments(null);
      setPrompt("");
      setLabel("");
    } catch (e: any) {
      setError(String(e.message ?? e));
    } finally {
      setBusy(null);
    }
  }

  async function ask(i: number) {
    if (!segments || question.trim().length < 4) return;
    setBusy(i);
    try {
      const ans = await tryAsk(segments[i], question.trim());
      setAnswers((a) => ({ ...a, [segments[i].id]: ans }));
    } catch (e: any) {
      setError(String(e.message ?? e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/30 p-4" onClick={onClose}>
      <div
        className="max-h-[88vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-border bg-card p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h3 className="font-display text-2xl font-semibold">✨ {t("pk_title")}</h3>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">✕</button>
        </div>
        <p className="mt-1 text-sm text-muted-foreground">{t("pk_desc")}</p>
        <p className="mt-1 text-xs text-muted-foreground">🛡️ {t("pk_gov_note")}</p>

        <div className="mt-4 space-y-2">
          <input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder={t("pk_label_ph")}
            className="w-full rounded-xl border border-border bg-background px-4 py-2.5 text-sm"
          />
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder={t("pk_prompt_ph")}
            rows={3}
            className="w-full rounded-xl border border-border bg-background px-4 py-2.5 text-sm"
          />
          <button
            onClick={generate}
            disabled={busy === "gen" || prompt.trim().length < 8}
            className="rounded-xl bg-primary px-5 py-2 text-sm font-medium text-white disabled:opacity-40"
          >
            {busy === "gen" ? `⏳ ${t("pk_generating")}` : `✨ ${t("pk_generate")}`}
          </button>
        </div>

        {error && <div className="mt-3 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}

        {segments && (
          <div className="mt-4 space-y-3">
            <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              {t("pk_preview")} ({segments.length} segments)
            </div>
            {/* ลอง ask — คำถามเดียวยิงราย segment */}
            <div className="flex gap-2">
              <input
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder={t("pk_ask_ph")}
                className="flex-1 rounded-xl border border-border bg-background px-3 py-2 text-xs"
              />
            </div>
            {segments.map((s, i) => (
              <div key={s.id} className="rounded-xl border border-border bg-background p-3 text-sm">
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <div className="font-medium">
                    {s.name} <span className="text-xs text-muted-foreground">({pct(s.share)})</span>
                  </div>
                  <button
                    onClick={() => ask(i)}
                    disabled={busy === i}
                    className="rounded-lg border border-border px-3 py-1 text-xs text-primary-strong hover:bg-primary/5 disabled:opacity-40"
                  >
                    {busy === i ? "⏳" : `💬 ${t("pk_try_ask")}`}
                  </button>
                </div>
                <div className="mt-1 flex flex-wrap gap-1.5 text-[11px] text-muted-foreground">
                  <span className="rounded-full bg-muted px-2 py-0.5">{t("pk_prior_kreng")} {s.cultural_priors.kreng_jai}</span>
                  <span className="rounded-full bg-muted px-2 py-0.5">say-do gap {s.cultural_priors.say_do_gap}</span>
                  <span className="rounded-full bg-muted px-2 py-0.5">{t("pk_prior_meme")} {s.cultural_priors.sarcasm_meme}</span>
                  <span className="rounded-full bg-muted px-2 py-0.5">{t("pk_prior_voice")} {s.voice_activity}</span>
                </div>
                {s.traits.length > 0 && (
                  <div className="mt-1 text-xs text-muted-foreground">{s.traits.join(" · ")}</div>
                )}
                {answers[s.id] && (
                  <div className="mt-2 rounded-lg bg-primary/5 border border-primary/20 px-3 py-2 text-xs">
                    💬 “{answers[s.id]}”
                  </div>
                )}
              </div>
            ))}
            <div className="flex gap-2">
              <button
                onClick={save}
                disabled={busy === "save"}
                className="rounded-xl bg-primary px-5 py-2 text-sm font-medium text-white disabled:opacity-40"
              >
                {busy === "save" ? "⏳" : `💾 ${t("pk_save")}`}
              </button>
              <button onClick={() => setSegments(null)} className="rounded-xl border border-border px-4 py-2 text-sm text-muted-foreground">
                {t("pk_discard")}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
