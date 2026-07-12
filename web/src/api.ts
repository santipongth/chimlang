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

export async function fetchDashboard(subject: string, agents = 100): Promise<DashboardData> {
  const r = await fetch(`/dashboard.json?subject=${encodeURIComponent(subject)}&agents=${agents}`);
  if (!r.ok) throw new Error((await r.json()).detail ?? `HTTP ${r.status}`);
  return r.json();
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

export async function fetchCompare(subject: string, agents = 100): Promise<CompareData> {
  const r = await fetch(`/compare.json?subject=${encodeURIComponent(subject)}&agents=${agents}`);
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
