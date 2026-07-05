import { useState } from "react";
import { CHOICES, ImpactResult, STANCES, fetchImpact, pct, sendFeedback } from "../api";
import { useLang } from "../i18n";

export default function Citizen() {
  const { t } = useLang();
  const [form, setForm] = useState<Record<string, string | number>>({
    income_band: CHOICES.income_band[1],
    region: CHOICES.region[2],
    commute: CHOICES.commute[1],
    occupation: CHOICES.occupation[0],
    age_band: CHOICES.age_band[1],
    household_size: 3,
  });
  const [result, setResult] = useState<ImpactResult | null>(null);
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const LABELS: Record<keyof typeof CHOICES, string> = {
    income_band: t("f_income"),
    region: t("f_region"),
    commute: t("f_commute"),
    occupation: t("f_occupation"),
    age_band: t("f_age"),
  };

  const card = "bg-card border border-border rounded-2xl p-6";
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    fetchImpact(form)
      .then(setResult)
      .catch((er) => setError(String(er.message ?? er)))
      .finally(() => setLoading(false));
  };

  return (
    <div className="space-y-6">
      <div>
        <div className="text-primary-strong text-xs font-semibold tracking-widest mb-2">✦ CITIZEN</div>
        <h1 className="font-display text-3xl font-semibold">{t("cit_title")}</h1>
        <p className="text-sm text-muted-foreground mt-2">{t("cit_sub")}</p>
      </div>

      <section className={card}>
        <form onSubmit={submit} className="grid sm:grid-cols-2 gap-4">
          {(Object.keys(CHOICES) as (keyof typeof CHOICES)[]).map((k) => (
            <label key={k} className="text-sm text-muted-foreground">
              {LABELS[k]}
              <select
                className="mt-1 w-full border border-border rounded-xl px-3 py-2.5 bg-card text-foreground"
                value={String(form[k])}
                onChange={(e) => setForm({ ...form, [k]: e.target.value })}
              >
                {CHOICES[k].map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </select>
            </label>
          ))}
          <label className="text-sm text-muted-foreground">
            {t("f_household")}
            <input
              type="number"
              min={1}
              max={10}
              className="mt-1 w-full border border-border rounded-xl px-3 py-2.5 bg-card text-foreground"
              value={Number(form.household_size)}
              onChange={(e) => setForm({ ...form, household_size: Number(e.target.value) })}
            />
          </label>
          <div className="sm:col-span-2">
            <button
              className="bg-primary hover:bg-primary-strong text-white px-6 py-2.5 rounded-xl text-sm font-medium"
              disabled={loading}
            >
              {loading ? t("running") : t("cit_submit")}
            </button>
          </div>
        </form>
      </section>

      {error && <div className="bg-red-50 border border-red-200 text-red-700 rounded-2xl p-5 text-sm">{error}</div>}

      {result && (
        <section className={card + " space-y-4"}>
          <h3 className="font-semibold">
            {t("cit_your_group")}: {result.segment}
          </h3>
          <div className="grid sm:grid-cols-2 gap-4 text-sm">
            <div className="bg-muted rounded-xl p-4">
              <div className="text-muted-foreground">{t("cit_no_response")}</div>
              <div className="text-2xl font-semibold text-red-600">
                {pct(result.concern_baseline_range[0])}–{pct(result.concern_baseline_range[1])}
              </div>
              <div className="text-muted-foreground">{t("cit_worry")}</div>
            </div>
            <div className="bg-primary-soft rounded-xl p-4">
              <div className="text-muted-foreground">{t("cit_with_response")}</div>
              <div className="text-2xl font-semibold text-primary-strong">
                {pct(result.concern_after_response_range[0])}–{pct(result.concern_after_response_range[1])}
              </div>
              <div className="text-muted-foreground">{t("cit_worry_after")}</div>
            </div>
          </div>
          <p className="text-xs text-muted-foreground">{result.note}</p>
          <p className="text-xs bg-amber-50 border border-amber-200 rounded-xl p-3 text-amber-900">
            ⚠️ {result.disclaimer}
          </p>
          <div className="pt-3 border-t border-border">
            <div className="text-sm text-muted-foreground mb-2">{t("cit_feedback")}</div>
            <div className="flex flex-wrap gap-2">
              {STANCES.map((s) => (
                <button
                  key={s}
                  className="border border-border rounded-full px-4 py-1.5 text-sm hover:bg-muted"
                  onClick={() =>
                    sendFeedback(result.segment, s)
                      .then(setNote)
                      .catch((er) => setError(String(er.message ?? er)))
                  }
                >
                  {s}
                </button>
              ))}
            </div>
            {note && <p className="text-xs text-primary-strong mt-2">✓ {note}</p>}
          </div>
        </section>
      )}
    </div>
  );
}
