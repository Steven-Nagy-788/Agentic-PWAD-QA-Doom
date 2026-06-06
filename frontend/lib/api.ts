export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "/api/v1";
export const API_ROOT = process.env.NEXT_PUBLIC_API_ROOT ?? apiRootFromBase(API_BASE);
export const WS_BASE = process.env.NEXT_PUBLIC_WS_BASE ?? "";

export type WadFile = {
  id: string;
  original_filename: string;
  file_size_bytes: number;
  sha256_hash: string;
  validation_status: string;
  validation_error?: string | null;
  detected_maps?: string[] | null;
  iwad_required: string;
  uploaded_at: string;
};

export type WadMap = {
  wad_file_id: string;
  map_name: string;
  map_title?: string | null;
  map_display_name?: string | null;
  iwad_required: string;
  analyzed: boolean;
  thing_count_enemies?: number | null;
  thing_count_items?: number | null;
  secret_sector_count?: number | null;
  estimated_difficulty?: string | null;
  spawn_summary_by_skill?: Record<string, SkillSummary> | null;
  map_overview_png_url?: string | null;
  map_min_x?: number | null;
  map_max_x?: number | null;
  map_min_y?: number | null;
  map_max_y?: number | null;
  map_width_units?: number | null;
  map_height_units?: number | null;
};

export type SkillSummary = {
  difficulty_level?: number;
  thing_count_enemies?: number;
  thing_count_items?: number;
  total_health_pickup_pts?: number;
  ammo_ratio?: number;
  health_ratio?: number;
  estimated_difficulty?: string;
};

export type Run = {
  id: string;
  wad_file_id: string;
  static_analysis_id?: string | null;
  map_name: string;
  map_display_name?: string | null;
  difficulty_level: number;
  iwad_used: string;
  llm_model: string;
  max_ticks: number;
  seed?: number | null;
  start_normalization?: Record<string, unknown> | null;
  status: string;
  started_at?: string | null;
  completed_at?: string | null;
  duration_seconds?: number | null;
  outcome?: string | null;
  error_message?: string | null;
  failure_category?: string | null;
  failure_stage?: string | null;
  failure_summary?: string | null;
  final_hp?: number | null;
  final_armor?: number | null;
  total_kills?: number | null;
  secrets_found?: number | null;
  total_items_collected?: number | null;
  total_actions_taken?: number | null;
  total_llm_calls?: number | null;
  recording_mp4_url?: string | null;
  recording_metadata?: Record<string, unknown> | null;
  behavior_profile?: string | null;
  progress_metrics?: Record<string, unknown> | null;
  agent_quality_flags?: Record<string, unknown> | null;
  environment_metadata?: Record<string, unknown> | null;
  report_pdf_url?: string | null;
  created_at: string;
};

export type RunList = {
  total: number;
  items: Run[];
  offset: number;
};

export type TraceEntry = {
  id: number;
  run_id: string;
  tick_number: number;
  player_x: number;
  player_y: number;
  player_angle: number;
  health: number;
  armor: number;
  ammo_bullets: number;
  ammo_shells: number;
  ammo_rockets: number;
  ammo_cells: number;
  kill_count: number;
  item_count: number;
  secret_count: number;
  event_type: string;
  llm_reasoning?: string | null;
  mcp_tool?: string | null;
  mcp_stop_reason?: string | null;
};

export type Decision = {
  id: string;
  run_id: string;
  sequence_number: number;
  tick_before?: number | null;
  tick_after?: number | null;
  status: string;
  reasoning_summary?: string | null;
  mcp_tool?: string | null;
  mcp_input?: Record<string, unknown> | null;
  mcp_output?: Record<string, unknown> | null;
  mcp_stop_reason?: string | null;
  decision_source: string;
  guard_modified?: boolean;
  guard_reason?: string | null;
  validation_rejection?: string | null;
  llm_duration_ms?: number | null;
  mcp_duration_ms?: number | null;
  llm_input_tokens?: number | null;
  llm_output_tokens?: number | null;
  llm_cost_estimate_usd?: number | null;
};

export type Defect = {
  id?: string;
  defect_type: string;
  title: string;
  severity: number;
  detected_at_tick?: number | null;
  fingerprint?: string | null;
  description?: string | null;
  resolution_status?: string;
};

export type PositionSample = {
  id: number;
  run_id: string;
  tick_number: number;
  x: number;
  y: number;
  angle?: number;
  health: number;
  is_sentinel?: boolean;
};

export type AppSettings = {
  app_name: string;
  app_env: string;
  llm_model: string;
  llm_throttle_seconds: number;
  gemini_rate_limit_calls_per_minute: number;
  llm_input_cost_per_million: number;
  llm_output_cost_per_million: number;
  max_run_ticks: number;
  default_run_ticks: number;
  live_frame_fps: number;
  recording_fps: number;
  recording_telemetry_stride: number;
  default_agent_behavior: string;
  iwad_used: string;
  cross_run_memory_enabled: boolean;
  guard_enabled: boolean;
  sources: Record<string, "environment" | "database_override">;
  env_defaults: Record<string, unknown>;
};

export type UsageStats = {
  run_id: string;
  model: string;
  total_llm_calls: number;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number;
  per_decision_avg_cost_usd: number;
};

export type LatencyStats = {
  avg: number;
  p50: number;
  p95: number;
  max: number;
  min: number;
  count: number;
};

export type BenchmarkStats = {
  run_id: string;
  total_decisions: number;
  llm_latency_ms: LatencyStats;
  mcp_latency_ms: LatencyStats;
  tools_used: Record<string, number>;
};

export type ReportStatus = {
  status: string;
  report_id?: string | null;
  pdf_available?: boolean | null;
  pdf_url?: string | null;
  generation_error?: string | null;
};

export type BehaviorProfile = {
  name: string;
  description: string;
};

export type RecurringDefect = {
  fingerprint: string;
  defect_type: string;
  title: string;
  occurrences: number;
  run_count: number;
};

export type MapMemory = {
  wad_id: string;
  map_name: string;
  recurring_defects: RecurringDefect[];
  hypotheses: { tag: string; content: string; confidence: number; evidence_status?: string }[];
  summary_counts: { prior_run_count: number; outcome_counts: Record<string, number> };
};

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  return response.json() as Promise<T>;
}

export async function apiRootGet<T>(path: string): Promise<T> {
  const response = await fetch(`${API_ROOT}${path}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  return response.json() as Promise<T>;
}

export async function apiSend<T>(path: string, init: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    throw new Error(await errorText(response));
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

export async function uploadWad(file: File): Promise<WadFile> {
  const data = new FormData();
  data.append("file", file);
  return apiSend<WadFile>("/wads/upload", { method: "POST", body: data });
}

export function assetUrl(path?: string | null): string | undefined {
  if (!path) {
    return undefined;
  }
  return path.startsWith("http") ? path : `${API_BASE}${path}`;
}

export function websocketUrl(runId: string): string {
  const base = websocketBaseUrl();
  const apiPrefix = base.pathname.replace(/\/$/, "");
  base.protocol = base.protocol === "https:" ? "wss:" : "ws:";
  base.pathname = `${apiPrefix}/ws/runs/${runId}`;
  return base.toString();
}

function websocketBaseUrl(): URL {
  if (WS_BASE) {
    return new URL(WS_BASE);
  }
  if (API_BASE.startsWith("http")) {
    return new URL(API_BASE);
  }
  const fallbackOrigin = typeof window !== "undefined" ? window.location.origin : "http://localhost:3000";
  const base = new URL(fallbackOrigin);
  if (isLocalFrontendOrigin(base) && API_BASE.startsWith("/api/")) {
    base.port = "8000";
    base.pathname = API_BASE.replace(/^\/api/, "").replace(/\/$/, "");
    return base;
  }
  base.pathname = API_BASE.replace(/\/$/, "");
  return base;
}

function isLocalFrontendOrigin(base: URL): boolean {
  return ["localhost", "127.0.0.1", "0.0.0.0"].includes(base.hostname);
}

function apiRootFromBase(base: string): string {
  if (base.endsWith("/v1")) {
    return base.slice(0, -3);
  }
  return base.replace(/\/v1\/?$/, "");
}

async function errorText(response: Response): Promise<string> {
  const text = await response.text();
  if (!text) {
    return `${response.status} ${response.statusText}`;
  }
  try {
    const parsed = JSON.parse(text);
    return typeof parsed.detail === "string" ? parsed.detail : JSON.stringify(parsed.detail ?? parsed);
  } catch {
    return text;
  }
}
