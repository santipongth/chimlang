import { useState } from "react";
import { LangProvider, useLang } from "./i18n";
import Landing from "./pages/Landing";
import NewRun from "./pages/NewRun";
import Dashboard from "./pages/Dashboard";
import Citizen from "./pages/Citizen";
import Runs from "./pages/Runs";
import type { DashboardData } from "./api";

export type Page = "home" | "new" | "dashboard" | "citizen" | "runs";
export interface RunRequest {
  subject: string;
  agents: number;
}

function WatermarkBanner() {
  const { t } = useLang();
  return (
    <div className="bg-amber-50 border-b border-amber-200 text-amber-900 text-xs px-4 py-1.5 text-center">
      ⚠️ {t("watermark")}
    </div>
  );
}

function Sidebar({ page, setPage }: { page: Page; setPage: (p: Page) => void }) {
  const { lang, setLang, t } = useLang();
  const items: { id: Page; icon: string; label: string }[] = [
    { id: "home", icon: "🏠", label: t("nav_home") },
    { id: "new", icon: "＋", label: t("nav_new_run") },
    { id: "dashboard", icon: "📊", label: t("nav_dashboard") },
    { id: "citizen", icon: "👥", label: t("nav_citizen") },
    { id: "runs", icon: "🕘", label: t("nav_runs") },
  ];
  return (
    <aside className="w-64 shrink-0 bg-sidebar border-r border-border flex flex-col min-h-screen">
      <div className="flex items-center gap-3 px-5 py-5">
        <div className="w-9 h-9 rounded-full bg-primary-soft flex items-center justify-center text-lg">🐟</div>
        <div>
          <div className="font-display text-lg font-semibold leading-tight">ชิมลาง</div>
          <div className="text-[11px] text-muted-foreground leading-tight">CHIMLANG</div>
        </div>
      </div>
      <nav className="px-3 space-y-1 flex-1">
        {items.map((it) => (
          <button
            key={it.id}
            onClick={() => setPage(it.id)}
            className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-xl text-sm text-left transition ${
              page === it.id ? "bg-secondary font-medium text-foreground" : "text-muted-foreground hover:bg-muted"
            }`}
          >
            <span className="w-5 text-center">{it.icon}</span>
            {it.label}
          </button>
        ))}
      </nav>
      <div className="px-5 py-4 border-t border-border">
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
  const [result, setResult] = useState<DashboardData | null>(null);

  const startRun = (req: RunRequest) => {
    setRequest(req);
    setResult(null);
    setPage("dashboard");
  };

  return (
    <div className="min-h-screen">
      <WatermarkBanner />
      <div className="flex">
        <Sidebar page={page} setPage={setPage} />
        <main className="flex-1 px-8 py-10">
          <div className="max-w-3xl mx-auto">
          {page === "home" && <Landing onStart={() => setPage("new")} />}
          {page === "new" && <NewRun onRun={startRun} />}
          {page === "dashboard" && (
            <Dashboard request={request} result={result} setResult={setResult} onNew={() => setPage("new")} />
          )}
          {page === "citizen" && <Citizen />}
          {page === "runs" && <Runs />}
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
