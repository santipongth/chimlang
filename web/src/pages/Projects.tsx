import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import {
  addTextEvidence,
  addUrlEvidence,
  createProject,
  createRunAsync,
  fetchEvidence,
  fetchProject,
  fetchProjects,
  freezeEvidence,
  previewEvidence,
  uploadEvidence,
  updateProject,
} from "../api";
import { useLang } from "../i18n";
import { PageHeader } from "../ui";

const STAGES = [
  "brief",
  "evidence",
  "population",
  "assumptions",
  "run",
  "compare",
  "decision",
  "resolution",
] as const;

export default function Projects({
  initialProjectId = "",
  onSelect,
  onOpenRun,
}: {
  initialProjectId?: string;
  onSelect?: (projectId: string) => void;
  onOpenRun?: (runId: string) => void;
}) {
  const { lang } = useLang();
  const th = lang === "th";
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState(initialProjectId);
  const [name, setName] = useState("");
  const [brief, setBrief] = useState("");
  const [evidenceLabel, setEvidenceLabel] = useState("");
  const [evidenceText, setEvidenceText] = useState("");
  const [evidenceUrl, setEvidenceUrl] = useState("");
  const [evidenceKind, setEvidenceKind] = useState<"text" | "url" | "rss" | "file">("text");
  const [evidenceFile, setEvidenceFile] = useState<File | null>(null);
  const [subject, setSubject] = useState("");
  const [populationAcknowledged, setPopulationAcknowledged] = useState(false);
  const [error, setError] = useState("");
  const dateFormat = useMemo(
    () => new Intl.DateTimeFormat(th ? "th-TH" : "en-US", { dateStyle: "medium" }),
    [th],
  );

  const list = useQuery({ queryKey: ["projects"], queryFn: fetchProjects });
  const detail = useQuery({
    queryKey: ["project", selected],
    queryFn: () => fetchProject(selected),
    enabled: !!selected,
  });
  const evidence = useQuery({
    queryKey: ["project-evidence", selected],
    queryFn: () => fetchEvidence(selected),
    enabled: !!selected,
  });
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["projects"] });
    queryClient.invalidateQueries({ queryKey: ["project", selected] });
    queryClient.invalidateQueries({ queryKey: ["project-evidence", selected] });
  };
  const create = useMutation({
    mutationFn: () => createProject(name, brief),
    onSuccess: (project) => {
      setSelected(project.project_id);
      onSelect?.(project.project_id);
      setName("");
      setBrief("");
      refresh();
    },
    onError: (reason) => setError(String(reason)),
  });
  const addEvidence = useMutation({
    mutationFn: () => {
      if (evidenceKind === "text") return addTextEvidence(selected, evidenceLabel, evidenceText);
      if (evidenceKind === "file" && evidenceFile) {
        return uploadEvidence(selected, evidenceLabel, evidenceFile);
      }
      if (evidenceKind === "url" || evidenceKind === "rss") {
        return addUrlEvidence(selected, evidenceLabel, evidenceUrl, evidenceKind);
      }
      throw new Error(th ? "กรุณาเลือกไฟล์" : "Choose a file");
    },
    onSuccess: () => {
      setEvidenceLabel("");
      setEvidenceText("");
      setEvidenceUrl("");
      setEvidenceFile(null);
      refresh();
    },
    onError: (reason) => setError(String(reason)),
  });
  const preview = useMutation({
    mutationFn: () => previewEvidence(selected, evidenceText),
    onError: (reason) => setError(String(reason)),
  });
  const freeze = useMutation({
    mutationFn: () =>
      freezeEvidence(
        selected,
        th ? "ชุดหลักฐานสำหรับรัน" : "Evidence set for run",
      ),
    onSuccess: refresh,
    onError: (reason) => setError(String(reason)),
  });

  const project = detail.data;
  const currentSet = project?.evidence_sets[0];
  const nextStage = project ? STAGES[project.stage_index + 1] : undefined;

  async function startRun() {
    if (!project || !currentSet || subject.trim().length < 4) return;
    try {
      const accepted = await createRunAsync(
        {
          engine: "debate",
          subject,
          domain: "ทั่วไป",
          agents: 10,
          rounds: 3,
          project_id: project.project_id,
          evidence_set_id: String(currentSet.set_id),
          population_acknowledged: populationAcknowledged,
        },
        crypto.randomUUID(),
      );
      onOpenRun?.(accepted.run_id);
    } catch (reason) {
      setError(String(reason));
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={th ? "พื้นที่ทำงาน" : "PROJECT WORKSPACE"}
        title={th ? "จากโจทย์สู่คำตัดสินที่ตรวจสอบได้" : "From brief to auditable decision"}
        desc={
          th
            ? "Brief → Evidence → Population → Assumptions → Run → Compare → Decision → Resolution"
            : "One case workspace keeps evidence, runs, comparisons and decisions connected."
        }
      />
      {error && (
        <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}
      <div className="grid gap-5 lg:grid-cols-[320px_1fr]">
        <aside className="space-y-4">
          <section className="space-y-3 rounded-2xl border border-border bg-card p-4">
            <h2 className="font-semibold">{th ? "สร้างโปรเจกต์" : "Create project"}</h2>
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder={th ? "ชื่อเคส" : "Case name"}
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
            />
            <textarea
              value={brief}
              onChange={(event) => setBrief(event.target.value)}
              placeholder={th ? "โจทย์และบริบท" : "Brief and context"}
              className="min-h-24 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
            />
            <button
              disabled={name.trim().length < 2 || create.isPending}
              onClick={() => create.mutate()}
              className="w-full rounded-lg bg-primary px-3 py-2 text-sm font-medium text-white disabled:opacity-40"
            >
              {th ? "สร้างพื้นที่ทำงาน" : "Create workspace"}
            </button>
          </section>
          <section className="rounded-2xl border border-border bg-card p-3">
            <h2 className="px-2 py-1 text-xs font-semibold uppercase text-muted-foreground">
              {th ? "โปรเจกต์" : "Projects"}
            </h2>
            <div className="mt-1 max-h-96 space-y-1 overflow-y-auto">
              {(list.data ?? []).map((item) => (
                <button
                  key={item.project_id}
                  onClick={() => {
                    setSelected(item.project_id);
                    onSelect?.(item.project_id);
                  }}
                  className={[
                    "w-full rounded-lg px-3 py-2 text-left text-xs",
                    selected === item.project_id ? "bg-primary/10 text-primary-strong" : "hover:bg-muted",
                  ].join(" ")}
                >
                  <div className="font-medium">{item.name}</div>
                  <div className="mt-1 text-[10px] text-muted-foreground">
                    {item.stage} · {dateFormat.format(new Date(item.updated_at))}
                  </div>
                </button>
              ))}
            </div>
          </section>
        </aside>
        {!project ? (
          <div className="rounded-2xl border border-dashed border-border p-12 text-center text-sm text-muted-foreground">
            {th ? "เลือกหรือสร้างโปรเจกต์" : "Select or create a project"}
          </div>
        ) : (
          <div className="space-y-5">
            <section className="rounded-2xl border border-border bg-card p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="text-xs uppercase text-muted-foreground">{project.stage}</div>
                  <h2 className="mt-1 text-xl font-semibold">{project.name}</h2>
                  <p className="mt-2 max-w-3xl text-sm text-muted-foreground">{project.brief}</p>
                </div>
                {nextStage && (
                  <button
                    onClick={async () => {
                      await updateProject(project.project_id, { stage: nextStage });
                      refresh();
                    }}
                    className="rounded-lg border border-primary px-3 py-2 text-xs text-primary-strong"
                  >
                    {th ? "ไปขั้นถัดไป" : "Advance"} → {nextStage}
                  </button>
                )}
              </div>
              <ol className="mt-5 grid gap-2 sm:grid-cols-4" aria-label={th ? "ลำดับงานโปรเจกต์" : "Project workflow"}>
                {project.workflow.map((item) => (
                  <li
                    key={String(item.stage)}
                    className={[
                      "rounded-lg border px-2 py-2 text-center text-[11px]",
                      item.status === "active"
                        ? "border-primary bg-primary/5 font-medium"
                        : "border-border text-muted-foreground",
                    ].join(" ")}
                  >
                    {String(item.stage)}
                  </li>
                ))}
              </ol>
            </section>
            <div className="grid gap-5 xl:grid-cols-2">
              <section className="space-y-3 rounded-2xl border border-border bg-card p-5">
                <div>
                  <div className="text-xs uppercase text-muted-foreground">Evidence Library</div>
                  <h2 className="mt-1 font-semibold">
                    {th ? "หลักฐานที่มีเวอร์ชันและ PII gate" : "Versioned evidence with PII gate"}
                  </h2>
                </div>
                <div className="grid grid-cols-4 gap-2">
                  {(["text", "file", "url", "rss"] as const).map((kind) => (
                    <button
                      key={kind}
                      onClick={() => setEvidenceKind(kind)}
                      className={[
                        "rounded-lg border px-2 py-2 text-xs",
                        evidenceKind === kind ? "border-primary bg-primary/5" : "border-border",
                      ].join(" ")}
                    >
                      {kind}
                    </button>
                  ))}
                </div>
                <input
                  value={evidenceLabel}
                  onChange={(event) => setEvidenceLabel(event.target.value)}
                  placeholder={th ? "ชื่อหลักฐาน" : "Evidence label"}
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
                />
                {evidenceKind === "text" ? (
                  <div className="space-y-2">
                    <textarea
                      value={evidenceText}
                      onChange={(event) => {
                        setEvidenceText(event.target.value);
                        preview.reset();
                      }}
                      placeholder={th ? "ข้อความตรงจะถูก block หากมี PII" : "Direct text is blocked when PII is found"}
                      className="min-h-28 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
                    />
                    <button
                      type="button"
                      disabled={!evidenceText.trim() || preview.isPending}
                      onClick={() => preview.mutate()}
                      className="w-full rounded-lg border border-border px-3 py-2 text-xs disabled:opacity-40"
                    >
                      {th ? "ตรวจ PII ก่อนบันทึก" : "Preview PII gate"}
                    </button>
                    {preview.data && (
                      <p
                        className={
                          preview.data.safe_to_store
                            ? "text-xs text-primary-strong"
                            : "text-xs text-red-700"
                        }
                        role="status"
                      >
                        {preview.data.safe_to_store
                          ? th
                            ? "ไม่พบ PII ที่ต้อง block"
                            : "No blocking PII detected"
                          : `${th ? "พบ PII — ยังบันทึกไม่ได้" : "PII found — storage blocked"}: ${JSON.stringify(preview.data.pii_counts)}`}
                      </p>
                    )}
                  </div>
                ) : evidenceKind === "file" ? (
                  <input
                    type="file"
                    accept=".pdf,.docx,.txt,.csv,text/plain,text/csv,application/pdf"
                    onChange={(event) => setEvidenceFile(event.target.files?.[0] ?? null)}
                    className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
                  />
                ) : (
                  <input
                    value={evidenceUrl}
                    onChange={(event) => setEvidenceUrl(event.target.value)}
                    placeholder="https://"
                    className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
                  />
                )}
                <button
                  disabled={
                    addEvidence.isPending ||
                    !evidenceLabel.trim() ||
                    (evidenceKind === "text" && preview.data?.safe_to_store === false) ||
                    (evidenceKind === "text"
                      ? !evidenceText.trim()
                      : evidenceKind === "file"
                        ? !evidenceFile
                        : !evidenceUrl.trim())
                  }
                  onClick={() => addEvidence.mutate()}
                  className="w-full rounded-lg bg-primary px-3 py-2 text-sm font-medium text-white disabled:opacity-40"
                >
                  {th ? "เพิ่มหลักฐาน" : "Add evidence"}
                </button>
                <div className="max-h-64 space-y-2 overflow-y-auto">
                  {(evidence.data ?? []).map((item) => (
                    <article key={item.version_id} className="rounded-xl border border-border p-3 text-xs">
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-medium">{item.label}</span>
                        <span className="rounded-full bg-muted px-2 py-0.5">{item.status}</span>
                      </div>
                      <div className="mt-1 font-mono text-[10px] text-muted-foreground">
                        v{item.version_no} · {item.content_hash.slice(0, 12)} · {item.byte_size} B
                      </div>
                      {Object.keys(item.pii_redactions).length > 0 && (
                        <p className="mt-1 text-amber-700">
                          {th ? "ลบ PII แล้ว" : "PII redacted"}: {JSON.stringify(item.pii_redactions)}
                        </p>
                      )}
                    </article>
                  ))}
                </div>
                <button
                  disabled={!evidence.data?.length || freeze.isPending}
                  onClick={() => freeze.mutate()}
                  className="w-full rounded-lg border border-primary px-3 py-2 text-sm text-primary-strong disabled:opacity-40"
                >
                  {th ? "Freeze เป็น EvidenceSetV1" : "Freeze EvidenceSetV1"}
                </button>
              </section>
              <section className="space-y-4 rounded-2xl border border-border bg-card p-5">
                <div>
                  <div className="text-xs uppercase text-muted-foreground">Run from frozen inputs</div>
                  <h2 className="mt-1 font-semibold">
                    {th ? "เริ่มรันจากชุดหลักฐานที่ตรวจ hash แล้ว" : "Run from a verified evidence set"}
                  </h2>
                </div>
                {currentSet ? (
                  <div className="rounded-xl border border-primary/30 bg-primary/5 p-3 text-xs">
                    <div className="font-medium">{String(currentSet.name)}</div>
                    <div className="mt-1 break-all font-mono text-[10px] text-muted-foreground">
                      {String(currentSet.content_hash)}
                    </div>
                  </div>
                ) : (
                  <p className="rounded-xl border border-dashed border-border p-4 text-xs text-muted-foreground">
                    {th ? "Freeze หลักฐานก่อนเริ่มรัน" : "Freeze evidence before starting a run"}
                  </p>
                )}
                <textarea
                  value={subject}
                  onChange={(event) => setSubject(event.target.value)}
                  placeholder={th ? "คำถามที่ต้องการจำลอง" : "Simulation question"}
                  className="min-h-28 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
                />
                <label className="flex items-start gap-2 rounded-lg border border-amber-300 bg-amber-50 p-3 text-xs text-amber-950">
                  <input
                    type="checkbox"
                    checked={populationAcknowledged}
                    onChange={(event) => setPopulationAcknowledged(event.target.checked)}
                    className="mt-0.5 size-4"
                  />
                  <span>
                    {th
                      ? "รับทราบว่า population เริ่มต้นเป็นสมมติฐานสังเคราะห์ และจะถูก freeze เป็น PopulationSetV1 ก่อนรัน"
                      : "Acknowledge that the initial population is synthetic and will be frozen as PopulationSetV1 before the run."}
                  </span>
                </label>
                <button
                  disabled={!currentSet || !populationAcknowledged || subject.trim().length < 4}
                  onClick={startRun}
                  className="w-full rounded-lg bg-primary px-3 py-2 text-sm font-medium text-white disabled:opacity-40"
                >
                  {th ? "เริ่ม Debate run →" : "Start Debate run →"}
                </button>
                <div className="border-t border-border pt-4">
                  <h3 className="text-xs font-semibold uppercase text-muted-foreground">
                    {th ? "รันที่เชื่อมกับโปรเจกต์" : "Linked runs"}
                  </h3>
                  <div className="mt-2 space-y-1">
                    {project.runs.map((run) => (
                      <button
                        key={String(run.run_id)}
                        onClick={() => onOpenRun?.(String(run.run_id))}
                        className="block w-full rounded-lg px-2 py-2 text-left font-mono text-xs hover:bg-muted"
                      >
                        {String(run.run_id)}
                      </button>
                    ))}
                  </div>
                </div>
              </section>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
