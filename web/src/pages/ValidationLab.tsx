import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import {
  assignResolutionOwner,
  fetchResolutionInbox,
  fetchValidationOverview,
} from "../api";
import { useLang } from "../i18n";
import { PageHeader } from "../ui";
import Experiments from "./Experiments";

type Tab = "overview" | "experiments" | "forecast";

export default function ValidationLab({
  onOpenCalibration,
}: {
  onOpenCalibration?: () => void;
}) {
  const { lang } = useLang();
  const th = lang === "th";
  const client = useQueryClient();
  const [tab, setTab] = useState<Tab>("overview");
  const [owners, setOwners] = useState<Record<number, string>>({});
  const overview = useQuery({
    queryKey: ["validation-overview"],
    queryFn: fetchValidationOverview,
  });
  const inbox = useQuery({
    queryKey: ["resolution-inbox"],
    queryFn: fetchResolutionInbox,
  });
  const number = useMemo(
    () => new Intl.NumberFormat(th ? "th-TH" : "en-US", { maximumFractionDigits: 4 }),
    [th],
  );
  const assign = useMutation({
    mutationFn: ({ id, owner }: { id: number; owner: string }) =>
      assignResolutionOwner(id, owner),
    onSuccess: () => client.invalidateQueries({ queryKey: ["resolution-inbox"] }),
  });
  const claims = overview.data?.trust_claims;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="VALIDATION LAB"
        title={th ? "ทดสอบความทนทานและวัดผลกับโลกจริง" : "Robustness and real-world evaluation"}
        desc={
          th
            ? "รวม comparison, sensitivity, calibration, datasets และ raw failures โดยไม่อ้างผลก่อนมีหลักฐานจริง"
            : "Comparison, sensitivity, calibration, datasets and raw failures without premature claims."
        }
      />
      <div className="flex flex-wrap gap-2" role="tablist">
        {(["overview", "experiments", "forecast"] as const).map((item) => (
          <button
            key={item}
            role="tab"
            aria-selected={tab === item}
            onClick={() => setTab(item)}
            className={[
              "rounded-lg border px-4 py-2 text-sm",
              tab === item ? "border-primary bg-primary/5 text-primary-strong" : "border-border",
            ].join(" ")}
          >
            {item === "overview"
              ? th
                ? "หลักฐานความน่าเชื่อถือ"
                : "Trust evidence"
              : item === "experiments"
                ? th
                  ? "เปรียบเทียบและ sensitivity"
                  : "Compare & sensitivity"
                : th
                  ? "Resolution Inbox"
                  : "Resolution Inbox"}
          </button>
        ))}
      </div>
      {tab === "overview" && (
        <div className="grid gap-5 lg:grid-cols-[1fr_1.2fr]">
          <section className="rounded-2xl border border-border bg-card p-5">
            <h2 className="font-semibold">{th ? "สถานะคำกล่าวอ้าง" : "Claim readiness"}</h2>
            <div className="mt-4 space-y-3">
              {[
                ["MIRACL Thai", claims?.miracl_measured],
                [th ? "Thai human panel" : "Thai human panel", claims?.human_panel_measured],
                [th ? "Usability pilot" : "Usability pilot", claims?.pilot_usability_measured],
              ].map(([label, measured]) => (
                <div key={String(label)} className="flex items-center justify-between rounded-xl border border-border p-3 text-sm">
                  <span>{String(label)}</span>
                  <span className={measured ? "text-primary-strong" : "text-amber-700"}>
                    {measured ? (th ? "มีผลจริง" : "Measured") : th ? "ยังห้ามอ้าง" : "Claim blocked"}
                  </span>
                </div>
              ))}
            </div>
          </section>
          <section className="rounded-2xl border border-border bg-card p-5">
            <div className="flex items-center justify-between">
              <h2 className="font-semibold">{th ? "ชุดข้อมูลและรายงาน" : "Datasets and reports"}</h2>
              <span className="text-xs text-muted-foreground">
                {overview.data?.datasets.length ?? 0} datasets
              </span>
            </div>
            <div className="mt-4 space-y-3">
              {(overview.data?.datasets ?? []).map((dataset) => (
                <article key={dataset.dataset_id} className="rounded-xl border border-border p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
                    <span className="font-medium">{dataset.name}</span>
                    <span className="rounded-full bg-muted px-2 py-0.5 text-xs">{dataset.kind}</span>
                  </div>
                  <div className="mt-1 break-all font-mono text-[10px] text-muted-foreground">
                    {dataset.revision} · {dataset.license} · {dataset.content_hash.slice(0, 16)}
                  </div>
                </article>
              ))}
              {overview.data?.datasets.length === 0 && (
                <p className="rounded-xl border border-dashed border-border p-5 text-sm text-muted-foreground">
                  {th ? "ยังไม่มี dataset ที่ import และตรวจ hash แล้ว" : "No imported, hashed dataset yet."}
                </p>
              )}
              {(overview.data?.reports ?? []).map((report) => (
                <article key={report.report_id} className="rounded-xl bg-muted/40 p-3 text-xs">
                  <div className="flex items-center justify-between gap-2">
                    <div className="font-medium">{report.kind}</div>
                    <span
                      className={
                        report.trust_status === "measured"
                          ? "text-primary-strong"
                          : report.trust_status === "invalidated"
                            ? "text-red-700"
                            : "text-amber-700"
                      }
                    >
                      {report.trust_status}
                    </span>
                  </div>
                  {String(
                    Object.entries(report.metadata).find(([key]) => key === "reason")?.[1] ?? "",
                  ) !== "" && (
                    <p className="mt-1 text-[10px] text-red-700">
                      {String(
                        Object.entries(report.metadata).find(([key]) => key === "reason")?.[1] ?? "",
                      )}
                    </p>
                  )}
                  <pre className="mt-1 overflow-x-auto whitespace-pre-wrap font-mono text-[10px]">
                    {JSON.stringify(report.metrics, null, 2)}
                  </pre>
                </article>
              ))}
            </div>
          </section>
        </div>
      )}
      {tab === "experiments" && <Experiments />}
      {tab === "forecast" && (
        <div className="space-y-5">
          <section className="grid gap-3 sm:grid-cols-3">
            <div className="rounded-2xl border border-border bg-card p-5">
              <div className="text-xs uppercase text-muted-foreground">Brier</div>
              <div className="mt-1 text-3xl font-semibold">
                {inbox.data?.metrics.mean_brier == null
                  ? "—"
                  : number.format(Number(inbox.data.metrics.mean_brier))}
              </div>
            </div>
            <div className="rounded-2xl border border-border bg-card p-5">
              <div className="text-xs uppercase text-muted-foreground">ECE</div>
              <div className="mt-1 text-3xl font-semibold">
                {inbox.data?.metrics.ece == null ? "—" : number.format(Number(inbox.data.metrics.ece))}
              </div>
            </div>
            <button
              onClick={onOpenCalibration}
              className="rounded-2xl border border-primary bg-primary/5 p-5 text-left text-sm text-primary-strong"
            >
              {th ? "เปิด Reliability Diagram →" : "Open reliability diagram →"}
            </button>
          </section>
          <section className="rounded-2xl border border-border bg-card p-5">
            <h2 className="font-semibold">
              {th ? "ครบกำหนดและต้องมีหลักฐานก่อน resolve" : "Due forecasts requiring evidence"}
            </h2>
            <div className="mt-4 space-y-3">
              {(inbox.data?.due ?? []).map((item) => {
                const id = Number(item.prediction_id);
                return (
                  <article key={id} className="rounded-xl border border-border p-4">
                    <p className="text-sm">{String(item.claim)}</p>
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      <span className="text-xs text-muted-foreground">{String(item.due_date)}</span>
                      <input
                        value={owners[id] ?? String(item.owner ?? "")}
                        onChange={(event) =>
                          setOwners((current) => ({ ...current, [id]: event.target.value }))
                        }
                        placeholder={th ? "เจ้าของ resolution" : "Resolution owner"}
                        className="ml-auto rounded-lg border border-border bg-background px-3 py-2 text-xs"
                      />
                      <button
                        disabled={!owners[id]?.trim() || assign.isPending}
                        onClick={() => assign.mutate({ id, owner: owners[id] })}
                        className="rounded-lg bg-primary px-3 py-2 text-xs text-white disabled:opacity-40"
                      >
                        {th ? "มอบหมาย" : "Assign"}
                      </button>
                    </div>
                  </article>
                );
              })}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
