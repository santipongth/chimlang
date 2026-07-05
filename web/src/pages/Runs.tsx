import { useEffect, useState } from "react";
import { RunsData, fetchRuns } from "../api";
import { useLang } from "../i18n";

export default function Runs() {
  const { t } = useLang();
  const [data, setData] = useState<RunsData | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchRuns()
      .then(setData)
      .catch(() => setError(t("db_down")));
  }, []);

  const card = "bg-card border border-border rounded-2xl p-6";

  return (
    <div className="space-y-6">
      <div>
        <div className="text-primary-strong text-xs font-semibold tracking-widest mb-2">✦ {t("runs_eyebrow")}</div>
        <h1 className="font-display text-3xl font-semibold">{t("runs_title")}</h1>
        <p className="text-sm text-muted-foreground mt-2">{t("runs_note")}</p>
      </div>

      {error && <div className="bg-red-50 border border-red-200 text-red-700 rounded-2xl p-5 text-sm">{error}</div>}

      {data && (
        <>
          <section className={card}>
            {data.runs.length === 0 ? (
              <p className="text-muted-foreground text-sm">{t("runs_empty")}</p>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-muted-foreground border-b border-border">
                    <th className="py-2 font-medium">{t("runs_col_id")}</th>
                    <th className="py-2 font-medium">{t("runs_col_started")}</th>
                    <th className="py-2 font-medium">{t("runs_col_pred")}</th>
                    <th className="py-2 font-medium">{t("runs_col_export")}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.runs.map((r) => (
                    <tr key={r.run_id} className="border-b border-border/60">
                      <td className="py-2.5 pr-3 font-mono text-xs">{r.run_id}</td>
                      <td className="py-2.5 pr-3 text-muted-foreground">{r.started.slice(0, 16).replace("T", " ")}</td>
                      <td className="py-2.5 pr-3 tabular-nums">{r.predictions}</td>
                      <td className="py-2.5">{r.exported ? "✅" : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>

          <section className={card}>
            <h2 className="font-semibold mb-3">{t("runs_due_title")}</h2>
            {data.due.length === 0 ? (
              <p className="text-muted-foreground text-sm">{t("runs_due_empty")}</p>
            ) : (
              <ul className="space-y-2 text-sm">
                {data.due.map((d) => (
                  <li key={d.prediction_id} className="border border-border rounded-xl px-4 py-2.5">
                    <span className="text-xs bg-muted rounded-full px-2 py-0.5 mr-2">#{d.prediction_id}</span>
                    <span className="text-xs text-muted-foreground mr-2">{d.domain} · due {d.due_date}</span>
                    {d.claim}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </div>
  );
}
