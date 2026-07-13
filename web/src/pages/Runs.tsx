import { useEffect, useState } from "react";
import { RunsData, SimRunSummary, deleteRun, fetchRuns, fetchSimRuns } from "../api";
import { useLang } from "../i18n";
import { ConfirmDialog, PageHeader } from "../ui";

// History (P6-M2) — รายการ run ถาวร (ค้นหา/กรอง engine) + คิว prediction รอ resolve (เดิม)

export default function Runs({ onOpen }: { onOpen: (runId: string) => void }) {
  const { t } = useLang();
  const [runs, setRuns] = useState<SimRunSummary[]>([]);
  const [legacy, setLegacy] = useState<RunsData | null>(null);
  const [search, setSearch] = useState("");
  const [engine, setEngine] = useState("");
  const [error, setError] = useState("");
  const [runToDelete, setRunToDelete] = useState<string | null>(null);

  const load = () =>
    fetchSimRuns(search, engine)
      .then((r) => {
        setRuns(r);
        setError("");
      })
      .catch((e) => setError(String(e.message ?? e)));

  useEffect(() => {
    load();
  }, [search, engine]);
  useEffect(() => {
    fetchRuns().then(setLegacy).catch(() => {});
  }, []);

  const card = "bg-card border border-border rounded-2xl p-6";

  // ลบ run — ยืนยันด้วย ConfirmDialog ของเราเอง (ห้าม popup ระบบ — มติผู้ใช้ 13 ก.ค.)
  async function removeConfirmed() {
    const runId = runToDelete;
    setRunToDelete(null);
    if (!runId) return;
    try {
      await deleteRun(runId);
      await load();
    } catch (e: any) {
      setError(String(e.message ?? e));
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader eyebrow={t("hist_eyebrow")} title={t("hist_title")} desc={t("hist_sub")} />
      {error && <div className="bg-red-50 border border-red-200 text-red-700 rounded-2xl p-5 text-sm">{error}</div>}

      <div className="flex flex-wrap items-center gap-2">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={t("hist_search_ph")}
          className="w-64 rounded-xl border border-border bg-card px-4 py-2 text-sm"
        />
        <div className="inline-flex rounded-lg border border-border bg-card p-1 text-xs">
          {([["", t("ins_all")], ["fabric", "⚙ Fabric"], ["debate", "🗣 Debate"]] as const).map(([k, label]) => (
            <button
              key={k}
              onClick={() => setEngine(k)}
              className={`rounded-md px-3 py-1 ${engine === k ? "bg-primary text-white" : "text-muted-foreground hover:text-foreground"}`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {runs.length === 0 ? (
        <p className="py-10 text-center text-sm text-muted-foreground">{t("hist_empty")}</p>
      ) : (
        <div className="space-y-2">
          {runs.map((r) => (
            <div key={r.run_id} className={card + " !p-4 flex items-center justify-between gap-3 hover:bg-muted/40 transition"}>
              <button onClick={() => onOpen(r.run_id)} className="min-w-0 flex-1 text-left">
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <span>{r.engine === "debate" ? "🗣 Debate" : "⚙ Fabric"}</span>
                  <span>·</span>
                  <span>{r.created_at.slice(0, 16).replace("T", " ")}</span>
                  <span>·</span>
                  <span>{r.agents} agents</span>
                  {r.status !== "complete" && (
                    <span className={`rounded-full px-2 py-0.5 text-[10px] ${r.status === "error" ? "bg-red-50 text-red-700" : "bg-amber-50 text-amber-700"}`}>
                      {r.status}
                    </span>
                  )}
                </div>
                <div className="mt-0.5 truncate font-medium">{r.subject}</div>
              </button>
              <button onClick={() => setRunToDelete(r.run_id)} className="shrink-0 text-xs text-muted-foreground hover:text-red-600" title={t("hist_delete")}>
                🗑
              </button>
            </div>
          ))}
        </div>
      )}

      {/* คิว prediction ครบกำหนด (เดิม) — ชี้ไปหน้า Calibration */}
      {legacy && legacy.due.length > 0 && (
        <section className={card}>
          <h2 className="font-semibold mb-3">{t("runs_due_title")}</h2>
          <ul className="space-y-2 text-sm">
            {legacy.due.map((d) => (
              <li key={d.prediction_id} className="border border-border rounded-xl px-4 py-2.5">
                <span className="text-xs bg-muted rounded-full px-2 py-0.5 mr-2">#{d.prediction_id}</span>
                <span className="text-xs text-muted-foreground mr-2">{d.domain} · due {d.due_date}</span>
                {d.claim}
              </li>
            ))}
          </ul>
          <p className="mt-3 text-xs text-muted-foreground">→ {t("hist_due_note")}</p>
        </section>
      )}

      <ConfirmDialog
        open={runToDelete != null}
        title={t("hist_delete_title")}
        message={t("hist_delete_confirm")}
        confirmLabel={t("hist_delete_ok")}
        cancelLabel={t("confirm_cancel")}
        danger
        onCancel={() => setRunToDelete(null)}
        onConfirm={removeConfirmed}
      />
    </div>
  );
}
