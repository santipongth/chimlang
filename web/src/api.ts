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
