import { useEffect, useState } from "react";
import {
  BarChart3,
  Bell,
  Fish,
  Globe,
  History,
  Languages,
  Plus,
  Settings as SettingsIcon,
  Target } from "lucide-react";
import { LangProvider, useLang } from "./i18n";
import Landing from "./pages/Landing";
import NewRun from "./pages/NewRun";
import Runs from "./pages/Runs";
import Calibration from "./pages/Calibration";
import Compare from "./pages/Compare";
import Watchlist from "./pages/Watchlist";
import Insights from "./pages/Insights";
import Gallery from "./pages/Gallery";
import RunDetail from "./pages/RunDetail";
import Settings from "./pages/Settings";
import { fetchWatchlists } from "./api";

export type Page =
  | "home"
  | "new"
  | "run"
  | "compare"
  | "history"
  | "insights"
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
  const [page, setPage] = useState<Page>("home");
  const [request, setRequest] = useState<RunRequest | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
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

  return (
    <div className="flex min-h-screen bg-background">
      <Sidebar page={page} setPage={setPage} badges={{ watchlist: unread }} />
      <main className="min-w-0 flex-1 px-4 py-8 sm:px-8 lg:px-12">
        <div className="w-full">
          {page === "home" && <Landing onStart={() => setPage("new")} />}
          {page === "new" && (
            <NewRun
              onCompare={(req) => {
                setRequest(req);
                setPage("compare");
              }}
              onCreated={(id) => {
                setRunId(id);
                setPage("run");
              }}
            />
          )}
          {page === "run" && runId && <RunDetail runId={runId} onBack={() => setPage("history")} />}
          {page === "compare" && <Compare request={request} />}
          {page === "history" && (
            <Runs
              onOpen={(id) => {
                setRunId(id);
                setPage("run");
              }}
            />
          )}
          {page === "insights" && <Insights />}
          {page === "calibration" && <Calibration />}
          {page === "watchlist" && <Watchlist onChanged={refreshUnread} />}
          {page === "gallery" && <Gallery />}
          {page === "settings" && <Settings />}
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
