import { useState } from "react";
import { useLang } from "../i18n";
import { PageHeader, SelectCard } from "../ui";
import type { RunRequest } from "../App";

// Template gallery แบบ studio: คลิกเดียวเซ็ตทั้งคำถาม + โดเมน
const TEMPLATES = [
  { label: "ค่าธรรมเนียมรถติด", q: "มาตรการค่าธรรมเนียมรถติด กทม.", domain: "นโยบายสาธารณะ" },
  { label: "ขึ้นราคา 15%", q: "แคมเปญขึ้นราคาสินค้า 15% พร้อมข้อความสื่อสารใหม่", domain: "ธุรกิจ/การตลาด" },
  { label: "เวลาขายแอลกอฮอล์", q: "นโยบายจำกัดเวลาขายแอลกอฮอล์รอบใหม่", domain: "นโยบายสาธารณะ" },
  { label: "ซ้อมแถลงดราม่า", q: "แบรนด์ถูกกล่าวหาเรื่องคุณภาพสินค้า — ควรแถลงด้วยข้อความแบบไหน", domain: "กระแสสังคม" },
  { label: "เปลี่ยนโมเดลราคา", q: "เปิดตัวบริการสมัครสมาชิกรายเดือนแทนการซื้อขาด", domain: "ธุรกิจ/การตลาด" },
  { label: "ข่าวลือน้ำประปา", q: "ข่าวลือเรื่องคุณภาพน้ำประปาในเขตเมืองกำลังแพร่ในกลุ่มปิด", domain: "กระแสสังคม" },
];
const DOMAINS = ["นโยบายสาธารณะ", "ธุรกิจ/การตลาด", "กระแสสังคม", "ทั่วไป"];

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

export default function NewRun({ onRun }: { onRun: (r: RunRequest) => void }) {
  const { t } = useLang();
  const [step, setStep] = useState(0);
  const [subject, setSubject] = useState("");
  const [domain, setDomain] = useState(DOMAINS[0]);
  const [agents, setAgents] = useState(100);

  const labels = [t("wiz_step1"), t("wiz_step2"), t("wiz_step3")];
  const card = "bg-card border border-border rounded-2xl p-6";

  return (
    <div className="space-y-6">
      <PageHeader eyebrow={t("wiz_eyebrow")} title={t("wiz_title")} />
      <Steps step={step} labels={labels} onJump={setStep} />

      {step === 0 && (
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
              {TEMPLATES.map((tpl) => (
                <SelectCard
                  key={tpl.label}
                  active={subject === tpl.q}
                  onClick={() => {
                    setSubject(tpl.q);
                    setDomain(tpl.domain);
                  }}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-medium">{tpl.label}</span>
                    <span className="rounded-full border border-border bg-background px-2 py-0.5 text-[10px] text-muted-foreground">
                      {tpl.domain}
                    </span>
                  </div>
                  <div className="mt-1 line-clamp-2 text-xs text-muted-foreground">{tpl.q}</div>
                </SelectCard>
              ))}
            </div>
          </div>
          <div>
            <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">{t("wiz_domain")}</div>
            <div className="grid sm:grid-cols-2 gap-2">
              {DOMAINS.map((d) => (
                <SelectCard key={d} active={domain === d} onClick={() => setDomain(d)}>
                  <span className="text-sm">{d}</span>
                </SelectCard>
              ))}
            </div>
            <p className="text-xs text-muted-foreground mt-3">🗳️ {t("wiz_election_warn")}</p>
          </div>
        </div>
      )}

      {step === 1 && (
        <div className={card + " space-y-4"}>
          <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t("wiz_agents")}</div>
          <div className="grid sm:grid-cols-3 gap-2">
            {[100, 500, 1000].map((n) => (
              <SelectCard key={n} active={agents === n} onClick={() => setAgents(n)}>
                <span className="text-sm font-medium">{n.toLocaleString()} agents</span>
              </SelectCard>
            ))}
          </div>
          <p className="text-xs text-muted-foreground">{t("wiz_agents_note")}</p>
          <p className="text-xs text-muted-foreground">🌌 {t("wiz_universes")}</p>
        </div>
      )}

      {step === 2 && (
        <div className={card + " space-y-3 text-sm"}>
          <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{t("wiz_review")}</div>
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
