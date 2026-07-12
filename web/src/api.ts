// ตัวช่วยเรียก API ของชิมลาง — type ตรงกับ response ฝั่ง FastAPI

export interface BriefLine {
  kind: "opportunity" | "risk";
  text: string;
}

export interface DashboardData {
  subject: string;
  brief: {
    lines: BriefLine[];
    fragility_index: number;
    confidence_label: string;
    headline_range: [number, number];
  };
  heatmap: { name: string; risk: number; band: string }[];
  scenarios: { name: string; belief_by_segment: Record<string, number> }[];
  voices: { private?: string; public?: string; segment?: string }[];
  voice_population_share: { segment: string; population_share: number }[];
  // PRD pipeline ขั้น 7 — key มีเสมอ (list ว่างได้)
  tipping_points: { scenario: string; round: number; before: number; after: number; delta: number }[];
}

export interface ImpactResult {
  segment: string;
  concern_baseline_range: [number, number];
  concern_after_response_range: [number, number];
  note: string;
  disclaimer: string;
}

export async function fetchDashboard(
  subject: string,
  agents = 100,
  packId?: number | null,
): Promise<DashboardData> {
  const pack = packId != null ? `&pack_id=${packId}` : "";
  const r = await fetch(
    `/dashboard.json?subject=${encodeURIComponent(subject)}&agents=${agents}${pack}`,
  );
  if (!r.ok) throw new Error((await r.json()).detail ?? `HTTP ${r.status}`);
  return r.json();
}

// ---- Engines + persistent runs (P6-M1/M2) ----

export interface EngineInfo {
  key: "fabric" | "debate";
  label_th: string;
  label_en: string;
  desc_th: string;
  desc_en: string;
  uses_llm: boolean;
  max_agents: number;
}

export async function fetchEngines(): Promise<EngineInfo[]> {
  const r = await fetch("/engines.json");
  if (!r.ok) throw new Error((await r.json()).detail ?? `HTTP ${r.status}`);
  return (await r.json()).engines;
}

export interface SourceInput {
  kind: "text" | "url" | "rss";
  label: string;
  url?: string;
  text?: string;
}

export interface CreateRunBody {
  engine: "fabric" | "debate";
  subject: string;
  domain: string;
  agents: number;
  rounds?: number;
  pack_id?: number | null;
  red_team?: boolean;
  sources?: SourceInput[];
  // เหตุการณ์จริง: ตั้งคำทำนายที่วัดผลได้เอง (ว่าง = ระบบตั้ง heuristic ให้)
  claim?: string;
  measurement?: string;
  due_days?: number;
}

export async function createRun(body: CreateRunBody): Promise<string> {
  const r = await fetch("/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error((await r.json()).detail ?? `HTTP ${r.status}`);
  return (await r.json()).run_id;
}

export interface SimRunSummary {
  run_id: string;
  created_at: string;
  engine: string;
  subject: string;
  domain: string;
  agents: number;
  rounds: number;
  status: "running" | "complete" | "error";
}

export async function fetchSimRuns(search = "", engine = ""): Promise<SimRunSummary[]> {
  const q = new URLSearchParams();
  if (search) q.set("search", search);
  if (engine) q.set("engine", engine);
  const r = await fetch(`/simruns.json?${q}`);
  if (!r.ok) throw new Error((await r.json()).detail ?? `HTTP ${r.status}`);
  return (await r.json()).runs;
}

export interface DebatePostItem {
  round_no: number;
  agent_idx: number;
  segment: string;
  content: string;
  stance: number;
  sentiment: number;
  failed: boolean;
}

export interface SimRunDetail extends SimRunSummary {
  seed: number;
  config: Record<string, any>;
  payload: Record<string, any> | null;
  error: string | null;
  posts: DebatePostItem[];
}

export async function fetchRunDetail(runId: string): Promise<SimRunDetail> {
  const r = await fetch(`/runs/${runId}.json`);
  if (!r.ok) throw new Error((await r.json()).detail ?? `HTTP ${r.status}`);
  return r.json();
}

export async function deleteRun(runId: string): Promise<void> {
  const r = await fetch(`/runs/${runId}`, { method: "DELETE" });
  if (!r.ok) throw new Error((await r.json()).detail ?? `HTTP ${r.status}`);
}

// ---- App settings (P6-M4) ----

export interface LlmProvider {
  key: string;
  label: string;
  base_url: string;
  needs_key: boolean;
  hint_th: string;
}

export interface AppSettings {
  default_engine: "fabric" | "debate";
  default_agents: number;
  default_rounds: number;
  default_domain: string;
  default_tab: string;
  webhook_configured: boolean;
  auth_enabled: boolean;
  caps: { fabric: number; debate: number };
  // LLM ปรับเองได้ (ADR-0006) — API key ไม่เคยมากับ response
  llm_provider: string;
  llm_base_url: string;
  llm_model_crowd: string;
  llm_model_analyst: string;
  llm_prices: Record<string, { input_usd_per_m: number; output_usd_per_m: number }>;
  llm: {
    providers: LlmProvider[];
    key_present: boolean;
    active_base_url: string;
    active_model_crowd: string;
    active_model_analyst: string;
    env_model_crowd: string;
    env_model_analyst: string;
  };
}

export async function fetchSettings(): Promise<AppSettings> {
  const r = await fetch("/settings.json");
  if (!r.ok) throw new Error((await r.json()).detail ?? `HTTP ${r.status}`);
  return r.json();
}

export async function saveSettings(patch: Partial<AppSettings>): Promise<void> {
  const r = await fetch("/settings.json", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!r.ok) throw new Error((await r.json()).detail ?? `HTTP ${r.status}`);
}

// ---- Persona packs (P5-M7) ----

export interface PackSegment {
  id: string;
  name: string;
  share: number;
  voice_activity: number;
  cultural_priors: Record<string, number>;
  channel_mix: Record<string, number>;
  traits: string[];
}

export interface PersonaPack {
  id: number;
  label: string;
  prompt: string;
  created_by: string;
  created_at: string;
  segments: PackSegment[];
}

export async function fetchPacks(): Promise<PersonaPack[]> {
  const r = await fetch("/personas/packs.json");
  if (!r.ok) throw new Error((await r.json()).detail ?? `HTTP ${r.status}`);
  return (await r.json()).packs;
}

export async function generatePack(label: string, prompt: string): Promise<PackSegment[]> {
  const r = await fetch("/personas/packs/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ label, prompt }),
  });
  if (!r.ok) throw new Error((await r.json()).detail ?? `HTTP ${r.status}`);
  return (await r.json()).segments;
}

export async function savePack(label: string, segments: PackSegment[], prompt: string): Promise<number> {
  const r = await fetch("/personas/packs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ label, segments, prompt }),
  });
  if (!r.ok) throw new Error((await r.json()).detail ?? `HTTP ${r.status}`);
  return (await r.json()).id;
}

export async function tryAsk(segment: PackSegment, question: string): Promise<string> {
  const r = await fetch("/personas/try-ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ segment, question }),
  });
  if (!r.ok) throw new Error((await r.json()).detail ?? `HTTP ${r.status}`);
  return (await r.json()).answer;
}

export async function deletePack(id: number): Promise<void> {
  const r = await fetch(`/personas/packs/${id}`, { method: "DELETE" });
  if (!r.ok) throw new Error((await r.json()).detail ?? `HTTP ${r.status}`);
}

export interface RunsData {
  runs: { run_id: string; started: string; predictions: number; exported: boolean }[];
  due: { prediction_id: number; claim: string; domain: string; due_date: string }[];
}

export async function fetchRuns(): Promise<RunsData> {
  const r = await fetch("/runs.json");
  if (!r.ok) throw new Error((await r.json()).detail ?? `HTTP ${r.status}`);
  return r.json();
}

// ---- Public gallery (P5-M8, ADR-0004) ----

export interface GalleryListItem {
  share_token: string;
  subject: string;
  agents: number;
  created_at: string;
  votes: { agree: number; disagree: number };
  watermark: { label: string; labels: string[]; shared_at: string; note: string };
  brief: DashboardData["brief"];
}

export interface GalleryDetail extends Omit<GalleryListItem, "brief"> {
  payload: DashboardData & Record<string, any>;
}

export async function fetchGallery(): Promise<GalleryListItem[]> {
  const r = await fetch("/gallery.json");
  if (!r.ok) throw new Error((await r.json()).detail ?? `HTTP ${r.status}`);
  return (await r.json()).items;
}

export async function fetchGalleryDetail(token: string): Promise<GalleryDetail> {
  const r = await fetch(`/gallery/${token}.json`);
  if (!r.ok) throw new Error((await r.json()).detail ?? `HTTP ${r.status}`);
  return r.json();
}

export async function shareToGallery(subject: string, agents: number): Promise<string> {
  const r = await fetch("/gallery/share", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ subject, agents }),
  });
  if (!r.ok) throw new Error((await r.json()).detail ?? `HTTP ${r.status}`);
  return (await r.json()).share_token;
}

export async function voteGallery(
  token: string,
  vote: "agree" | "disagree",
): Promise<{ agree: number; disagree: number }> {
  const r = await fetch(`/gallery/${token}/vote`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ vote }),
  });
  if (!r.ok) throw new Error((await r.json()).detail ?? `HTTP ${r.status}`);
  return (await r.json()).votes;
}

// ---- Knowledge graph viz + insights (P5-M6) ----

export interface GraphNode {
  name: string;
  kind: string;
  degree: number;
  sources: number;
}

export interface GraphSummary {
  nodes: GraphNode[];
  edges: { from: string; to: string; relation: string }[];
  hubs: string[];
  kinds: string[];
  note: string;
}

export async function fetchGraphSummary(): Promise<GraphSummary> {
  const r = await fetch("/graph/summary.json");
  if (!r.ok) throw new Error((await r.json()).detail ?? `HTTP ${r.status}`);
  return r.json();
}

export interface InsightsData {
  total_runs: number;
  exports: number;
  runs_per_day: { day: string; runs: number }[];
  predictions_by_domain: { domain: string; total: number; resolved: number }[];
}

export async function fetchInsights(): Promise<InsightsData> {
  const r = await fetch("/insights.json");
  if (!r.ok) throw new Error((await r.json()).detail ?? `HTTP ${r.status}`);
  return r.json();
}

// ---- Watchlist + alerts (P5-M5) ----

export interface WatchlistItem {
  id: number;
  label: string;
  subject: string;
  agents: number;
  cadence: "daily" | "weekly";
  active: boolean;
  last_run_at: string | null;
  last_delta: number | null;
}

export interface AlertItem {
  id: number;
  ts: string;
  watchlist_id: number | null;
  kind: string;
  payload: Record<string, any>;
  read: boolean;
}

export interface WatchlistData {
  items: WatchlistItem[];
  alerts: AlertItem[];
  unread: number;
  webhook_configured: boolean;
}

export async function fetchWatchlists(): Promise<WatchlistData> {
  const r = await fetch("/watchlists.json");
  if (!r.ok) throw new Error((await r.json()).detail ?? `HTTP ${r.status}`);
  return r.json();
}

export async function createWatchlist(body: {
  label: string;
  subject: string;
  agents: number;
  cadence: "daily" | "weekly";
}): Promise<void> {
  const r = await fetch("/watchlists", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error((await r.json()).detail ?? `HTTP ${r.status}`);
}

export async function toggleWatchlist(id: number, active: boolean): Promise<void> {
  const r = await fetch(`/watchlists/${id}/toggle?active=${active}`, { method: "POST" });
  if (!r.ok) throw new Error((await r.json()).detail ?? `HTTP ${r.status}`);
}

export async function runWatchlistNow(id: number): Promise<{ alerts_created: any[] }> {
  const r = await fetch(`/watchlists/${id}/run`, { method: "POST" });
  if (!r.ok) throw new Error((await r.json()).detail ?? `HTTP ${r.status}`);
  return r.json();
}

export async function markAlertsRead(id?: number): Promise<void> {
  await fetch("/alerts/read", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(id == null ? { all: true } : { id }),
  });
}

// ---- Compare baseline vs +Red Team (P5-M4) ----

export interface CompareSide {
  mean_delta: number;
  ci95: [number, number];
  conclusion: string;
  belief_by_segment: Record<string, number>;
}

export interface CompareData {
  subject: string;
  seeds: number[];
  rounds: number;
  agents: number;
  baseline: CompareSide;
  red_team: CompareSide & { roster: { agent_id: string; traits: string[] }[]; segment_label: string };
  delta_of_delta: number;
  robust: boolean;
  note: string;
}

export async function fetchCompare(
  subject: string,
  agents = 100,
  packId?: number | null,
): Promise<CompareData> {
  const pack = packId != null ? `&pack_id=${packId}` : "";
  const r = await fetch(
    `/compare.json?subject=${encodeURIComponent(subject)}&agents=${agents}${pack}`,
  );
  if (!r.ok) throw new Error((await r.json()).detail ?? `HTTP ${r.status}`);
  return r.json();
}

// ---- Calibration (P5-M3) ----

export interface CalibrationItem {
  prediction_id: number;
  run_id: string;
  claim: string;
  domain: string;
  confidence: number;
  outcome_value: number; // 1 | 0.5 | 0
  brier: number;
  resolved_at: string;
  note: string;
}

export interface CalibrationData {
  overall_brier: number | null;
  resolved_total: number;
  domains: { domain: string; n: number; brier: number; happened: number; partial: number; didnt: number }[];
  trend: { t: number; brier: number; n: number }[];
  items: CalibrationItem[];
  due: { prediction_id: number; claim: string; domain: string; confidence: number; due_date: string }[];
  upcoming: { prediction_id: number; claim: string; domain: string; confidence: number; due_date: string }[];
}

export async function fetchCalibration(): Promise<CalibrationData> {
  const r = await fetch("/calibration.json");
  if (!r.ok) throw new Error((await r.json()).detail ?? `HTTP ${r.status}`);
  return r.json();
}

export async function resolvePrediction(
  id: number,
  outcome: "true" | "partial" | "false",
  note: string,
): Promise<{ brier: number }> {
  const r = await fetch(`/predictions/${id}/resolve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ outcome, note }),
  });
  if (!r.ok) throw new Error((await r.json()).detail ?? `HTTP ${r.status}`);
  return r.json();
}

export async function fetchImpact(body: Record<string, string | number>): Promise<ImpactResult> {
  const r = await fetch("/citizen/impact.json", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error((await r.json()).detail ?? `HTTP ${r.status}`);
  return r.json();
}

export async function sendFeedback(segment_id: string, stance: string): Promise<string> {
  const r = await fetch("/citizen/feedback.json", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ segment_id, stance }),
  });
  if (!r.ok) throw new Error((await r.json()).detail ?? `HTTP ${r.status}`);
  return (await r.json()).k_anonymity_note;
}

// ตัวเลือกปิดต้องตรงกับ simulation/citizen.py (CIT-01: ไม่มี free text)
export const CHOICES = {
  income_band: ["ต่ำกว่า 15k", "15k-30k", "30k-60k", "60k ขึ้นไป"],
  region: ["ในเมืองชั้นใน", "แนวรถไฟฟ้า", "ชานเมือง", "นอกแนวขนส่งสาธารณะ"],
  commute: ["รถไฟฟ้า/รถเมล์", "รถยนต์ส่วนตัว", "มอเตอร์ไซค์", "เดิน/ใกล้ที่ทำงาน"],
  occupation: [
    "พนักงานออฟฟิศ",
    "ค้าขาย/กิจการเล็ก",
    "ไรเดอร์/ขนส่ง",
    "เกษียณ/ดูแลบ้าน",
    "นักเรียนนักศึกษา",
  ],
  age_band: ["18-30", "31-45", "46-60", "60 ขึ้นไป"],
} as const;

export const STANCES = ["เห็นด้วย", "ไม่เห็นด้วย", "กังวลแต่ยังไม่ตัดสินใจ"] as const;

export const pct = (x: number) => `${Math.round(x * 100)}%`;
