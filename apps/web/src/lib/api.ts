// API client + TypeScript mirror of the Dataset Manifest contract
// (source of truth: apps/api/app/models/manifest.py)

import type { PersistedInvestigationState } from "@/lib/investigation-context";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8400";

export type SemanticRole =
  | "id" | "timestamp" | "date" | "latitude" | "longitude"
  | "admin_area_1" | "admin_area_2" | "admin_area_3"
  | "category" | "subcategory" | "status" | "person_name" | "phone"
  | "address" | "age" | "gender" | "measure" | "money" | "free_text"
  | "boolean" | "foreign_key" | "identifier" | "other";

export interface ColumnSpec {
  name: string;
  dtype: string;
  semantic_role: SemanticRole;
  label: string;
  stats: {
    count: number;
    null_fraction: number;
    distinct_count: number;
    min?: unknown;
    max?: unknown;
    mean?: number;
    top_values: { value: unknown; count: number }[];
  };
}

export interface TableSpec {
  name: string;
  row_count: number;
  columns: ColumnSpec[];
  is_primary: boolean;
}

export interface KpiSpec {
  id: string;
  title: string;
  table: string;
  agg: string;
  column?: string | null;
  filters: Record<string, unknown>;
  compare_window?: string | null;
}

export interface ChartSpec {
  id: string;
  title: string;
  kind: "timeseries" | "bar" | "pie" | "map_heat" | "map_points" | "table" | "network";
  table: string;
  dimension?: string | null;
  measure_agg: string;
  measure_column?: string | null;
  time_grain?: string | null;
}

export interface Manifest {
  id: string;
  name: string;
  domain_pack: string;
  created_at: string;
  tables: TableSpec[];
  relations: { from_table: string; from_column: string; to_table: string; to_column: string }[];
  entities: { name: string; table: string; id_column: string; label_column?: string; link_columns: string[] }[];
  kpis: KpiSpec[];
  charts: ChartSpec[];
  notes: string;
}

export interface QueryResult {
  columns: string[];
  rows: (string | number | null)[][];
  computed_at?: string;
  cached?: boolean;
}

export function primaryTable(m: Manifest): TableSpec {
  return m.tables.find((t) => t.is_primary) ?? m.tables[0];
}

export function byRole(t: TableSpec, role: SemanticRole): ColumnSpec | undefined {
  return t.columns.find((c) => c.semantic_role === role);
}

async function check(r: Response) {
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
  return r;
}

export async function getDatasets() {
  const r = await check(await fetch(`${API_BASE}/api/datasets`));
  return r.json() as Promise<
    { id: string; name: string; domain_pack: string; created_at: string; tables: { name: string; row_count: number }[] }[]
  >;
}

export async function getManifest(id: string) {
  const r = await check(await fetch(`${API_BASE}/api/datasets/${id}/manifest`));
  return r.json() as Promise<Manifest>;
}

export interface QueryRequest {
  table: string;
  dimensions?: string[];
  time_dimension?: string;
  time_grain?: string;
  measures?: { agg: string; column?: string | null; alias?: string }[];
  filters?: Record<string, unknown>;
  order_by?: string;
  desc?: boolean;
  limit?: number;
}

export async function runQuery(dsId: string, req: QueryRequest, refresh = false) {
  const r = await check(
    await fetch(`${API_BASE}/api/query/${dsId}${refresh ? "?refresh=1" : ""}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    })
  );
  return r.json() as Promise<QueryResult>;
}

export async function getSpikes(dsId: string) {
  const r = await check(
    await fetch(`${API_BASE}/api/analytics/${dsId}/spikes?z_threshold=2.0`)
  );
  return r.json() as Promise<{ alerts: Record<string, string | number>[]; as_of?: string }>;
}

export interface RiskArea {
  area: string;
  recent_daily_avg: number;
  trend_slope: number;
  spike_z: number;
  forecast_daily: number;
  risk_score: number;
  population?: number;
  per_lakh_daily?: number;
  density_per_km2?: number | null;
  urbanization_pct?: number | null;
  exposure_factor?: number;
  components?: { volume: number; trend: number; spike: number; exposure: number };
}

export async function getRisk(dsId: string) {
  const r = await check(await fetch(`${API_BASE}/api/analytics/${dsId}/risk`));
  return r.json() as Promise<{ areas: RiskArea[]; demographics_used?: boolean }>;
}

export async function getHotspots(dsId: string, params: Record<string, string> = {}) {
  const qs = new URLSearchParams(params).toString();
  const r = await check(
    await fetch(`${API_BASE}/api/analytics/${dsId}/hotspots${qs ? `?${qs}` : ""}`)
  );
  return r.json() as Promise<{ cells: { lat: number; lng: number; count: number; intensity: number }[] }>;
}

export async function getAnomalies(dsId: string) {
  const r = await check(
    await fetch(`${API_BASE}/api/analytics/${dsId}/anomalies?limit=20`)
  );
  return r.json() as Promise<{ anomalies: { record_id: string; score: number; record: Record<string, string | null> }[] }>;
}

export async function getGraphSummary(dsId: string) {
  const r = await check(await fetch(`${API_BASE}/api/graph/${dsId}/summary`));
  return r.json() as Promise<{
    nodes: number;
    edges: number;
    key_players: { node: string; label: string; connections: number }[];
    repeat_offenders: { node: string; label: string; case_count: number }[];
    communities: Record<string, number>;
  }>;
}

export async function getEgo(dsId: string, nodeId: string, hops = 2) {
  const r = await check(
    await fetch(`${API_BASE}/api/graph/${dsId}/ego/${encodeURIComponent(nodeId)}?hops=${hops}`)
  );
  return r.json() as Promise<{
    nodes: { id: string; kind: string; label: string; is_center?: boolean }[];
    edges: { source: string; target: string; kind: string; value: string }[];
  }>;
}

export async function searchGraph(dsId: string, q: string) {
  const r = await check(
    await fetch(`${API_BASE}/api/graph/${dsId}/search?q=${encodeURIComponent(q)}`)
  );
  return r.json() as Promise<{ id: string; kind: string; label: string; connections: number }[]>;
}

export async function getPlaybooks() {
  const r = await check(await fetch(`${API_BASE}/api/agents/playbooks`));
  return r.json() as Promise<{ id: string; name: string; description: string }[]>;
}

export interface AgentThreadHeader {
  thread_id: string;
  playbook: string;
  title: string;
  updated_at: string;
  turn_count: number;
}

export interface AgentTurn {
  role: "user" | "agent";
  text: string;
  steps?: { tool: string; args: Record<string, unknown>; result_preview: string }[];
  run_id?: string;
  at?: string;
}

export interface AgentThread {
  thread_id: string;
  playbook: string;
  title: string;
  created_at: string;
  updated_at: string;
  turns: AgentTurn[];
}

export interface AgentMemoryItem {
  id: string;
  text: string;
  kind: string;
  source_thread?: string | null;
  source_playbook?: string | null;
  at?: string;
}

export async function runAgent(
  dsId: string, playbook: string, input: string,
  language = "en", threadId?: string
) {
  const r = await check(
    await fetch(`${API_BASE}/api/agents/${dsId}/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ playbook, input, language, thread_id: threadId ?? null }),
    })
  );
  return r.json() as Promise<{
    run_id: string;
    thread_id: string;
    steps: { tool: string; args: Record<string, unknown>; result_preview: string }[];
    report: string;
  }>;
}

export async function listThreads(dsId: string, playbook: string) {
  const r = await check(
    await fetch(`${API_BASE}/api/agents/${dsId}/threads?playbook=${encodeURIComponent(playbook)}`)
  );
  return r.json() as Promise<AgentThreadHeader[]>;
}

export async function getThread(dsId: string, threadId: string) {
  const r = await check(
    await fetch(`${API_BASE}/api/agents/${dsId}/threads/${encodeURIComponent(threadId)}`)
  );
  return r.json() as Promise<AgentThread>;
}

export async function deleteThread(dsId: string, threadId: string) {
  await check(
    await fetch(`${API_BASE}/api/agents/${dsId}/threads/${encodeURIComponent(threadId)}`, {
      method: "DELETE",
    })
  );
}

export async function getAgentMemory(dsId: string) {
  const r = await check(await fetch(`${API_BASE}/api/agents/${dsId}/memory`));
  return r.json() as Promise<AgentMemoryItem[]>;
}

export async function clearAgentMemory(dsId: string) {
  await check(await fetch(`${API_BASE}/api/agents/${dsId}/memory`, { method: "DELETE" }));
}

// ---- Digital Handbook ----

export interface Handbook {
  dataset: string;
  domain_pack: string;
  period: string;
  generated_at: string;
  kpis: { id: string; title: string; value: number }[];
  by_area?: QueryResult;
  area_label?: string;
  by_category?: QueryResult;
  category_label?: string;
  by_status?: QueryResult;
  monthly_trend?: QueryResult;
  spikes?: Record<string, string | number>[];
  risk?: { areas: RiskArea[]; demographics_used?: boolean };
  demographics?: Record<string, { population: number; density_per_km2?: number; urbanization_pct?: number; literacy_pct?: number }>;
  network?: {
    nodes: number;
    edges: number;
    repeat_offenders: { node: string; label: string; case_count: number }[];
    key_players: { node: string; label: string; connections: number }[];
  };
}

export async function getHandbook(dsId: string, period?: string) {
  const qs = period ? `?period=${period}` : "";
  const r = await check(await fetch(`${API_BASE}/api/reports/${dsId}/handbook${qs}`));
  return r.json() as Promise<Handbook>;
}

export async function getHandbookSummary(dsId: string, language = "en", period?: string) {
  const qs = new URLSearchParams({ language, ...(period ? { period } : {}) });
  const r = await check(
    await fetch(`${API_BASE}/api/reports/${dsId}/handbook/summary?${qs}`)
  );
  return r.json() as Promise<{ summary: string; language: string }>;
}

export async function downloadCsv(dsId: string, req: QueryRequest, filename: string) {
  const r = await check(
    await fetch(`${API_BASE}/api/query/${dsId}?format=csv`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    })
  );
  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// ---- Sentinel alerts ----

export interface SentinelAlert {
  id: string;
  at: string;
  kind: string;
  area?: string | null;
  category?: string | null;
  z_score: number;
  pct_change?: number | null;
  title: string;
  read: boolean;
}

export async function getAlerts(dsId: string) {
  const r = await check(await fetch(`${API_BASE}/api/alerts/${dsId}`));
  return r.json() as Promise<SentinelAlert[]>;
}

export async function markAlertsRead(dsId: string, alertId = "all") {
  await check(
    await fetch(`${API_BASE}/api/alerts/${dsId}/${alertId}/read`, { method: "POST" })
  );
}

export async function ingestFiles(files: File[], name: string) {
  const fd = new FormData();
  files.forEach((f) => fd.append("files", f));
  fd.append("name", name);
  const r = await check(
    await fetch(`${API_BASE}/api/ingest`, { method: "POST", body: fd })
  );
  return r.json() as Promise<Manifest>;
}

// ---- Dataset composition + append (grow an existing dataset) ----

export interface AppendTableResult {
  name: string;
  added: number;
  duplicates_skipped: number;
  extras_ignored: number;
  new_table: boolean;
}

export interface AppendResult {
  tables: AppendTableResult[];
  dataset_version: string;
}

export interface IngestLogEntry {
  at: string;
  action: string;
  files: string[];
  tables: { name: string; added: number; duplicates_skipped: number; new_table: boolean }[];
}

export interface Composition {
  id: string;
  name: string;
  source: "upload" | "seed";
  read_only: boolean;
  created_at: string;
  updated_at: string | null;
  total_rows: number;
  tables: { name: string; row_count: number; n_columns: number }[];
  history: IngestLogEntry[];
}

export async function appendFiles(dsId: string, files: File[]) {
  const fd = new FormData();
  files.forEach((f) => fd.append("files", f));
  const r = await check(
    await fetch(`${API_BASE}/api/ingest/${dsId}/append`, { method: "POST", body: fd })
  );
  return r.json() as Promise<AppendResult>;
}

export async function getComposition(dsId: string) {
  const r = await check(await fetch(`${API_BASE}/api/datasets/${dsId}/composition`));
  return r.json() as Promise<Composition>;
}

// ---- Data Intake (agentic cleaning pipeline) ----

export interface IntakeIteration {
  iteration: number;
  plan: { op: string; column?: string }[];
  applied: { op: string; column?: string; stats?: Record<string, number>; error?: string }[];
  n_changes: number;
  n_quarantined: number;
  assessment: { done?: boolean; issues?: string[]; corrective_plan?: { op: string }[] };
}

export interface IntakeStatus {
  job_id: string;
  name: string;
  status: string;
  done: boolean;
  iterations: IntakeIteration[];
  report: string;
  output_dataset_id: string | null;
  quarantined?: number;
  rows_in?: number;
  rows_out?: number;
  error?: string;
  appended_to?: string;
  added?: number;
  duplicates_skipped?: number;
  note?: string;
}

export async function startIntakeClean(file: File, name: string, destDatasetId?: string) {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("name", name);
  if (destDatasetId) fd.append("dest_dataset_id", destDatasetId);
  const r = await check(
    await fetch(`${API_BASE}/api/intake/clean`, { method: "POST", body: fd })
  );
  return r.json() as Promise<{ job_id: string; key_col: string; rows: number }>;
}

export async function getIntakeStatus(jobId: string) {
  const r = await check(await fetch(`${API_BASE}/api/intake/clean/${jobId}/status`));
  return r.json() as Promise<IntakeStatus>;
}

// ---- Insights (Command Brief) ----

export type InsightType = "spike" | "rising_risk" | "network_hub" | "anomaly" | "data_gap" | "spatiotemporal" | "socio_correlation" | "emerging_typology" | "mo_signature" | "predicted_undetected" | "predicted_stall";

export interface InsightFinding {
  id: string;
  type: InsightType;
  severity: number;
  title: string;
  evidence: Record<string, unknown>;
  area: string | null;
  category: string | null;
  suggested_action: string;
  drill: { surface: "dashboard" | "map" | "network" | "intake"; params: Record<string, string> };
}

export interface InsightForecastArea {
  area: string;
  forecast_daily: number;
  risk_score: number;
  recent_daily_avg: number;
  components?: { volume: number; trend: number; spike: number; exposure: number };
  per_lakh_daily?: number;
}

export interface InsightsResponse {
  dataset_id: string;
  generated_at: string;
  findings: InsightFinding[];
  forecast: {
    horizon_days?: number;
    as_of?: string;
    demographics_used?: boolean;
    confidence?: "high" | "medium" | "low";
    areas?: InsightForecastArea[];
  };
  backtest: {
    available: boolean;
    capture_rate?: number;
    k?: number;
    folds?: number;
    window_days?: number;
    n_areas?: number;
    reason?: string;
  };
  signals_used: string[];
  computed_at?: string;
  cached?: boolean;
}

export async function getInsights(dsId: string, language = "en", refresh = false) {
  const r = await check(
    await fetch(
      `${API_BASE}/api/insights/${dsId}?language=${language}${refresh ? "&refresh=1" : ""}`
    )
  );
  return r.json() as Promise<InsightsResponse>;
}

export async function getInsightsBrief(dsId: string, language = "en", refresh = false) {
  const r = await check(
    await fetch(
      `${API_BASE}/api/insights/${dsId}/brief?language=${language}${refresh ? "&refresh=1" : ""}`
    )
  );
  return r.json() as Promise<{
    brief: string;
    language: string;
    source: "llm" | "fallback";
    computed_at?: string;
    cached?: boolean;
  }>;
}

// ---- Socio-economic correlation ----

export interface CorrelationPoint {
  area: string;
  rate_per_lakh: number;
  urbanization_pct: number | null;
  literacy_pct: number | null;
  density_per_km2: number | null;
}

export interface CorrelationFactor {
  factor: string;
  r: number;
  direction: string;
}

export type CorrelationResult =
  | { available: true; correlations: CorrelationFactor[]; n_areas: number; points: CorrelationPoint[] }
  | { available: false; reason: string };

export async function getCorrelation(dsId: string): Promise<CorrelationResult> {
  const r = await check(await fetch(`${API_BASE}/api/analytics/${dsId}/correlation`));
  return r.json() as Promise<CorrelationResult>;
}

// ---- Repeat-offender MO profile ----

export interface OffenderCase {
  fir: string;
  district: string;
  subtype: string;
  band: string;
}

export interface OffenderProfile {
  node: string;
  label: string | null;
  case_count: number;
  districts: string[];
  mo: { top_subtype: string | null; peak_band: string | null };
  cases: OffenderCase[];
}

export async function getOffenderProfile(dsId: string, node: string): Promise<OffenderProfile> {
  const r = await check(
    await fetch(`${API_BASE}/api/graph/${dsId}/offender/${encodeURIComponent(node)}`)
  );
  return r.json() as Promise<OffenderProfile>;
}

// ---- Predictive Case Triage ----

export interface FlaggedCase {
  id: string;
  detection_prob: number;
  predicted_days: number | null;
  stall: boolean;
  factors: string[];
}

export interface PredictionArea {
  area: string;
  predicted_detection_rate: number;
  n_open: number;
}

export type PredictionResult =
  | {
      available: true;
      flagged: FlaggedCase[];
      by_area: PredictionArea[];
      meta: {
        detection_auc?: number;
        base_rate?: number;
        n_open?: number;
        has_duration?: boolean;
        [key: string]: unknown;
      };
    }
  | { available: false; reason: string };

export async function getPredictions(dsId: string): Promise<PredictionResult> {
  const r = await check(
    await fetch(`${API_BASE}/api/predict/${dsId}/predict?limit=25`)
  );
  return r.json() as Promise<PredictionResult>;
}

// ---- Finale intelligence suite ----

export interface TemporalComparisonFrame {
  index: number;
  from: string;
  to: string;
  rows: number;
  cells: { lat: number; lng: number; count: number; previous_count: number; delta: number; change: "emerging" | "persistent" | "declining" }[];
}

export interface TemporalComparisonData {
  available: boolean;
  reason?: string;
  current: { rows: number };
  previous: { rows: number };
  delta: { absolute: number; percent: number | null };
  areas: { key: string; current: number; previous: number; absolute: number; percent: number | null }[];
  categories: { key: string; current: number; previous: number; absolute: number; percent: number | null }[];
  frames: TemporalComparisonFrame[];
  window: { current: { from: string; to: string }; previous: { from: string; to: string } };
  dataset_version: string;
  generated_at: string;
  evidence_id: string;
}

export type TemporalComparison = TemporalComparisonData | { available: false; reason: string };

export async function getTemporalComparison(dsId: string, from: string, to: string, params: Record<string, string> = {}) {
  const qs = new URLSearchParams({ from_date: from, to_date: to, ...params });
  const r = await check(await fetch(`${API_BASE}/api/temporal/${dsId}/compare?${qs}`));
  return r.json() as Promise<TemporalComparison>;
}

export type InvestigationKind = "area" | "hotspot" | "entity" | "alert" | "finding" | "mission";
export type InvestigationStatus = "new" | "reviewing" | "actioned" | "resolved";
export type InvestigationPriority = "low" | "medium" | "high" | "critical";
export interface InvestigationCard {
  id: string; title: string; kind: InvestigationKind; target: string; status: InvestigationStatus;
  priority: InvestigationPriority; owner: string; notes: string; state: PersistedInvestigationState;
  created_at: string; updated_at: string;
}
export interface CreateInvestigationCardInput { title: string; kind: InvestigationKind; target?: string; priority?: InvestigationPriority; owner?: string; notes?: string; state?: PersistedInvestigationState; }
export interface UpdateInvestigationCardInput { title?: string; status?: InvestigationStatus; priority?: InvestigationPriority; owner?: string; notes?: string; }
export interface WatchRule { id: string; name: string; metric: "percent_change"; operator: "gte" | "lte"; threshold: number; from_date: string; to_date: string; area: string; category: string; enabled: boolean; }
export interface CreateWatchRuleInput { name: string; metric: "percent_change"; operator: "gte" | "lte"; threshold: number; from_date: string; to_date: string; area?: string; category?: string; enabled?: boolean; }
export interface UpdateWatchRuleInput { name?: string; threshold?: number; from_date?: string; to_date?: string; area?: string; category?: string; enabled?: boolean; }
export interface WatchEvent { id: string; rule_id: string; rule_name: string; matched: boolean; value: number | null; threshold: number; evidence_id: string; at: string; created?: boolean; }

async function investigationRequest<T>(path: string, method = "GET", data?: object): Promise<T> {
  const r = await check(await fetch(`${API_BASE}${path}`, { method, headers: data ? { "Content-Type": "application/json" } : undefined, body: data ? JSON.stringify({ data }) : undefined }));
  return r.json() as Promise<T>;
}
export const listInvestigationCards = (ds: string) => investigationRequest<InvestigationCard[]>(`/api/investigations/${ds}/cards`);
export const createInvestigationCard = (ds: string, data: CreateInvestigationCardInput) => investigationRequest<InvestigationCard>(`/api/investigations/${ds}/cards`, "POST", data);
export const updateInvestigationCard = (ds: string, id: string, data: UpdateInvestigationCardInput) => investigationRequest<InvestigationCard>(`/api/investigations/${ds}/cards/${id}`, "PATCH", data);
export const deleteInvestigationCard = (ds: string, id: string) => investigationRequest<{ ok: boolean }>(`/api/investigations/${ds}/cards/${id}`, "DELETE");
export const listWatchRules = (ds: string) => investigationRequest<WatchRule[]>(`/api/investigations/${ds}/rules`);
export const createWatchRule = (ds: string, data: CreateWatchRuleInput) => investigationRequest<WatchRule>(`/api/investigations/${ds}/rules`, "POST", data);
export const updateWatchRule = (ds: string, id: string, data: UpdateWatchRuleInput) => investigationRequest<WatchRule>(`/api/investigations/${ds}/rules/${id}`, "PATCH", data);
export const deleteWatchRule = (ds: string, id: string) => investigationRequest<{ ok: boolean }>(`/api/investigations/${ds}/rules/${id}`, "DELETE");
export const evaluateWatchRule = (ds: string, id: string) => investigationRequest<WatchEvent>(`/api/investigations/${ds}/rules/${id}/evaluate`, "POST");
export const listWatchEvents = (ds: string) => investigationRequest<WatchEvent[]>(`/api/investigations/${ds}/events`);
