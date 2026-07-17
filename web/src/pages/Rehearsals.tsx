import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import {
  answerRehearsal,
  controlRehearsal,
  createRehearsal,
  fetchRehearsal,
  fetchRehearsals,
  finishRehearsal,
  logRehearsalDecision,
  nextRehearsalQuestion,
  type RehearsalDetail,
} from "../api";
import { useLang } from "../i18n";
import { PageHeader } from "../ui";

export default function Rehearsals({
  initialSessionId = "",
  onSelect,
}: {
  initialSessionId?: string;
  onSelect?: (sessionId: string) => void;
}) {
  const { lang } = useLang();
  const th = lang === "th";
  const client = useQueryClient();
  const [selected, setSelected] = useState(initialSessionId);
  const [title, setTitle] = useState("");
  const [scenario, setScenario] = useState("");
  const [answer, setAnswer] = useState("");
  const [decision, setDecision] = useState("");
  const [error, setError] = useState("");
  const currency = useMemo(
    () =>
      new Intl.NumberFormat(th ? "th-TH" : "en-US", {
        style: "currency",
        currency: "USD",
        minimumFractionDigits: 4,
      }),
    [th],
  );

  const list = useQuery({ queryKey: ["rehearsals"], queryFn: fetchRehearsals });
  const detail = useQuery({
    queryKey: ["rehearsal", selected],
    queryFn: () => fetchRehearsal(selected),
    enabled: !!selected,
  });
  const accept = (result: RehearsalDetail) => {
    client.setQueryData(["rehearsal", result.session_id], result);
    client.invalidateQueries({ queryKey: ["rehearsals"] });
    setError("");
  };
  const fail = (reason: unknown) => setError(String(reason));
  const create = useMutation({
    mutationFn: () =>
      createRehearsal({
        title,
        scenario,
        seed: null,
        netizens: 4,
        max_turns: 8,
        reactions_per_turn: 2,
      }),
    onSuccess: (result) => {
      setSelected(result.session_id);
      onSelect?.(result.session_id);
      accept(result);
    },
    onError: fail,
  });
  const next = useMutation({
    mutationFn: () => nextRehearsalQuestion(selected),
    onSuccess: accept,
    onError: fail,
  });
  const submit = useMutation({
    mutationFn: () => answerRehearsal(selected, answer),
    onSuccess: (result) => {
      setAnswer("");
      accept(result);
    },
    onError: fail,
  });
  const control = useMutation({
    mutationFn: (action: "pause" | "resume") => controlRehearsal(selected, action),
    onSuccess: accept,
    onError: fail,
  });
  const finish = useMutation({
    mutationFn: () => finishRehearsal(selected),
    onSuccess: accept,
    onError: fail,
  });
  const addDecision = useMutation({
    mutationFn: () => logRehearsalDecision(selected, decision),
    onSuccess: (result) => {
      setDecision("");
      accept(result);
    },
    onError: fail,
  });

  const session = detail.data;
  const current = session?.turns[session.turns.length - 1];
  const pending = current && !Boolean(current.answered);
  const busy =
    next.isPending ||
    submit.isPending ||
    control.isPending ||
    finish.isPending ||
    addDecision.isPending;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="PRESS ROOM REHEARSAL"
        title={th ? "ซ้อมตอบคำถามแบบ turn-by-turn" : "Turn-by-turn press room rehearsal"}
        desc={
          th
            ? "หยุดพัก กลับมาซ้อมต่อ บันทึกมติ และจบด้วย scorecard ที่ย้อนถึง transcript ได้"
            : "Pause, resume, log decisions and finish with a transcript-grounded scorecard."
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
            <h2 className="font-semibold">{th ? "เริ่มวงซ้อม" : "Start rehearsal"}</h2>
            <input
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder={th ? "ชื่อวงซ้อม" : "Session title"}
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
            />
            <textarea
              value={scenario}
              onChange={(event) => setScenario(event.target.value)}
              placeholder={th ? "บริบทเรื่องที่จะแถลง" : "Press-room scenario"}
              className="min-h-28 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
            />
            <p className="text-[11px] text-muted-foreground">
              {th
                ? "ระบบประเมินคำตอบ แต่จะไม่ร่างสคริปต์ชักจูงให้ (GOV-05)"
                : "The system critiques answers but never ghostwrites persuasive scripts (GOV-05)."}
            </p>
            <button
              disabled={title.trim().length < 2 || scenario.trim().length < 4 || create.isPending}
              onClick={() => create.mutate()}
              className="w-full rounded-lg bg-primary px-3 py-2 text-sm font-medium text-white disabled:opacity-40"
            >
              {th ? "สร้าง session และ preflight งบ" : "Create session and preflight budget"}
            </button>
          </section>
          <section className="rounded-2xl border border-border bg-card p-3">
            <h2 className="px-2 py-1 text-xs font-semibold uppercase text-muted-foreground">
              Sessions
            </h2>
            <div className="mt-1 max-h-96 space-y-1 overflow-y-auto">
              {(list.data ?? []).map((item) => (
                <button
                  key={item.session_id}
                  onClick={() => {
                    setSelected(item.session_id);
                    onSelect?.(item.session_id);
                  }}
                  className={[
                    "w-full rounded-lg px-3 py-2 text-left text-xs",
                    selected === item.session_id ? "bg-primary/10" : "hover:bg-muted",
                  ].join(" ")}
                >
                  <div className="font-medium">{item.title}</div>
                  <div className="mt-1 text-[10px] text-muted-foreground">
                    {item.status} · {currency.format(item.cost_usd)}
                  </div>
                </button>
              ))}
            </div>
          </section>
        </aside>
        {!session ? (
          <div className="rounded-2xl border border-dashed border-border p-12 text-center text-sm text-muted-foreground">
            {th ? "เลือกหรือสร้าง rehearsal session" : "Select or create a rehearsal session"}
          </div>
        ) : (
          <div className="space-y-5">
            <section className="rounded-2xl border border-border bg-card p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="text-xs uppercase text-muted-foreground">
                    {session.status} · {currency.format(session.cost_usd)}
                  </div>
                  <h2 className="mt-1 text-xl font-semibold">{session.title}</h2>
                  <p className="mt-2 text-sm text-muted-foreground">{session.scenario}</p>
                </div>
                <div className="flex gap-2">
                  {session.status === "active" && (
                    <button
                      disabled={busy}
                      onClick={() => control.mutate("pause")}
                      className="rounded-lg border border-border px-3 py-2 text-xs"
                    >
                      {th ? "พัก" : "Pause"}
                    </button>
                  )}
                  {session.status === "paused" && (
                    <button
                      disabled={busy}
                      onClick={() => control.mutate("resume")}
                      className="rounded-lg border border-primary px-3 py-2 text-xs text-primary-strong"
                    >
                      {th ? "ซ้อมต่อ" : "Resume"}
                    </button>
                  )}
                  {session.status === "active" && session.turns.some((turn) => Boolean(turn.answered)) && (
                    <button
                      disabled={busy || Boolean(pending)}
                      onClick={() => finish.mutate()}
                      className="rounded-lg bg-foreground px-3 py-2 text-xs text-background disabled:opacity-40"
                    >
                      {th ? "จบและประเมิน" : "Finish & score"}
                    </button>
                  )}
                </div>
              </div>
            </section>
            <div className="grid gap-5 xl:grid-cols-[1.3fr_0.7fr]">
              <section className="space-y-4 rounded-2xl border border-border bg-card p-5">
                <div className="flex items-center justify-between">
                  <h2 className="font-semibold">{th ? "Transcript" : "Transcript"}</h2>
                  <span className="text-xs text-muted-foreground">
                    {session.turns.length}/{session.max_turns}
                  </span>
                </div>
                <div className="max-h-[520px] space-y-4 overflow-y-auto pr-1" aria-live="polite">
                  {session.turns.map((turn) => (
                    <article key={Number(turn.turn_no)} className="rounded-xl border border-border p-4">
                      <div className="text-xs font-semibold text-primary-strong">
                        Q{String(turn.turn_no)} · {String(turn.journalist)}
                      </div>
                      <p className="mt-2 text-sm">{String(turn.question)}</p>
                      {Boolean(turn.answered) && (
                        <>
                          <div className="mt-3 rounded-lg bg-muted/50 p-3 text-sm">
                            <span className="text-xs font-semibold text-muted-foreground">
                              {th ? "คำตอบผู้แถลง" : "Operator answer"}
                            </span>
                            <p className="mt-1">{String(turn.answer)}</p>
                          </div>
                          <div className="mt-2 space-y-1">
                            {(Array.isArray(turn.reactions) ? turn.reactions : []).map((reaction) => (
                              <p key={String(reaction)} className="text-xs text-muted-foreground">
                                💬 {String(reaction)}
                              </p>
                            ))}
                          </div>
                        </>
                      )}
                    </article>
                  ))}
                  {session.turns.length === 0 && (
                    <p className="rounded-xl border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
                      {th ? "กดเริ่มคำถามแรกเมื่อพร้อม" : "Start the first question when ready"}
                    </p>
                  )}
                </div>
                {session.status === "active" && !pending && session.turns.length < session.max_turns && (
                  <button
                    disabled={busy}
                    onClick={() => next.mutate()}
                    className="w-full rounded-lg bg-primary px-4 py-3 text-sm font-medium text-white disabled:opacity-40"
                  >
                    {next.isPending
                      ? th
                        ? "นักข่าวกำลังเตรียมคำถาม…"
                        : "Journalist is preparing…"
                      : th
                        ? "คำถามถัดไป"
                        : "Next question"}
                  </button>
                )}
                {session.status === "active" && pending && (
                  <div className="space-y-2">
                    <label htmlFor="rehearsal-answer" className="text-xs font-semibold">
                      {th ? "คำตอบของคุณ" : "Your answer"}
                    </label>
                    <textarea
                      id="rehearsal-answer"
                      value={answer}
                      onChange={(event) => setAnswer(event.target.value)}
                      className="min-h-28 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
                    />
                    <button
                      disabled={!answer.trim() || submit.isPending}
                      onClick={() => submit.mutate()}
                      className="w-full rounded-lg bg-primary px-4 py-3 text-sm font-medium text-white disabled:opacity-40"
                    >
                      {th ? "ส่งคำตอบและดูปฏิกิริยา" : "Submit answer and reactions"}
                    </button>
                  </div>
                )}
              </section>
              <div className="space-y-5">
                <section className="space-y-3 rounded-2xl border border-border bg-card p-5">
                  <h2 className="font-semibold">{th ? "Decision log" : "Decision log"}</h2>
                  <textarea
                    value={decision}
                    onChange={(event) => setDecision(event.target.value)}
                    placeholder={th ? "บันทึกมติ/สิ่งที่จะปรับ" : "Record a decision or adjustment"}
                    className="min-h-20 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
                  />
                  <button
                    disabled={!decision.trim() || addDecision.isPending}
                    onClick={() => addDecision.mutate()}
                    className="w-full rounded-lg border border-primary px-3 py-2 text-xs text-primary-strong disabled:opacity-40"
                  >
                    {th ? "บันทึกแบบ append-only" : "Append decision"}
                  </button>
                  <div className="space-y-2">
                    {session.decisions.map((event) => (
                      <p key={Number(event.id)} className="rounded-lg bg-muted/50 p-2 text-xs">
                        {String(
                          Object.entries(event.payload ?? {}).find(([key]) => key === "decision")?.[1] ?? "",
                        )}
                      </p>
                    ))}
                  </div>
                </section>
                {session.scorecard && (
                  <section className="space-y-4 rounded-2xl border border-primary/30 bg-primary/5 p-5">
                    <div>
                      <div className="text-xs uppercase text-primary-strong">Scorecard</div>
                      <p className="mt-2 text-sm">{String(session.scorecard.summary ?? "")}</p>
                    </div>
                    {[
                      [th ? "ดับไฟ" : "Calmed", session.scorecard.calmed],
                      [th ? "ราดน้ำมัน" : "Inflamed", session.scorecard.inflamed],
                      [th ? "ประโยคเสี่ยง" : "Risky quotes", session.scorecard.risky_quotes],
                    ].map(([label, values]) => (
                      <div key={String(label)}>
                        <h3 className="text-xs font-semibold">{String(label)}</h3>
                        <ul className="mt-1 list-disc space-y-1 pl-4 text-xs">
                          {(Array.isArray(values) ? values : []).map((value) => (
                            <li key={String(value)}>{String(value)}</li>
                          ))}
                        </ul>
                      </div>
                    ))}
                    <p className="text-[10px] text-muted-foreground">
                      simulation_estimate · GOV-05 no ghostwriting · transcript grounded
                    </p>
                  </section>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
