import { useLang } from "../i18n";

export default function Landing({ onStart }: { onStart: () => void }) {
  const { t } = useLang();
  const feats = [
    { t: t("feat1_t"), d: t("feat1_d"), icon: "🎯" },
    { t: t("feat2_t"), d: t("feat2_d"), icon: "🇹🇭" },
    { t: t("feat3_t"), d: t("feat3_d"), icon: "🛡️" },
  ];
  return (
    <div className="space-y-10">
      <div className="pt-6">
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">
          <span className="text-primary">✦</span> {t("landing_eyebrow")}
        </div>
        <h1 className="font-display text-4xl font-semibold leading-tight mb-4">{t("landing_title")}</h1>
        <p className="text-muted-foreground max-w-xl leading-relaxed">{t("landing_sub")}</p>
        <button
          onClick={onStart}
          className="mt-6 bg-primary hover:bg-primary-strong text-white px-6 py-2.5 rounded-xl text-sm font-medium transition"
        >
          {t("landing_cta")} →
        </button>
      </div>
      <div className="grid sm:grid-cols-3 gap-4">
        {feats.map((f) => (
          <div key={f.t} className="bg-card border border-border rounded-2xl p-5">
            <div className="text-2xl mb-2">{f.icon}</div>
            <div className="font-medium mb-1">{f.t}</div>
            <div className="text-sm text-muted-foreground leading-relaxed">{f.d}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
