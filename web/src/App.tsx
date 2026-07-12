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

// Sidebar ตาม layout studio: w-60, nav item rounded-lg px-3 py-2, active = bg-sidebar-accent,
// รองรับ badge ตัวเลขชิดขวา (ใช้จริงกับ alerts ใน P5-M5)
function Sidebar({ page, setPage, badges = {} }: { page: Page; setPage: (p: Page) => void; badges?: Partial<Record<Page, number>> }) {
  const { lang, setLang, t } = useLang();
  const items: { id: Page; icon: string; label: string }[] = [
    { id: "home", icon: "🏠", label: t("nav_home") },
    { id: "new", icon: "＋", label: t("nav_new_run") },
    { id: "dashboard", icon: "📊", label: t("nav_dashboard") },
    { id: "citizen", icon: "👥", label: t("nav_citizen") },
    { id: "runs", icon: "🕘", label: t("nav_runs") },
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
              <span className="ml-auto rounded-full bg-primary px-1.5 text-[10px] font-medium text-white">
                {badges[it.id]}
              </span>
            )}
          </button>
        ))}
      </nav>
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
        <main className="min-w-0 flex-1 px-8 py-10">
          {/* dashboard/runs กว้าง max-w-4xl แบบ studio; ฟอร์ม/wizard แคบ max-w-3xl */}
          <div className={`mx-auto ${page === "dashboard" || page === "runs" ? "max-w-4xl" : "max-w-3xl"}`}>
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
