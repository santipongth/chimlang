import { lazy, Suspense, useEffect, useRef, useState, type ElementType } from "react";
import {
  BarChart3,
  Bell,
  Fish,
  Globe,
  History,
  Languages,
  Menu,
  Plus,
  Settings as SettingsIcon,
  X,
} from "lucide-react";
import {
  HashRouter,
  Link,
  NavLink,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useParams,
} from "react-router-dom";
import { LangProvider, useLang } from "./i18n";
import { fetchShellUnread } from "./api-shell";

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

export const ROUTES = {
  home: "/",
  new: "/new",
  compare: "/compare",
  history: "/history",
  insights: "/insights",
  experiments: "/experiments",
  calibration: "/calibration",
  watchlist: "/watchlist",
  gallery: "/gallery",
  settings: "/settings",
  run: (runId: string) => `/runs/${encodeURIComponent(runId)}`,
  galleryItem: (token: string) => `/gallery/${encodeURIComponent(token)}`,
  experiment: (experimentId: string) => `/experiments/${encodeURIComponent(experimentId)}`,
} as const;

export interface RunRequest {
  subject: string;
  agents: number;
  redTeam?: boolean;
  packId?: number | null;
}

type NavigationItem = {
  to: string;
  icon: ElementType;
  label: string;
  badge?: number;
};

function LanguageControl() {
  const { lang, setLang, t } = useLang();
  return (
    <div className="mt-4 flex items-center justify-between border-t border-border px-1 pt-3">
      <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <Languages className="h-3.5 w-3.5" /> {t("lang_label")}
      </span>
      <div
        className="flex overflow-hidden rounded-lg border border-border text-[11px]"
        role="group"
        aria-label={t("language_options")}
      >
        {(["th", "en"] as const).map((candidate) => (
          <button
            key={candidate}
            type="button"
            aria-pressed={lang === candidate}
            aria-label={candidate === "th" ? "ภาษาไทย" : "English"}
            onClick={() => setLang(candidate)}
            className={`px-2.5 py-1 transition ${
              lang === candidate
                ? "bg-primary font-medium text-white"
                : "text-muted-foreground hover:bg-muted"
            }`}
          >
            {candidate === "th" ? "ไทย" : "EN"}
          </button>
        ))}
      </div>
    </div>
  );
}

function Navigation({ unread, onNavigate }: { unread: number; onNavigate?: () => void }) {
  const { t } = useLang();
  const items: NavigationItem[] = [
    { to: ROUTES.new, icon: Plus, label: t("nav_new_run") },
    { to: ROUTES.history, icon: History, label: t("nav_history") },
    { to: ROUTES.insights, icon: BarChart3, label: t("nav_insights") },
    { to: ROUTES.gallery, icon: Globe, label: t("nav_gallery") },
    { to: ROUTES.watchlist, icon: Bell, label: t("nav_watchlist"), badge: unread },
    { to: ROUTES.settings, icon: SettingsIcon, label: t("nav_settings") },
  ];
  return (
    <>
      <Link to={ROUTES.home} onClick={onNavigate} className="mb-6 flex items-center gap-2 px-2 text-left">
        <div className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary">
          <Fish className="h-5 w-5" />
        </div>
        <span className="font-display text-lg font-semibold">ชิมลาง</span>
      </Link>
      <nav aria-label={t("nav_main")} className="flex flex-1 flex-col gap-1 text-sm">
        {items.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            onClick={onNavigate}
            className={({ isActive }) =>
              `flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left transition ${
                isActive
                  ? "bg-sidebar-accent font-medium text-foreground"
                  : "text-muted-foreground hover:bg-sidebar-accent/60"
              }`
            }
          >
            <item.icon className="h-4 w-4 shrink-0" />
            {item.label}
            {(item.badge ?? 0) > 0 && (
              <span className="ml-auto rounded-full bg-primary px-1.5 text-[10px] font-medium text-white">
                {item.badge}
              </span>
            )}
          </NavLink>
        ))}
      </nav>
      <LanguageControl />
    </>
  );
}

function RunRoute() {
  const navigate = useNavigate();
  const { runId } = useParams<{ runId: string }>();
  if (!runId) return <NotFound />;
  return (
    <RunDetail
      runId={runId}
      onBack={() => navigate(ROUTES.history)}
      onOpenRun={(nextRunId) => navigate(ROUTES.run(nextRunId))}
    />
  );
}

function GalleryRoute() {
  const navigate = useNavigate();
  const { token } = useParams<{ token: string }>();
  return (
    <Gallery
      shareToken={token}
      onBackToList={() => navigate(ROUTES.gallery)}
      onSelectToken={(nextToken) => navigate(ROUTES.galleryItem(nextToken))}
    />
  );
}

function ExperimentRoute() {
  const navigate = useNavigate();
  const { experimentId } = useParams<{ experimentId: string }>();
  return (
    <Experiments
      initialExperimentId={experimentId}
      onSelect={(id) => navigate(id ? ROUTES.experiment(id) : ROUTES.experiments)}
    />
  );
}

function NotFound() {
  const { t } = useLang();
  return (
    <section className="mx-auto max-w-xl rounded-2xl border border-border bg-card p-8 text-center">
      <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">404</p>
      <h1 className="mt-2 font-display text-2xl font-semibold">{t("route_not_found")}</h1>
      <Link to={ROUTES.home} className="mt-5 inline-flex rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white">
        {t("route_home")}
      </Link>
    </section>
  );
}

function Shell() {
  const { t } = useLang();
  const navigate = useNavigate();
  const location = useLocation();
  const [request, setRequest] = useState<RunRequest | null>(null);
  const [unread, setUnread] = useState(0);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const openButtonRef = useRef<HTMLButtonElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const mainRef = useRef<HTMLElement>(null);
  const previousPathRef = useRef(location.pathname);
  const [routeAnnouncement, setRouteAnnouncement] = useState("");

  const dismissDrawer = () => {
    setDrawerOpen(false);
    window.setTimeout(() => openButtonRef.current?.focus(), 0);
  };

  const refreshUnread = () =>
    fetchShellUnread()
      .then(setUnread)
      .catch(() => {});

  useEffect(() => {
    refreshUnread();
    const timer = window.setInterval(refreshUnread, 60_000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (previousPathRef.current === location.pathname) return;
    previousPathRef.current = location.pathname;
    setDrawerOpen(false);
    setRouteAnnouncement(t("route_changed"));
    window.requestAnimationFrame(() => mainRef.current?.focus());
  }, [location.pathname, t]);
  useEffect(() => {
    if (!drawerOpen) return;
    closeButtonRef.current?.focus();
    const handleDrawerKeys = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        dismissDrawer();
        return;
      }
      if (event.key !== "Tab") return;
      const dialog = closeButtonRef.current?.closest<HTMLElement>("[role='dialog']");
      const focusable = Array.from(
        dialog?.querySelectorAll<HTMLElement>(
          "a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])",
        ) ?? [],
      ).filter((element) => element.getClientRects().length > 0);
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", handleDrawerKeys);
    return () => window.removeEventListener("keydown", handleDrawerKeys);
  }, [drawerOpen]);

  return (
    <div className="min-h-screen bg-background md:flex">
      <button
        type="button"
        onClick={() => mainRef.current?.focus()}
        className="skip-link rounded-lg bg-foreground px-4 py-2 text-sm font-medium text-background"
      >
        {t("skip_main")}
      </button>
      <div className="sr-only" role="status" aria-live="polite" aria-atomic="true">
        {routeAnnouncement}
      </div>
      <aside className="hidden min-h-screen w-60 shrink-0 flex-col border-r border-border bg-sidebar p-4 md:flex">
        <Navigation unread={unread} />
      </aside>

      <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-border bg-background/95 px-4 backdrop-blur md:hidden">
        <Link to={ROUTES.home} className="flex items-center gap-2 font-display font-semibold">
          <Fish className="h-5 w-5 text-primary" /> ชิมลาง
        </Link>
        <button
          ref={openButtonRef}
          type="button"
          aria-label={t("nav_open")}
          aria-expanded={drawerOpen}
          aria-controls="mobile-navigation"
          onClick={() => setDrawerOpen(true)}
          className="grid h-11 w-11 place-items-center rounded-lg border border-border"
        >
          <Menu className="h-5 w-5" />
        </button>
      </header>

      {drawerOpen && (
        <div className="fixed inset-0 z-50 md:hidden" role="dialog" aria-modal="true" aria-label={t("nav_main")}>
          <button
            type="button"
            aria-label={t("nav_close")}
            className="absolute inset-0 bg-black/40"
            onClick={dismissDrawer}
          />
          <aside id="mobile-navigation" className="relative flex h-full w-[min(20rem,85vw)] flex-col bg-sidebar p-4 shadow-xl">
            <button
              ref={closeButtonRef}
              type="button"
              aria-label={t("nav_close")}
              onClick={dismissDrawer}
              className="absolute right-3 top-3 grid h-11 w-11 place-items-center rounded-lg border border-border"
            >
              <X className="h-5 w-5" />
            </button>
            <Navigation unread={unread} onNavigate={() => setDrawerOpen(false)} />
          </aside>
        </div>
      )}

      <main
        id="main-content"
        ref={mainRef}
        tabIndex={-1}
        className="min-w-0 flex-1 px-4 py-8 outline-none sm:px-8 lg:px-12"
      >
        <Suspense fallback={<div role="status" className="rounded-2xl border border-border bg-card p-8 text-sm text-muted-foreground">{t("loading_page")}</div>}>
          <Routes>
            <Route path={ROUTES.home} element={<Landing onStart={() => navigate(ROUTES.new)} />} />
            <Route
              path={ROUTES.new}
              element={
                <NewRun
                  onCompare={(nextRequest) => {
                    setRequest(nextRequest);
                    navigate(ROUTES.compare);
                  }}
                  onCreated={(runId) => navigate(ROUTES.run(runId))}
                />
              }
            />
            <Route path="/runs/:runId" element={<RunRoute />} />
            <Route path={ROUTES.compare} element={<Compare request={request} />} />
            <Route path={ROUTES.history} element={<Runs onOpen={(runId) => navigate(ROUTES.run(runId))} />} />
            <Route path={ROUTES.insights} element={<Insights />} />
            <Route path={ROUTES.experiments} element={<ExperimentRoute />} />
            <Route path="/experiments/:experimentId" element={<ExperimentRoute />} />
            <Route path={ROUTES.calibration} element={<Calibration />} />
            <Route path={ROUTES.watchlist} element={<Watchlist onChanged={refreshUnread} />} />
            <Route path={ROUTES.gallery} element={<GalleryRoute />} />
            <Route path="/gallery/:token" element={<GalleryRoute />} />
            <Route path={ROUTES.settings} element={<Settings />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </Suspense>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <LangProvider>
      <HashRouter>
        <Shell />
      </HashRouter>
    </LangProvider>
  );
}
