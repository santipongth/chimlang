import { useState } from "react";
import { useLang } from "../i18n";
import type { RunRequest } from "../App";

const EXAMPLES = [
  "มาตรการค่าธรรมเนียมรถติด กทม.",
  "แคมเปญขึ้นราคาสินค้า 15% พร้อมข้อความสื่อสารใหม่",
  "นโยบายจำกัดเวลาขายแอลกอฮอล์รอบใหม่",
];
const DOMAINS = ["นโยบายสาธารณะ", "ธุรกิจ/การตลาด", "กระแสสังคม", "ทั่วไป"];

function Steps({ step, labels }: { step: number; labels: string[] }) {
  return (
    <div className="flex items-center gap-2 flex-wrap text-sm">
      {labels.map((l, i) => (
        <div key={l} className="flex items-center gap-2">
          <span
            className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold ${
              i === step ? "bg-primary text-white" : i < step ? "bg-primary-soft text-primary-strong" : "bg-muted text-muted-foreground"
            }`}
          >
            {i + 1}
          </span>
          <span className={i === step ? "font-medium" : "text-muted-foreground"}>{l}</span>
          {i < labels.length - 1 && <span className="text-muted-foreground">›</span>}
        </div>
      ))}
    </div>
  );
}

export default function NewRun({ onRun }: { onRun: (r: RunRequest) => void }) {
  const { t } = useLang();
  const [step, setStep] = useState(0);
  const [subject, setSubject] = useState("");
  const [domain, setDomain] = useState(DOMAINS[0]);
  const [agents, setAgents] = useState(100);

  const labels = [t("wiz_step1"), t("wiz_step2"), t("wiz_step3")];
  const card = "bg-card border border-border rounded-2xl p-6";
  const chip = (active: boolean) =>
    `border rounded-xl px-4 py-2.5 text-sm text-left transition ${
      active ? "border-primary bg-primary-soft text-primary-strong font-medium" : "border-border bg-card hover:bg-muted"
    }`;

  return (
    <div className="space-y-6">
      <div>
        <div className="text-primary-strong text-xs font-semibold tracking-widest mb-2">✦ {t("wiz_eyebrow")}</div>
        <h1 className="font-display text-3xl font-semibold mb-4">{t("wiz_title")}</h1>
        <Steps step={step} labels={labels} />
      </div>

      {step === 0 && (
        <div className={card + " space-y-5"}>
          <div>
            <div className="text-xs font-semibold text-muted-foreground tracking-wider mb-2">{t("wiz_q_label")}</div>
            <textarea
              className="w-full border border-border rounded-xl px-4 py-3 text-sm bg-card min-h-24"
              placeholder={t("wiz_q_ph")}
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
            />
            <div className="flex flex-wrap gap-2 mt-2">
              {EXAMPLES.map((ex) => (
                <button
                  key={ex}
                  onClick={() => setSubject(ex)}
                  className="border border-border rounded-full px-3 py-1.5 text-xs text-muted-foreground hover:bg-muted"
                >
                  {ex}
                </button>
              ))}
            </div>
          </div>
          <div>
            <div className="text-xs font-semibold text-muted-foreground tracking-wider mb-2">{t("wiz_domain")}</div>
            <div className="grid sm:grid-cols-2 gap-2">
              {DOMAINS.map((d) => (
                <button key={d} className={chip(domain === d)} onClick={() => setDomain(d)}>
                  {d}
                </button>
              ))}
            </div>
            <p className="text-xs text-muted-foreground mt-3">🗳️ {t("wiz_election_warn")}</p>
          </div>
        </div>
      )}

      {step === 1 && (
        <div className={card + " space-y-4"}>
          <div className="text-xs font-semibold text-muted-foreground tracking-wider">{t("wiz_agents")}</div>
          <div className="grid sm:grid-cols-3 gap-2">
            {[100, 500, 1000].map((n) => (
              <button key={n} className={chip(agents === n)} onClick={() => setAgents(n)}>
                {n.toLocaleString()} agents
              </button>
            ))}
          </div>
          <p className="text-xs text-muted-foreground">{t("wiz_agents_note")}</p>
          <p className="text-xs text-muted-foreground">🌌 {t("wiz_universes")}</p>
        </div>
      )}

      {step === 2 && (
        <div className={card + " space-y-3 text-sm"}>
          <div className="text-xs font-semibold text-muted-foreground tracking-wider">{t("wiz_review")}</div>
          <div className="grid grid-cols-[120px_1fr] gap-y-2">
            <span className="text-muted-foreground">{t("wiz_step1")}</span>
            <span className="font-medium">{subject || "—"}</span>
            <span className="text-muted-foreground">{t("wiz_domain")}</span>
            <span>{domain}</span>
            <span className="text-muted-foreground">{t("wiz_agents")}</span>
            <span>{agents.toLocaleString()} × 5 universes</span>
          </div>
        </div>
      )}

      <div className="flex justify-between">
        <button
          className="px-5 py-2.5 rounded-xl text-sm border border-border text-muted-foreground disabled:opacity-40"
          disabled={step === 0}
          onClick={() => setStep(step - 1)}
        >
          {t("back")}
        </button>
        {step < 2 ? (
          <button
            className="bg-primary hover:bg-primary-strong text-white px-6 py-2.5 rounded-xl text-sm font-medium disabled:opacity-40"
            disabled={step === 0 && !subject.trim()}
            onClick={() => setStep(step + 1)}
          >
            {t("next")}
          </button>
        ) : (
          <button
            className="bg-primary hover:bg-primary-strong text-white px-6 py-2.5 rounded-xl text-sm font-medium"
            onClick={() => onRun({ subject: subject.trim(), agents })}
          >
            {t("run_now")}
          </button>
        )}
      </div>
    </div>
  );
}
