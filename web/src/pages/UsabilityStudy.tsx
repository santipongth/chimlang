import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, Clock3, Download, ExternalLink, RotateCcw, Users } from "lucide-react";
import { useLang } from "../i18n";
import { PageHeader } from "../ui";

type TaskStatus = "pending" | "in_progress" | "complete" | "blocked";

type TaskResult = {
  status: TaskStatus;
  started_at: number | null;
  elapsed_seconds: number | null;
  critical_errors: number;
  ease: number;
  note_category: string;
};

type ParticipantRecord = {
  code: string;
  consent_confirmed: boolean;
  tasks: TaskResult[];
};

const STORAGE_KEY = "chimlang-usability-p9m3-v1";

const TASKS = [
  {
    route: "/projects",
    th: "สร้างโปรเจกต์ใหม่จาก brief ที่ผู้ดำเนินการให้",
    en: "Create a new project from the supplied brief.",
    successTh: "สร้างโปรเจกต์และเห็น workflow ขั้น Brief",
    successEn: "A project is created and the Brief workflow stage is visible.",
  },
  {
    route: "/projects",
    th: "เพิ่มหลักฐานหนึ่งชิ้น ตรวจ PII และ freeze เป็น EvidenceSetV1",
    en: "Add one evidence item, check PII, and freeze it as EvidenceSetV1.",
    successTh: "เห็น evidence version, hash และ frozen set",
    successEn: "The evidence version, hash, and frozen set are visible.",
  },
  {
    route: "/new",
    th: "เริ่มรันหนึ่งครั้ง แล้วหาวิธียกเลิกรันที่กำลังทำงาน",
    en: "Start one run, then find how to cancel it while it is active.",
    successTh: "เข้า Run Detail ทันทีและสถานะสุดท้ายเป็น canceled",
    successEn: "Run Detail opens immediately and the terminal status is canceled.",
  },
  {
    route: "/validation",
    th: "หา Validation Lab และอธิบายว่า claim ใดวัดผลแล้วหรือยังถูก block",
    en: "Find Validation Lab and identify which claims are measured or blocked.",
    successTh: "แยก measured ออกจาก blocked ได้โดยไม่ต้องให้คำใบ้",
    successEn: "Measured and blocked claims are distinguished without a hint.",
  },
  {
    route: "/history",
    th: "เปิดผลรันเดิมและ export snapshot โดยไม่รัน simulation ใหม่",
    en: "Open a stored result and export its snapshot without rerunning it.",
    successTh: "ได้ JSON หรือ PDF ที่มี manifest hash/watermark",
    successEn: "A JSON or PDF with manifest hash/watermark is produced.",
  },
] as const;

function emptyParticipant(index: number): ParticipantRecord {
  return {
    code: "P" + String(index + 1).padStart(2, "0"),
    consent_confirmed: false,
    tasks: TASKS.map(() => ({
      status: "pending",
      started_at: null,
      elapsed_seconds: null,
      critical_errors: 0,
      ease: 3,
      note_category: "none",
    })),
  };
}

function initialRecords(): ParticipantRecord[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
    if (Array.isArray(parsed) && parsed.length === 5) return parsed;
  } catch {
    // Corrupt local mock data is disposable and must not block the study.
  }
  return Array.from({ length: 5 }, (_, index) => emptyParticipant(index));
}

export default function UsabilityStudy() {
  const { lang, formatNumber } = useLang();
  const th = lang === "th";
  const [records, setRecords] = useState<ParticipantRecord[]>(initialRecords);
  const [selected, setSelected] = useState(0);
  const [moderatorMode, setModeratorMode] = useState(false);
  const participant = records[selected];

  const copy = th
    ? {
        eyebrow: "P9-M3 · USABILITY",
        title: "ชุดทดสอบกับผู้ใช้ไทย 5 คน",
        desc: "งานจริงห้าข้อแบบไม่ชี้นำ เก็บเฉพาะรหัสนิรนาม เวลา ความสำเร็จ และหมวดปัญหาในเครื่องนี้",
        participant: "ผู้เข้าร่วม",
        moderator: "โหมดผู้ดำเนินการ",
        consent: "ผู้เข้าร่วมยืนยัน consent สำหรับการทดสอบและการเก็บผลแบบนิรนามแล้ว",
        task: "งาน",
        open: "เปิดพื้นที่ทำงาน",
        start: "เริ่มจับเวลา",
        complete: "ทำสำเร็จ",
        blocked: "ติดขัด",
        pending: "ยังไม่เริ่ม",
        inProgress: "กำลังทำ",
        done: "สำเร็จ",
        success: "เกณฑ์สำเร็จสำหรับผู้ดำเนินการ",
        errors: "critical errors",
        ease: "ความง่าย 1–5",
        category: "หมวดบันทึก",
        export: "ส่งออกผลนิรนาม JSON",
        reset: "ล้าง mockup ชุดนี้",
        summary: "ความคืบหน้ารวม",
        realOnly: "ห้ามกรอกผลแทนผู้เข้าร่วม ผลจะถือว่าใช้ได้เมื่อทดสอบจริงครบทั้ง 5 คน",
      }
    : {
        eyebrow: "P9-M3 · USABILITY",
        title: "Five-participant Thai usability study",
        desc: "Five neutral real tasks; only anonymous codes, time, completion, and issue categories stay on this device.",
        participant: "Participant",
        moderator: "Moderator mode",
        consent: "The participant confirmed consent for testing and anonymized result capture.",
        task: "Task",
        open: "Open workspace",
        start: "Start timer",
        complete: "Complete",
        blocked: "Blocked",
        pending: "Pending",
        inProgress: "In progress",
        done: "Complete",
        success: "Moderator success criterion",
        errors: "critical errors",
        ease: "Ease 1–5",
        category: "Note category",
        export: "Export anonymized JSON",
        reset: "Reset this mockup",
        summary: "Overall progress",
        realOnly: "Do not enter results on a participant's behalf. Evidence is valid only after all five people complete a real session.",
      };

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(records));
  }, [records]);

  const completed = useMemo(
    () => records.reduce((total, record) => total + record.tasks.filter((task) => task.status === "complete").length, 0),
    [records],
  );
  const required = records.length * TASKS.length;

  function updateParticipant(update: (record: ParticipantRecord) => ParticipantRecord) {
    setRecords((current) => current.map((record, index) => (index === selected ? update(record) : record)));
  }

  function updateTask(taskIndex: number, update: Partial<TaskResult>) {
    updateParticipant((record) => ({
      ...record,
      tasks: record.tasks.map((task, index) => (index === taskIndex ? { ...task, ...update } : task)),
    }));
  }

  function startTask(taskIndex: number) {
    if (!participant.consent_confirmed) return;
    updateTask(taskIndex, { status: "in_progress", started_at: Date.now(), elapsed_seconds: null });
  }

  function finishTask(taskIndex: number, status: "complete" | "blocked") {
    const task = participant.tasks[taskIndex];
    updateTask(taskIndex, {
      status,
      elapsed_seconds: task.started_at == null ? null : Math.max(1, Math.round((Date.now() - task.started_at) / 1000)),
    });
  }

  function exportResults() {
    const payload = {
      schema_version: 1,
      protocol: "P9-M3-usability-v1",
      generated_at: new Date().toISOString(),
      claim_ready: completed === required && records.every((record) => record.consent_confirmed),
      participants: records,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "chimlang-usability-anonymized.json";
    link.click();
    URL.revokeObjectURL(url);
  }

  function resetStudy() {
    if (!window.confirm(th ? "ล้างผลในเครื่องทั้งหมดหรือไม่" : "Clear all local study results?")) return;
    setRecords(Array.from({ length: 5 }, (_, index) => emptyParticipant(index)));
    setSelected(0);
  }

  const statusLabel = (status: TaskStatus) =>
    status === "complete"
      ? copy.done
      : status === "in_progress"
        ? copy.inProgress
        : status === "blocked"
          ? copy.blocked
          : copy.pending;

  return (
    <div className="space-y-6">
      <PageHeader eyebrow={copy.eyebrow} title={copy.title} desc={copy.desc} />
      <section aria-labelledby="study-progress" className="rounded-2xl border border-border bg-card p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 id="study-progress" className="font-semibold">{copy.summary}</h2>
            <p className="mt-1 text-sm text-muted-foreground">{formatNumber(completed)} / {formatNumber(required)}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={() => setModeratorMode((value) => !value)} aria-pressed={moderatorMode} className="rounded-lg border border-border px-3 py-2 text-sm">
              <Users className="mr-1 inline h-4 w-4" aria-hidden="true" /> {copy.moderator}
            </button>
            <button type="button" onClick={exportResults} className="rounded-lg border border-primary px-3 py-2 text-sm text-primary-strong">
              <Download className="mr-1 inline h-4 w-4" aria-hidden="true" /> {copy.export}
            </button>
            <button type="button" onClick={resetStudy} className="rounded-lg border border-red-200 px-3 py-2 text-sm text-red-700">
              <RotateCcw className="mr-1 inline h-4 w-4" aria-hidden="true" /> {copy.reset}
            </button>
          </div>
        </div>
        <div className="mt-4 h-2 overflow-hidden rounded-full bg-muted" role="progressbar" aria-valuemin={0} aria-valuemax={required} aria-valuenow={completed} aria-label={copy.summary}>
          <div className="h-full bg-primary" style={{ width: String((completed / required) * 100) + "%" }} />
        </div>
        <p className="mt-3 rounded-lg bg-amber-50 p-3 text-xs text-amber-900">{copy.realOnly}</p>
      </section>

      <div className="grid gap-5 lg:grid-cols-[15rem_1fr]">
        <aside aria-label={copy.participant} className="rounded-2xl border border-border bg-card p-3">
          <div className="px-2 py-2 text-xs font-semibold uppercase text-muted-foreground">{copy.participant}</div>
          <div className="space-y-1">
            {records.map((record, index) => (
              <button key={record.code} type="button" aria-pressed={selected === index} onClick={() => setSelected(index)} className={(selected === index ? "bg-primary/10 text-primary-strong " : "hover:bg-muted ") + "flex w-full items-center justify-between rounded-lg px-3 py-3 text-left text-sm"}>
                <span>{record.code}</span>
                <span className="text-xs">{record.tasks.filter((task) => task.status === "complete").length}/{TASKS.length}</span>
              </button>
            ))}
          </div>
        </aside>

        <section aria-labelledby="participant-title" className="space-y-4">
          <div className="rounded-2xl border border-border bg-card p-5">
            <h2 id="participant-title" className="text-lg font-semibold">{copy.participant} {participant.code}</h2>
            <label className="mt-3 flex min-h-11 items-start gap-3 rounded-lg border border-border p-3 text-sm">
              <input type="checkbox" checked={participant.consent_confirmed} onChange={(event) => updateParticipant((record) => ({ ...record, consent_confirmed: event.target.checked }))} className="mt-0.5 h-6 w-6 shrink-0" />
              <span>{copy.consent}</span>
            </label>
          </div>

          {TASKS.map((task, index) => {
            const result = participant.tasks[index];
            return (
              <article key={task.route + String(index)} className="rounded-2xl border border-border bg-card p-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="max-w-2xl">
                    <div className="text-xs font-semibold uppercase text-muted-foreground">{copy.task} {index + 1}</div>
                    <h3 className="mt-1 font-semibold">{th ? task.th : task.en}</h3>
                    {moderatorMode && <p className="mt-2 rounded-lg bg-muted p-3 text-xs"><b>{copy.success}:</b> {th ? task.successTh : task.successEn}</p>}
                  </div>
                  <span className="rounded-full bg-muted px-3 py-1 text-xs">{statusLabel(result.status)}</span>
                </div>
                <div className="mt-4 flex flex-wrap gap-2">
                  <a href={"#" + task.route} target="_blank" rel="noreferrer" className="inline-flex items-center rounded-lg border border-border px-3 py-2 text-sm">
                    {copy.open} <ExternalLink className="ml-1 h-4 w-4" aria-hidden="true" />
                  </a>
                  <button type="button" disabled={!participant.consent_confirmed} onClick={() => startTask(index)} className="rounded-lg border border-border px-3 py-2 text-sm disabled:opacity-40">
                    <Clock3 className="mr-1 inline h-4 w-4" aria-hidden="true" /> {copy.start}
                  </button>
                  <button type="button" disabled={result.status !== "in_progress"} onClick={() => finishTask(index, "complete")} className="rounded-lg bg-primary px-3 py-2 text-sm font-medium text-white disabled:opacity-40">
                    <CheckCircle2 className="mr-1 inline h-4 w-4" aria-hidden="true" /> {copy.complete}
                  </button>
                  <button type="button" disabled={result.status !== "in_progress"} onClick={() => finishTask(index, "blocked")} className="rounded-lg border border-red-200 px-3 py-2 text-sm text-red-700 disabled:opacity-40">
                    {copy.blocked}
                  </button>
                </div>
                {moderatorMode && (
                  <div className="mt-4 grid gap-3 border-t border-border pt-4 sm:grid-cols-3">
                    <label className="text-xs">{copy.errors}<input aria-label={copy.errors} type="number" min={0} max={20} value={result.critical_errors} onChange={(event) => updateTask(index, { critical_errors: Number(event.target.value) })} className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" /></label>
                    <label className="text-xs">{copy.ease}<input aria-label={copy.ease} type="number" min={1} max={5} value={result.ease} onChange={(event) => updateTask(index, { ease: Number(event.target.value) })} className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" /></label>
                    <label className="text-xs">{copy.category}<select aria-label={copy.category} value={result.note_category} onChange={(event) => updateTask(index, { note_category: event.target.value })} className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"><option value="none">—</option><option value="navigation">navigation</option><option value="terminology">terminology</option><option value="trust">trust</option><option value="accessibility">accessibility</option><option value="error-recovery">error recovery</option></select></label>
                  </div>
                )}
              </article>
            );
          })}
        </section>
      </div>
    </div>
  );
}
