import { lazy, Suspense, useEffect, useState } from "react";
import {
  BarChart3,
  Bell,
  Fish,
  FlaskConical,
  Globe,
  History,
  Languages,
  Plus,
  Settings as SettingsIcon,
  Target } from "lucide-react";
import { LangProvider, useLang } from "./i18n";
import { fetchWatchlists } from "./api";

const Landing = lazy(() => import("./pages/Landing"));
const NewRun = lazy(() => import("./pages/NewRun"));
const Runs = lazy(() => import("./pages/Runs"));
const Calibration = lazy(() => import("./pages/Calibration"));
const Compare = lazy(() => import("./pages/Compare"));
const Watchlist = lazy(() => import("./pages/Watchlist"));
const Insights = lazy(() => import("./pages/Insights"));
const Experiments = lazy(() => import("./pages/Experiments"));
const Gallery = lazy(() => import("./pages/Gallery"));
const RunDetail = lazy(() => import("./pages/RunDetail"));
const Settings = lazy(() => import("./pages/Settings"));

export type Page =
  | "home"
  | "new"
  | "run"
  | "compare"
  | "history"
  | "insights"
  | "experiments"
  | "calibration"
  | "watchlist"
  | "gallery"
  | "settings";

export interface RunRequest {
  subject: string;
  agents: number;
  redTeam?: boolean; // fabric A/B → หน้า Compare
  packId?: number | null;
}

// Sidebar ตาม studio ต้นทาง (route.tsx ของ swarm-visionary-forge): lucide icons +
// ลำดับเมนูเดียวกัน + Settings อยู่ท้าย nav
function Sidebar({
  page,
  setPage,
  badges = {},
}: {
  page: Page;
  setPage: (p: Page) => void;
  badges?: Partial<Record<Page, number>>;
}) {
  const { lang, setLang, t } = useLang();
  const items: { id: Page; icon: React.ElementType; label: string }[] = [
    { id: "new", icon: Plus, label: t("nav_new_run") },
    { id: "history", icon: History, label: t("nav_history") },
    { id: "insights", icon: BarChart3, label: t("nav_insights") },
    { id: "experiments", icon: FlaskConical, label: "Experiments" },
    { id: "calibration", icon: Target, label: t("nav_calibration") },
    { id: "gallery", icon: Globe, label: t("nav_gallery") },
    { id: "watchlist", icon: Bell, label: t("nav_watchlist") },
    { id: "settings", icon: SettingsIcon, label: t("nav_settings") },
  ];
  return (
    <aside className="hidden w-60 shrink-0 flex-col border-r border-border bg-sidebar p-4 md:flex min-h-screen">
      <button onClick={() => setPage("home")} className="mb-6 flex items-center gap-2 px-2 text-left">
        <div className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary">
          <Fish className="h-5 w-5" />
        </div>
        <span className="font-display text-lg font-semibold">ชิมลาง</span>
      </button>
      <nav className="flex flex-1 flex-col gap-1 text-sm">
        {items.map((it) => (
          <button
            key={it.id}
            onClick={() => setPage(it.id)}
            className={`flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left transition ${
              page === it.id
                ? "bg-sidebar-accent font-medium text-foreground"
                : "text-muted-foreground hover:bg-sidebar-accent/60"
            }`}
          >
            <it.icon className="h-4 w-4 shrink-0" />
            {it.label}
            {(badges[it.id] ?? 0) > 0 && (
              <span className="ml-auto rounded-full bg-primary px-1.5 text-[10px] font-medium text-white">
                {badges[it.id]}
              </span>
            )}
          </button>
        ))}
      </nav>
      {/* ตัวสลับภาษา — mini segmented control มุมล่าง (redesign 12 ก.ค.) */}
      <div className="mt-4 flex items-center justify-between border-t border-border px-1 pt-3">
        <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Languages className="h-3.5 w-3.5" /> {t("lang_label")}
        </span>
        <div className="flex overflow-hidden rounded-lg border border-border text-[11px]">
          {(["th", "en"] as const).map((l) => (
            <button
              key={l}
              onClick={() => setLang(l)}
              className={`px-2.5 py-1 transition ${
                lang === l ? "bg-primary font-medium text-white" : "text-muted-foreground hover:bg-muted"
              }`}
            >
              {l === "th" ? "ไทย" : "EN"}
            </button>
          ))}
        </div>
      </div>
    </aside>
  );
}

function Shell() {
  const initialHash = window.location.hash.replace(/^#\/?/, "");
  const initialRun = initialHash.match(/^runs\/([^/]+)$/)?.[1] ?? null;
  const initialPage = (initialRun ? "run" : initialHash || "home") as Page;
  const [page, setPage] = useState<Page>(initialPage);
  const [request, setRequest] = useState<RunRequest | null>(null);
  const [runId, setRunId] = useState<string | null>(initialRun);
  const [unread, setUnread] = useState(0);

  const refreshUnread = () =>
    fetchWatchlists()
      .then((d) => setUnread(d.unread))
      .catch(() => {});
  useEffect(() => {
    refreshUnread();
    const timer = setInterval(refreshUnread, 60_000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    const syncRoute = () => {
      const hash = window.location.hash.replace(/^#\/?/, "");
      const matchedRun = hash.match(/^runs\/([^/]+)$/)?.[1];
      if (matchedRun) {
        setRunId(matchedRun);
        setPage("run");
      } else if (hash) {
        setPage(hash as Page);
      } else {
        setPage("home");
      }
    };
    window.addEventListener("hashchange", syncRoute);
    return () => window.removeEventListener("hashchange", syncRoute);
  }, []);

  const goPage = (next: Page) => {
    window.location.hash = `/${next}`;
    setPage(next);
  };
  const goRun = (id: string) => {
    setRunId(id);
    window.location.hash = `/runs/${encodeURIComponent(id)}`;
    setPage("run");
  };

  return (
    <div className="flex min-h-screen bg-background">
      <Sidebar page={page} setPage={goPage} badges={{ watchlist: unread }} />
      <main className="min-w-0 flex-1 px-4 py-8 sm:px-8 lg:px-12">
        <div className="w-full">
          <Suspense fallback={<div className="rounded-2xl border border-border bg-card p-8 text-sm text-muted-foreground">กำลังโหลดหน้า…</div>}>
          {page === "home" && <Landing onStart={() => goPage("new")} />}
          {page === "new" && (
            <NewRun
              onCompare={(req) => {
                setRequest(req);
                goPage("compare");
              }}
              onCreated={(id) => {
                goRun(id);
              }}
            />
          )}
          {page === "run" && runId && <RunDetail runId={runId} onBack={() => goPage("history")} />}
          {page === "compare" && <Compare request={request} />}
          {page === "history" && (
            <Runs
              onOpen={(id) => {
                goRun(id);
              }}
            />
          )}
          {page === "insights" && <Insights />}
          {page === "experiments" && <Experiments />}
          {page === "calibration" && <Calibration />}
          {page === "watchlist" && <Watchlist onChanged={refreshUnread} />}
          {page === "gallery" && <Gallery />}
          {page === "settings" && <Settings />}
          </Suspense>
        </div>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <LangProvider>
      <Shell />
    </LangProvider>
  );
}
