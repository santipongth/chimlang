import { useEffect, useState } from "react";
import { LangProvider, useLang } from "./i18n";
import Landing from "./pages/Landing";
import NewRun from "./pages/NewRun";
import Citizen from "./pages/Citizen";
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
  | "run" // run detail (P6-M2)
  | "compare"
  | "history"
  | "insights"
  | "calibration"
  | "watchlist"
  | "gallery"
  | "citizen"
  | "settings";

export interface RunRequest {
  subject: string;
  agents: number;
  redTeam?: boolean; // fabric A/B → หน้า Compare
  packId?: number | null;
}

function WatermarkBanner() {
  const { t } = useLang();
  return (
    <div className="bg-amber-50 border-b border-amber-200 text-amber-900 text-xs px-4 py-1.5 text-center">
      ⚠️ {t("watermark")}
    </div>
  );
}

// Sidebar ตาม layout studio: nav หลัก + Settings ล่างสุด (แบบเดียวกับต้นแบบ)
function Sidebar({ page, setPage, badges = {} }: { page: Page; setPage: (p: Page) => void; badges?: Partial<Record<Page, number>> }) {
  const { lang, setLang, t } = useLang();
  const items: { id: Page; icon: string; label: string }[] = [
    { id: "home", icon: "🏠", label: t("nav_home") },
    { id: "new", icon: "＋", label: t("nav_new_run") },
    { id: "history", icon: "🕘", label: t("nav_history") },
    { id: "insights", icon: "📈", label: t("nav_insights") },
    { id: "calibration", icon: "🎯", label: t("nav_calibration") },
    { id: "watchlist", icon: "🔔", label: t("nav_watchlist") },
    { id: "gallery", icon: "🌐", label: t("nav_gallery") },
    { id: "citizen", icon: "👥", label: t("nav_citizen") },
  ];
  return (
    <aside className="w-60 shrink-0 bg-sidebar border-r border-border flex flex-col min-h-screen p-4">
      <button onClick={() => setPage("home")} className="mb-6 flex items-center gap-2 px-2 text-left">
        <div className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary">🐟</div>
        <div>
          <div className="font-display text-lg font-semibold leading-tight">ชิมลาง</div>
          <div className="text-[11px] text-muted-foreground leading-tight">CHIMLANG</div>
        </div>
      </button>
      <nav className="flex flex-1 flex-col gap-1 text-sm">
        {items.map((it) => (
          <button
            key={it.id}
            onClick={() => setPage(it.id)}
            className={`flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left transition ${
              page === it.id ? "bg-sidebar-accent font-medium text-foreground" : "text-muted-foreground hover:bg-sidebar-accent/60"
            }`}
          >
            <span className="w-4 text-center text-[13px]">{it.icon}</span>
            {it.label}
            {(badges[it.id] ?? 0) > 0 && (
              <span className="ml-auto rounded-full bg-primary px-1.5 text-[10px] font-medium text-white">{badges[it.id]}</span>
            )}
          </button>
        ))}
      </nav>
      <button
        onClick={() => setPage("settings")}
        className={`mb-3 flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm transition ${
          page === "settings" ? "bg-sidebar-accent font-medium text-foreground" : "text-muted-foreground hover:bg-sidebar-accent/60"
        }`}
      >
        <span className="w-4 text-center text-[13px]">⚙️</span>
        {t("nav_settings")}
      </button>
      <div className="border-t border-border pt-3">
        <div className="flex rounded-full border border-border overflow-hidden text-xs">
          {(["th", "en"] as const).map((l) => (
            <button
              key={l}
              onClick={() => setLang(l)}
              className={`flex-1 py-1.5 ${lang === l ? "bg-primary text-white font-medium" : "text-muted-foreground"}`}
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

  const wide = !["new", "home", "citizen"].includes(page);

  return (
    <div className="min-h-screen">
      <WatermarkBanner />
      <div className="flex">
        <Sidebar page={page} setPage={setPage} badges={{ watchlist: unread }} />
        <main className="min-w-0 flex-1 px-8 py-10">
          <div className={`mx-auto ${wide ? "max-w-4xl" : "max-w-3xl"}`}>
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
            {page === "citizen" && <Citizen />}
            {page === "settings" && <Settings />}
          </div>
        </main>
      </div>
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
