import type { DashboardStatus, IncidentDetail, IncidentSummary, ReplayRow } from "./types";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(path, { headers: { Accept: "application/json" } });
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new Error(body?.error ?? `HTTP ${res.status}`);
  return body as T;
}

async function post<T>(path: string): Promise<T> {
  const res = await fetch(path, { method: "POST", headers: { Accept: "application/json" } });
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new Error(body?.error ?? `HTTP ${res.status}`);
  return body as T;
}

export interface GateRow {
  gate?: string;
  id?: string;
  status: string;
  detail?: string;
}

export interface AutopatchEvent {
  event_type: string;
  fingerprint: string;
  payload: Record<string, unknown>;
  created_at?: string;
}

export interface AutopatchFinding {
  finding_id?: string;
  state?: string;
  priority_index?: number;
  severity?: string;
  fingerprint?: string;
}

export interface BenchmarkPack {
  mode: string;
  host_class?: string;
  policy_baselines: Array<{
    id: string;
    label: string;
    attack_k: number;
    attack_n: number;
    legit_k: number;
    legit_n: number;
    mode: string;
  }>;
  model_development?: {
    label: string;
    model: string;
    replay_mode: string;
    unguarded_attack_success: { k: number; n: number };
    context_bound_attack_success: { k: number; n: number };
    legit_completion_baseline_and_guard: { k: number; n: number };
  };
  claims_doc?: string;
}

export type { IncidentSummary };

export const api = {
  status: () => get<DashboardStatus>("/api/dashboard/status"),
  gates: () => get<GateRow[]>("/api/gates"),
  incidents: () => get<{ incidents: IncidentSummary[]; mode: string }>("/api/incidents?limit=50"),
  incident: (id: string) => get<IncidentDetail>(`/api/incidents/${id}`),
  replays: (id: string) => get<{ replays: ReplayRow[]; disclaimer?: string }>(`/api/incidents/${id}/replays`),
  runReplays: (id: string) => post<{ replays: ReplayRow[] }>(`/api/incidents/${id}/replays`),
  approvalRequest: (id: string) => post<Record<string, unknown>>(`/api/incidents/${id}/approval-request`),
  metrics: () => get<Record<string, unknown>>("/api/metrics"),
  autopatchEvents: (limit = 30) => get<{ events: AutopatchEvent[]; mode: string }>(`/api/autopatch/events?limit=${limit}`),
  autopatchFindings: (limit = 10) => get<{ findings: AutopatchFinding[]; mode: string }>(`/api/autopatch/findings?limit=${limit}`),
  evidenceBenchmarks: () => get<BenchmarkPack>("/api/evidence/benchmarks"),
};
