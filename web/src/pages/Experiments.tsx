import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import {
  ExperimentDetail,
  createExperimentComparison,
  createExperimentSweep,
  fetchExperiment,
  fetchExperiments,
} from "../api";
import { PageHeader } from "../ui";

function parseList(value: string): string[] {
  return value.split(/[\n,]/).map((item) => item.trim()).filter(Boolean);
}

function Analysis({ detail }: { detail: ExperimentDetail }) {
  const analysis = detail.analysis;
  return (
    <section className="space-y-4 rounded-2xl border border-border bg-card p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-xs uppercase tracking-wider text-muted-foreground">Experiment analysis</div>
          <h2 className="mt-1 text-xl font-semibold">{detail.workspace.name}</h2>
          <p className="mt-1 text-xs text-muted-foreground">{analysis.note}</p>
        </div>
        <div className="text-right text-xs text-muted-foreground">
          <div>{analysis.completed}/{analysis.runs.length} complete</div>
          <div>${analysis.total_cost_usd.toFixed(4)} total</div>
        </div>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        {analysis.ranked_sensitivity.slice(0, 3).map((item) => (
          <div key={item.parameter} className="rounded-xl bg-muted/50 p-3">
            <div className="text-[10px] uppercase text-muted-foreground">{item.parameter}</div>
            <div className="mt-1 text-2xl font-semibold tabular-nums">{item.sensitivity_range.toFixed(3)}</div>
            <div className="text-[10px] text-muted-foreground">range of group means</div>
          </div>
        ))}
        {analysis.ranked_sensitivity.length === 0 && (
          <div className="rounded-xl bg-muted/50 p-3 text-xs text-muted-foreground sm:col-span-3">
            ต้องมี completed variants อย่างน้อยสองค่าต่อ parameter จึงคำนวณ sensitivity ได้
          </div>
        )}
      </div>
      <div className="overflow-x-auto rounded-xl border border-border">
        <table className="w-full text-left text-xs">
          <thead className="bg-muted/50 text-muted-foreground">
            <tr><th className="px-3 py-2">Run</th><th className="px-3 py-2">Variant</th><th className="px-3 py-2">Status</th><th className="px-3 py-2">Value</th><th className="px-3 py-2">Cost</th></tr>
          </thead>
          <tbody>
            {analysis.runs.map((run) => (
              <tr key={run.run_id} className="border-t border-border">
                <td className="px-3 py-2"><a href={`#/runs/${encodeURIComponent(run.run_id)}`} className="font-mono text-primary-strong hover:underline">{run.run_id}</a></td>
                <td className="px-3 py-2 font-mono">{JSON.stringify(run.variant)}</td>
                <td className="px-3 py-2">{run.status}</td>
                <td className="px-3 py-2 tabular-nums">{run.value == null ? "—" : run.value.toFixed(4)}</td>
                <td className="px-3 py-2 tabular-nums">${run.cost_usd.toFixed(4)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="rounded-xl border border-primary/20 bg-primary/5 px-3 py-2 text-xs text-primary-strong">
        Public votes used by engine: <b>NO</b>
      </div>
    </section>
  );
}

export default function Experiments({
  initialExperimentId = "",
  onSelect,
}: {
  initialExperimentId?: string;
  onSelect?: (experimentId: string) => void;
}) {
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState(initialExperimentId);
  const [mode, setMode] = useState<"comparison" | "sweep">("comparison");
  const [name, setName] = useState("วิเคราะห์ความไวของผลจำลอง");
  const [runIds, setRunIds] = useState("");
  const [subject, setSubject] = useState("");
  const [engine, setEngine] = useState<"fabric" | "debate">("fabric");
  const [seeds, setSeeds] = useState("41,42,43");
  const [agents, setAgents] = useState("100");
  const listQuery = useQuery({ queryKey: ["experiments"], queryFn: fetchExperiments });
  const detailQuery = useQuery({
    queryKey: ["experiment", selected],
    queryFn: () => fetchExperiment(selected),
    enabled: !!selected,
    refetchInterval: (query) =>
      query.state.data?.analysis.runs.some((run) => ["queued", "running"].includes(run.status))
        ? 5_000
        : false,
  });
  const comparison = useMutation({
    mutationFn: () => createExperimentComparison(name, parseList(runIds)),
    onSuccess: (detail) => {
      setSelected(detail.workspace.experiment_id);
      onSelect?.(detail.workspace.experiment_id);
      queryClient.invalidateQueries({ queryKey: ["experiments"] });
      queryClient.setQueryData(["experiment", detail.workspace.experiment_id], detail);
    },
  });
  const sweep = useMutation({
    mutationFn: () => {
      const seedValues = parseList(seeds).map(Number).filter(Number.isFinite);
      const agentValues = parseList(agents).map(Number).filter(Number.isFinite);
      return createExperimentSweep(
        name,
        { engine, subject, domain: "ทั่วไป", agents: agentValues[0] || 100, rounds: 3 },
        { seed: seedValues, ...(agentValues.length > 1 ? { agents: agentValues } : {}) },
      );
    },
    onSuccess: (created) => {
      setSelected(created.experiment_id);
      onSelect?.(created.experiment_id);
      queryClient.invalidateQueries({ queryKey: ["experiments"] });
      queryClient.invalidateQueries({ queryKey: ["experiment", created.experiment_id] });
    },
  });
  const activeError = comparison.error || sweep.error;
  const canSubmit = useMemo(
    () =>
      name.trim().length >= 2 &&
      (mode === "comparison"
        ? parseList(runIds).length >= 2
        : subject.trim().length >= 4 && parseList(seeds).length > 0),
    [mode, name, runIds, subject, seeds],
  );

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="EXPERIMENT WORKSPACE"
        title="เปรียบเทียบ run และวิเคราะห์ sensitivity"
        desc="Parameter sweep ใช้ BudgetGuard รวมก่อน enqueue และไม่ใช้ public votes เป็น input"
      />
      <div className="grid gap-5 lg:grid-cols-[360px_1fr]">
        <div className="space-y-4">
          <section className="space-y-3 rounded-2xl border border-border bg-card p-5">
            <div className="grid grid-cols-2 gap-2">
              {(["comparison", "sweep"] as const).map((item) => (
                <button key={item} onClick={() => setMode(item)} className={`rounded-lg border px-3 py-2 text-xs ${mode === item ? "border-primary bg-primary/5 text-primary-strong" : "border-border"}`}>{item}</button>
              ))}
            </div>
            <input value={name} onChange={(event) => setName(event.target.value)} className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" placeholder="ชื่อ experiment" />
            {mode === "comparison" ? (
              <textarea value={runIds} onChange={(event) => setRunIds(event.target.value)} className="min-h-28 w-full rounded-lg border border-border bg-background px-3 py-2 font-mono text-xs" placeholder="run-id-1, run-id-2" />
            ) : (
              <div className="space-y-2">
                <select value={engine} onChange={(event) => setEngine(event.target.value as "fabric" | "debate")} className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"><option value="fabric">Fabric ($0)</option><option value="debate">Debate (LLM budgeted)</option></select>
                <textarea value={subject} onChange={(event) => setSubject(event.target.value)} className="min-h-20 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" placeholder="หัวข้อจำลอง" />
                <input value={seeds} onChange={(event) => setSeeds(event.target.value)} className="w-full rounded-lg border border-border bg-background px-3 py-2 font-mono text-xs" placeholder="seeds: 41,42,43" />
                <input value={agents} onChange={(event) => setAgents(event.target.value)} className="w-full rounded-lg border border-border bg-background px-3 py-2 font-mono text-xs" placeholder="agents: 100 หรือ 100,500" />
                <p className="text-[11px] text-muted-foreground">สูงสุด 12 variants · Fabric รองรับ seed/agents</p>
              </div>
            )}
            <button disabled={!canSubmit || comparison.isPending || sweep.isPending} onClick={() => mode === "comparison" ? comparison.mutate() : sweep.mutate()} className="w-full rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white disabled:opacity-40">{comparison.isPending || sweep.isPending ? "กำลังสร้าง…" : "สร้าง workspace"}</button>
            {activeError && <p className="text-xs text-red-700">{String((activeError as Error).message)}</p>}
          </section>
          <section className="rounded-2xl border border-border bg-card p-3">
            <div className="px-2 py-1 text-xs font-semibold uppercase text-muted-foreground">Workspaces</div>
            <div className="mt-1 max-h-80 space-y-1 overflow-y-auto">
              {(listQuery.data ?? []).map((item) => (
                <button key={item.experiment_id} onClick={() => { setSelected(item.experiment_id); onSelect?.(item.experiment_id); }} className={`w-full rounded-lg px-3 py-2 text-left text-xs ${selected === item.experiment_id ? "bg-primary/10 text-primary-strong" : "hover:bg-muted"}`}><div className="font-medium">{item.name}</div><div className="mt-0.5 text-[10px] text-muted-foreground">{item.kind} · {item.run_count} runs</div></button>
              ))}
              {listQuery.data?.length === 0 && <p className="px-2 py-3 text-xs text-muted-foreground">ยังไม่มี experiment</p>}
            </div>
          </section>
        </div>
        <div>
          {detailQuery.data ? <Analysis detail={detailQuery.data} /> : <div className="rounded-2xl border border-dashed border-border p-12 text-center text-sm text-muted-foreground">เลือกหรือสร้าง workspace เพื่อดู comparison และ sensitivity</div>}
        </div>
      </div>
    </div>
  );
}
