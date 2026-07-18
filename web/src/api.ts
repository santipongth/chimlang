// ตัวช่วยเรียก API ของชิมลาง — type ตรงกับ response ฝั่ง FastAPI

import { apiClient } from "./openapi-client";
import type { components } from "./openapi.generated";

function openApiError(error: unknown, status: number): Error {
  if (error && typeof error === "object" && "detail" in error) {
    return new Error(String((error as { detail: unknown }).detail));
  }
  return new Error(`HTTP ${status}`);
}

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
  universe_estimates: {
    universe_id: number;
    estimate: number;
    ci95: [number, number];
    conclusion: string;
  }[];
  // PRD pipeline ขั้น 7 — key มีเสมอ (list ว่างได้)
  tipping_points: { scenario: string; round: number; before: number; after: number; delta: number }[];
}

export async function fetchDashboard(
  subject: string,
  agents = 100,
  packId?: number | null,
): Promise<DashboardData> {
  const { data, error, response } = await apiClient.GET("/dashboard.json", {
    params: { query: { subject, agents, pack_id: packId ?? undefined } },
  });
  if (!response.ok || !data) throw openApiError(error, response.status);
  return data as unknown as DashboardData;
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
  const { data, error, response } = await apiClient.GET("/engines.json");
  if (!response.ok || !data) throw openApiError(error, response.status);
  return (data as unknown as { engines: EngineInfo[] }).engines;
}

export interface RunReadiness {
  can_run: boolean;
  checks: { id: string; label: string; status: "pass" | "warn" | "block"; detail: string }[];
  cost: {
    estimated_usd: number;
    currency?: string;
    calls?: number;
    run_cap_usd?: number;
    note?: string;
    error?: string;
  };
}

export interface CreateRunBody {
  parent_run_id?: string;
  population_set_id?: string;
}

export async function fetchRunReadiness(body: CreateRunBody): Promise<RunReadiness> {
  const { data, error, response } = await apiClient.POST("/runs/readiness", {
    body: toRunRequest(body),
  });
  if (!response.ok || !data) throw openApiError(error, response.status);
  return data as unknown as RunReadiness;
}

export interface SourceInput {
  kind: "text" | "url"; // ADR-0027: ถอด "rss" — แถวประวัติ kind='rss' อ่านได้ผ่าน run payload เท่านั้น
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
  probability?: number | null;
  seed?: number | null;
  views?: string[]; // มุมมองที่จะเปิดใช้ (P6-M6)
  live_news?: boolean; // โต๊ะข่าวสด (P7, debate เท่านั้น)
}

function toRunRequest(body: CreateRunBody) {
  return {
    engine: body.engine,
    subject: body.subject,
    domain: body.domain,
    agents: body.agents,
    rounds: body.rounds ?? 3,
    pack_id: body.pack_id ?? null,
    red_team: body.red_team ?? false,
    sources: (body.sources ?? []).map((source) => ({ ...source })),
    claim: body.claim ?? "",
    measurement: body.measurement ?? "",
    due_days: body.due_days ?? 30,
    probability: body.probability ?? null,
    seed: body.seed ?? null,
    views: body.views ?? [],
    live_news: body.live_news ?? false,
    parent_run_id: body.parent_run_id ?? "",
    experiment_id: "",
    population_set_id: body.population_set_id ?? "",
    input_mode: "latest" as const,
    source_run_id: "",
  };
}

// พูลของ persona (P6-M6)
export interface PoolSegment {
  id: string;
  name: string;
  share: number;
  voice_activity?: number;
  cultural_priors: Record<string, number>;
  channel_mix: Record<string, number>;
  traits: string[];
}

export interface PackLimits {
  min_segments: number;
  max_segments: number;
}

// fallback เมื่อ backend รุ่นเก่ายังไม่ส่ง limits — ค่าต้องตรง MIN/MAX_SEGMENTS ฝั่ง Python (ADR-0009)
export const FALLBACK_PACK_LIMITS: PackLimits = { min_segments: 2, max_segments: 12 };

export async function fetchPool(
  packId?: number | null,
): Promise<{ source: string; segments: PoolSegment[]; limits?: PackLimits }> {
  const { data, error, response } = await apiClient.GET("/personas/pool.json", {
    params: { query: { pack_id: packId ?? undefined } },
  });
  if (!response.ok || !data) throw openApiError(error, response.status);
  return data as unknown as { source: string; segments: PoolSegment[]; limits?: PackLimits };
}

export async function createRun(body: CreateRunBody): Promise<string> {
  const { data, error, response } = await apiClient.POST("/runs", {
    body: toRunRequest(body),
  });
  if (!response.ok || !data) throw openApiError(error, response.status);
  return String((data as { run_id: string }).run_id);
}

export interface RunJobResult {
  run_id: string;
  engine: string;
  agents: number;
}

export interface RunJobStatus {
  job_id: string;
  run_id?: string;
  status: string;
  reused?: boolean;
  status_url?: string;
  events_url?: string;
  manifest_url?: string;
  snapshot_url?: string;
  progress?: number;
  progress_message?: string;
  result?: RunJobResult;
  error?: string;
}

export type AsyncRunAccepted = components["schemas"]["AsyncRunAccepted"];

export async function createRunAsync(body: CreateRunBody, idempotencyKey: string): Promise<AsyncRunAccepted> {
  const { data, error, response } = await apiClient.POST("/runs/async", {
    params: { header: { "Idempotency-Key": idempotencyKey } },
    body: toRunRequest(body),
  });
  if (!response.ok || !data) throw openApiError(error, response.status);
  return data;
}

export async function fetchRunJob(jobId: string): Promise<RunJobStatus> {
  const { data, error, response } = await apiClient.GET("/run-jobs/{job_id}", {
    params: { path: { job_id: jobId } },
  });
  if (!response.ok || !data) throw openApiError(error, response.status);
  return data as unknown as RunJobStatus;
}

export interface SimRunSummary {
  run_id: string;
  created_at: string;
  engine: string;
  subject: string;
  domain: string;
  agents: number;
  rounds: number;
  status: "queued" | "running" | "complete" | "error" | "canceled";
  job_id?: string;
  queued_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  progress?: number;
  progress_message?: string;
}

export async function fetchSimRuns(search = "", engine = "", status = ""): Promise<SimRunSummary[]> {
  const { data, error, response } = await apiClient.GET("/simruns.json", {
    params: { query: { search, engine, status } },
  });
  if (!response.ok || !data) throw openApiError(error, response.status);
  return (data as unknown as { runs: SimRunSummary[] }).runs;
}

export interface DebatePostItem {
  round_no: number;
  agent_idx: number;
  segment: string;
  content: string;
  stance: number;
  sentiment: number;
  failed: boolean;
  failure_reason?: string;
  parser_mode?: string;
  move_id?: string;
  move_type?: "claim" | "evidence" | "counterclaim" | "concession" | "question";
  parent_move_id?: string;
  evidence_refs?: string[];
}

export interface EvidenceSourceItem {
  label?: string;
  title?: string;
  provider?: string;
  kind?: string;
  status?: string;
  error?: string;
  url?: string;
  chunks?: number;
  fetched_at?: string;
  pii_redactions?: Record<string, number>;
  content?: string;
  channel_tags?: Record<string, number>;
}

export interface EvidenceMatch extends EvidenceSourceItem {
  source_label: string;
  seq: number;
  score: number;
  quality_score: number;
  citation_spans: { start: number; end: number; text: string; match: string }[];
  requested_mode: string;
  note: string;
}

export interface DebateRunPayload {
  result_kind?: "simulation_finding" | "prediction";
  synthesis: {
    status?: "analyst_failed";
    summary: string;
    confidence: number;
    distribution: { bucket: string; pct: number }[];
    key_drivers: string[];
    risks: string[];
    failure_reason?: string;
    analyst_attempts?: number;
    parser_mode?: string;
    judge?: {
      verdict: "pass" | "warn" | "fail";
      citation_assessment: string;
      contradiction_assessment: string;
      schema_assessment: string;
    };
  };
  metrics: {
    per_round_avg_stance: number[];
    final_dispersion?: number;
    tipping_points?: { round: number; before: number; after: number; delta: number }[];
    posts_ok?: number;
    posts_failed?: number;
  };
  protocol?: Record<string, unknown>;
  cost_usd?: number;
  red_team?: boolean;
  sources?: EvidenceSourceItem[];
  evidence_matches?: EvidenceMatch[];
  context_used?: number;
  news?: { enabled: boolean; items: EvidenceSourceItem[]; refreshed_at?: string };
}

export interface FabricRunPayload extends DashboardData {
  result_kind?: "simulation_finding" | "prediction";
  cost_usd?: number;
}

export type RunPayload = DebateRunPayload | FabricRunPayload;

interface SimRunDetailBase extends Omit<SimRunSummary, "engine"> {
  share_token?: string | null;
  seed: number;
  config: Record<string, unknown>;
  error: string | null;
  posts: DebatePostItem[];
  result_kind?: "simulation_finding" | "prediction";
  findings?: SimulationFinding[];
  predictions?: PredictionContract[];
  synthesis_revisions?: SynthesisRevision[];
  parent_run_id?: string;
  events?: {
    created_at: string;
    event_type: string;
    actor: string;
    message: string;
    payload: Record<string, unknown>;
  }[];
  trust_scorecard?: {
    score: number;
    band: string;
    checks: {
      id: string;
      label: string;
      status: "pass" | "warn" | "block";
      detail: string;
      weight?: number;
    }[];
  };
  manifest?: {
    schema_version: number;
    complete: boolean;
    reproducibility: string;
    manifest_hash?: string;
    config_hash?: string;
  };
}

export type SimRunDetail =
  | (SimRunDetailBase & { engine: "fabric"; payload: FabricRunPayload | null })
  | (SimRunDetailBase & { engine: "debate"; payload: DebateRunPayload | null });

export interface SimulationFinding {
  finding_id: number;
  created_at: string;
  summary: string;
  metrics: Record<string, unknown>;
  provenance: Record<string, unknown>;
  model_version: string;
}

export interface PredictionContract {
  prediction_id: number;
  claim: string;
  probability: number;
  measurement: string;
  due_date: string;
  domain: string;
  source_kind: string;
  forecast_type: "binary";
  resolution: null | {
    outcome: boolean;
    observed_at: string;
    evidence_url: string;
    evidence_name: string;
    note: string;
    brier: number;
  };
}

export interface SynthesisRevision {
  id: number;
  created_at: string;
  kind: "analyst" | "mechanical";
  synthesis: Record<string, unknown>;
  metrics: Record<string, unknown>;
  parser_mode: string;
  cost_usd: number;
}

export async function fetchRunDetail(runId: string): Promise<SimRunDetail> {
  const { data, error, response } = await apiClient.GET("/runs/{run_id}.json", {
    params: { path: { run_id: runId } },
  });
  if (!response.ok || !data) throw openApiError(error, response.status);
  return data as unknown as SimRunDetail;
}

export async function deleteRun(runId: string): Promise<void> {
  const { error, response } = await apiClient.DELETE("/runs/{run_id}", {
    params: { path: { run_id: runId } },
  });
  if (!response.ok) throw openApiError(error, response.status);
}

export interface ValidationReport {
  parent_run_id: string;
  status: string;
  completed: number;
  failure_rate: number;
  sign_agreement: number | null;
  stance_range: [number, number] | null;
  between_run_dispersion: number;
  claim_overlap: number | null;
  agent_failure_rate: number;
  total_cost_usd: number;
  children: {
    run_id: string;
    seed: number;
    status: string;
    error: string | null;
    value: number | null;
  }[];
  note: string;
}

// POST คืน ack ว่า queue ลูก 3 seed แล้ว (หรือรายงานเดิมถ้ามีอยู่แล้ว) — ไม่ใช่ ValidationReport เสมอ
export async function validateRun(runId: string): Promise<{ parent_run_id: string; status: string }> {
  const { data, error, response } = await apiClient.POST("/runs/{run_id}/validate", {
    params: { path: { run_id: runId } },
  });
  if (!response.ok || !data) throw openApiError(error, response.status);
  return data as unknown as { parent_run_id: string; status: string };
}

export async function fetchValidation(runId: string): Promise<ValidationReport> {
  const { data, error, response } = await apiClient.GET("/runs/{run_id}/validation", {
    params: { path: { run_id: runId } },
  });
  if (!response.ok || !data) throw openApiError(error, response.status);
  return data as unknown as ValidationReport;
}

export async function cancelRun(runId: string): Promise<void> {
  const { error, response } = await apiClient.POST("/runs/{run_id}/cancel", {
    params: { path: { run_id: runId } },
  });
  if (!response.ok) throw openApiError(error, response.status);
}

export async function rerunRun(
  runId: string,
  inputMode: "frozen" | "latest",
  idempotencyKey: string,
): Promise<AsyncRunAccepted> {
  const { data, error, response } = await apiClient.POST("/runs/{run_id}/rerun", {
    params: {
      path: { run_id: runId },
      header: { "Idempotency-Key": idempotencyKey },
    },
    body: { input_mode: inputMode },
  });
  if (!response.ok || !data) throw openApiError(error, response.status);
  return data;
}

export async function retryRun(runId: string): Promise<RunJobStatus> {
  const { data, error, response } = await apiClient.POST("/runs/{run_id}/retry", {
    params: { path: { run_id: runId } },
  });
  if (!response.ok || !data) throw openApiError(error, response.status);
  return data as unknown as RunJobStatus;
}

export interface RunMetrics {
  by_status: Record<string, { count: number; avg_runtime_s: number }>;
  avg_queue_wait_s: number;
  avg_runtime_s: number;
  errors_24h: number;
  sources_by_status: Record<string, number>;
  news_by_status: Record<string, number>;
  recent: {
    run_id: string;
    created_at: string;
    engine: string;
    status: string;
    progress: number;
    progress_message: string;
  }[];
  runs_24h: { hour: string; status: string; count: number }[];
  spent_this_month: number;
}

export async function fetchRunMetrics(): Promise<RunMetrics> {
  const { data, error, response } = await apiClient.GET("/run-metrics.json");
  if (!response.ok || !data) throw openApiError(error, response.status);
  return data as unknown as RunMetrics;
}

// ---- App settings (P6-M4) ----

export interface LlmProvider {
  key: string;
  label: string;
  base_url: string;
  needs_key: boolean;
  hint_th: string;
  hint_en?: string; // เพิ่ม 18 ก.ค. 2026 — โหมดอังกฤษต้องไม่โชว์ hint ไทย (fallback hint_th)
}

export interface AppSettings {
  default_engine: "fabric" | "debate";
  default_agents: number;
  default_rounds: number;
  default_domain: string;
  default_tab: string;
  auth_enabled: boolean;
  caps: { fabric: number; debate: number };
  // LLM ปรับเองได้ (ADR-0006) — API key ไม่เคยมากับ response
  llm_provider: string;
  llm_base_url: string;
  llm_model_crowd: string;
  llm_model_analyst: string;
  llm_synthesis_max_tokens?: number;
  llm_prices: Record<string, { input_usd_per_m: number; output_usd_per_m: number }>;
  run_budget_usd_cap: number;
  monthly_budget_usd_cap: number;
  llm: {
    providers: LlmProvider[];
    key_present: boolean;
    key_masked: string;
    key_source: "db" | "env" | "none";
    master_key_present: boolean;
    active_base_url: string;
    active_model_crowd: string;
    active_model_analyst: string;
    env_model_crowd: string;
    env_model_analyst: string;
    yaml_prices: Record<string, { input_usd_per_m: number; output_usd_per_m: number }>;
  };
  budget: {
    run_cap_effective: number;
    monthly_cap_effective: number;
    spent_this_month: number;
    reserved_this_month: number;
    available_this_month: number;
    env_run_cap: number;
    env_monthly_cap: number;
  };
  news_cache_ttl_hours?: number;
  news: {
    cache_ttl_hours?: number;
    tavily_present: boolean;
    tavily_masked: string;
    tavily_source: "db" | "env" | "none";
  };
}

export interface ProductPolicyItem {
  key: "pricing_metering" | "source_strategy" | "election_eligibility" | "semantic_memory";
  status: string;
  active_default: string;
  rationale: string;
  change_gate: string;
}

export interface ProductPolicy {
  version: string;
  billing_enabled: boolean;
  repository_public: boolean;
  semantic_memory_enabled: boolean;
  items: ProductPolicyItem[];
  note: string;
}

export async function fetchProductPolicy(): Promise<ProductPolicy> {
  const { data, error, response } = await apiClient.GET("/product-policy.json");
  if (!response.ok || !data) throw openApiError(error, response.status);
  return data as unknown as ProductPolicy;
}

export async function saveTavilyKey(apiKey: string): Promise<void> {
  const { error, response } = await apiClient.PUT("/settings/tavily-key", {
    body: { api_key: apiKey },
  });
  if (!response.ok) throw openApiError(error, response.status);
}

export async function saveLlmKey(apiKey: string): Promise<void> {
  const { error, response } = await apiClient.PUT("/settings/llm-key", {
    body: { api_key: apiKey },
  });
  if (!response.ok) throw openApiError(error, response.status);
}

export async function fetchSettings(): Promise<AppSettings> {
  const { data, error, response } = await apiClient.GET("/settings.json");
  if (!response.ok || !data) throw openApiError(error, response.status);
  return data as unknown as AppSettings;
}

export interface DeepHealth {
  status: string;
  components: Record<string, string>;
}

export async function fetchDeepHealth(): Promise<DeepHealth> {
  const { data, error, response } = await apiClient.GET("/health/deep");
  if (!response.ok || !data) throw openApiError(error, response.status);
  return data as unknown as DeepHealth;
}

export async function saveSettings(patch: Partial<AppSettings>): Promise<AppSettings> {
  const { data, error, response } = await apiClient.PUT("/settings.json", {
    body: patch,
  });
  if (!response.ok || !data) throw openApiError(error, response.status);
  return data as unknown as AppSettings;
}

export interface ObservabilityData {
  window_hours: number;
  providers: {
    provider: string;
    operation: string;
    calls: number;
    successes: number;
    success_rate: number;
    avg_latency_ms: number;
    cost_usd: number;
    last_call_at: string | null;
  }[];
  failure_taxonomy: { reason: string; count: number }[];
  queue: { queued: number; running: number; errors: number; avg_latency_seconds: number };
  pii_policy: string;
}

export async function fetchObservability(hours = 24): Promise<ObservabilityData> {
  const { data, error, response } = await apiClient.GET("/observability.json", {
    params: { query: { hours } },
  });
  if (!response.ok || !data) throw openApiError(error, response.status);
  return data as unknown as ObservabilityData;
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
  const { data, error, response } = await apiClient.GET("/personas/packs.json");
  if (!response.ok || !data) throw openApiError(error, response.status);
  return (data as unknown as { packs: PersonaPack[] }).packs;
}

export async function generatePack(label: string, prompt: string): Promise<PackSegment[]> {
  const { data, error, response } = await apiClient.POST("/personas/packs/generate", {
    body: { label, prompt },
  });
  if (!response.ok || !data) throw openApiError(error, response.status);
  return (data as unknown as { segments: PackSegment[] }).segments;
}

export async function savePack(label: string, segments: PackSegment[], prompt: string): Promise<number> {
  const { data, error, response } = await apiClient.POST("/personas/packs", {
    body: { label, segments: segments.map((segment) => ({ ...segment })), prompt },
  });
  if (!response.ok || !data) throw openApiError(error, response.status);
  return Number((data as { id: number }).id);
}

export async function updatePack(
  id: number,
  label: string,
  segments: PackSegment[],
  prompt: string,
): Promise<void> {
  const { error, response } = await apiClient.PUT("/personas/packs/{pack_id}", {
    params: { path: { pack_id: id } },
    body: { label, segments: segments.map((segment) => ({ ...segment })), prompt },
  });
  if (!response.ok) throw openApiError(error, response.status);
}

export async function tryAsk(segment: PackSegment, question: string): Promise<string> {
  const { data, error, response } = await apiClient.POST("/personas/try-ask", {
    body: { segment: { ...segment }, question },
  });
  if (!response.ok || !data) throw openApiError(error, response.status);
  return String((data as { answer: string }).answer);
}

export async function deletePack(id: number): Promise<void> {
  const { error, response } = await apiClient.DELETE("/personas/packs/{pack_id}", {
    params: { path: { pack_id: id } },
  });
  if (!response.ok) throw openApiError(error, response.status);
}

export interface RunsData {
  runs: { run_id: string; started: string; predictions: number; exported: boolean }[];
  due: { prediction_id: number; claim: string; domain: string; due_date: string }[];
}

export async function fetchRuns(): Promise<RunsData> {
  const { data, error, response } = await apiClient.GET("/runs.json");
  if (!response.ok || !data) throw openApiError(error, response.status);
  return data as unknown as RunsData;
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
  payload: FabricRunPayload;
}

export async function fetchGallery(): Promise<GalleryListItem[]> {
  const { data, error, response } = await apiClient.GET("/gallery.json");
  if (!response.ok || !data) throw openApiError(error, response.status);
  return (data as unknown as { items: GalleryListItem[] }).items;
}

export async function fetchGalleryDetail(token: string): Promise<GalleryDetail> {
  const { data, error, response } = await apiClient.GET("/gallery/{token}.json", {
    params: { path: { token } },
  });
  if (!response.ok || !data) throw openApiError(error, response.status);
  return data as unknown as GalleryDetail;
}

export async function shareRun(runId: string): Promise<string> {
  const { data, error, response } = await apiClient.POST("/runs/{run_id}/share", {
    params: { path: { run_id: runId } },
  });
  if (!response.ok || !data) throw openApiError(error, response.status);
  return String((data as { share_token: string }).share_token);
}

export async function unshareRun(runId: string): Promise<void> {
  const { error, response } = await apiClient.DELETE("/runs/{run_id}/share", {
    params: { path: { run_id: runId } },
  });
  if (!response.ok) throw openApiError(error, response.status);
}

export async function voteGallery(
  token: string,
  vote: "agree" | "disagree",
): Promise<{ agree: number; disagree: number }> {
  const { data, error, response } = await apiClient.POST("/gallery/{token}/vote", {
    params: { path: { token } },
    body: { vote },
  });
  if (!response.ok || !data) throw openApiError(error, response.status);
  return (data as unknown as { votes: { agree: number; disagree: number } }).votes;
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
  const { data, error, response } = await apiClient.GET("/graph/summary.json");
  if (!response.ok || !data) throw openApiError(error, response.status);
  return data as unknown as GraphSummary;
}

export interface InsightsData {
  total_runs: number;
  exports: number;
  runs_per_day: { day: string; runs: number }[];
  predictions_by_domain: { domain: string; total: number; resolved: number }[];
}

export async function fetchInsights(): Promise<InsightsData> {
  const { data, error, response } = await apiClient.GET("/insights.json");
  if (!response.ok || !data) throw openApiError(error, response.status);
  return data as unknown as InsightsData;
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
  const { data, error, response } = await apiClient.GET("/compare.json", {
    params: { query: { subject, agents, pack_id: packId ?? undefined } },
  });
  if (!response.ok || !data) throw openApiError(error, response.status);
  return data as unknown as CompareData;
}

// ---- Experiment workspace (P8-M6) ----

export interface ExperimentSummary {
  experiment_id: string;
  created_at: string;
  name: string;
  kind: "sweep" | "comparison";
  dimensions: Record<string, unknown[]>;
  run_count: number;
}

export interface ExperimentRun {
  run_id: string;
  variant: Record<string, unknown>;
  engine: "fabric" | "debate" | "unknown";
  status: string;
  value: number | null;
  cost_usd: number;
  error: string | null;
}

export interface SensitivityDimension {
  groups: { value: string; n: number; mean: number; min: number; max: number }[];
  sensitivity_range: number | null;
}

export interface ExperimentDetail {
  workspace: ExperimentSummary & {
    base_config: Record<string, unknown>;
    created_by: string;
    members: { run_id: string; variant: Record<string, unknown> }[];
  };
  analysis: {
    runs: ExperimentRun[];
    completed: number;
    failed: number;
    total_cost_usd: number;
    dimensions: Record<string, SensitivityDimension>;
    ranked_sensitivity: { parameter: string; sensitivity_range: number }[];
    public_votes_used: false;
    note: string;
  };
}

export async function fetchExperiments(): Promise<ExperimentSummary[]> {
  const { data, error, response } = await apiClient.GET("/experiments");
  if (!response.ok || !data) throw openApiError(error, response.status);
  return (data as unknown as { experiments: ExperimentSummary[] }).experiments;
}

export async function fetchExperiment(experimentId: string): Promise<ExperimentDetail> {
  const { data, error, response } = await apiClient.GET("/experiments/{experiment_id}", {
    params: { path: { experiment_id: experimentId } },
  });
  if (!response.ok || !data) throw openApiError(error, response.status);
  return data as unknown as ExperimentDetail;
}

export async function createExperimentComparison(name: string, runIds: string[]): Promise<ExperimentDetail> {
  const { data, error, response } = await apiClient.POST("/experiments/compare", {
    body: { name, run_ids: runIds },
  });
  if (!response.ok || !data) throw openApiError(error, response.status);
  return data as unknown as ExperimentDetail;
}

export interface SweepCreated {
  experiment_id: string;
  budget: { variants: number; estimated_usd: number; monthly_spent_usd?: number; monthly_cap_usd?: number };
  jobs: { run_id: string; job_id: string; variant: Record<string, unknown> }[];
  public_votes_used: false;
}

export async function createExperimentSweep(
  name: string,
  baseRun: CreateRunBody,
  parameters: Record<string, unknown[]>,
): Promise<SweepCreated> {
  const { data, error, response } = await apiClient.POST("/experiments/sweep", {
    body: {
      name,
      base_run: toRunRequest(baseRun),
      parameters,
    },
  });
  if (!response.ok || !data) throw openApiError(error, response.status);
  return data as unknown as SweepCreated;
}

export const pct = (x: number) => `${Math.round(x * 100)}%`;
