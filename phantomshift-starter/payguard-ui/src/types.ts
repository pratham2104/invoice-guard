export type DataMode = "live_verified" | "replay" | "synthetic_demo";
export type NodeKind =
  | "untrusted_input"
  | "trusted_instruction"
  | "agent"
  | "model_route"
  | "tool_proposal"
  | "policy_gate"
  | "external_effect"
  | "approval"
  | "verification";
export type EdgeKind =
  | "data_flow"
  | "influence"
  | "proposed_action"
  | "denied_at_gate"
  | "allowed_action"
  | "evidence_link"
  | "policy_fork";

export interface TraceNode {
  id: string;
  incident_id: string;
  kind: NodeKind;
  label: string;
  timestamp: string;
  trust: "trusted" | "untrusted" | "unknown";
  outcome?: string;
  position: [number, number, number];
  evidence_refs: string[];
}

export interface TraceEdge {
  id: string;
  from: string;
  to: string;
  kind: EdgeKind;
  timestamp?: string;
  evidence_refs: string[];
}

export interface IncidentSummary {
  id: string;
  scenario_id: string;
  mode: DataMode;
  status: string;
  title: string;
  financial_exposure_usd?: number;
  exposure_basis?: string;
  source_type: string;
  created_at: string;
}

export interface IncidentDetail extends IncidentSummary {
  run_id: string;
  source_excerpt: string;
  trusted_task: string;
  tool_proposal: Record<string, unknown>;
  policy_verdict: Record<string, unknown>;
  live_action: { held?: boolean; violations?: unknown[] };
  nodes: TraceNode[];
  edges: TraceEdge[];
  forks?: unknown[];
  selected_policy?: string;
  approval?: Record<string, unknown>;
  verification?: Record<string, unknown>;
  replay_mode: string;
  evidence: string;
}

export interface DashboardStatus {
  mode: DataMode;
  backend_connected: boolean;
  guard_posture?: string;
  last_seen_at?: string;
  hardware_gate: string;
  nemo_claw_gate: string;
  openclaw_gate: string;
  openshell_gate: string;
  discord_gate: string;
  local_llm_gate: string;
  labels?: Record<string, string>;
}

export interface ReplayRow {
  candidate_policy_digest: string;
  policy_label: string;
  status: string;
  malicious_blocked: number;
  malicious_total: number;
  benign_allowed: number;
  benign_total: number;
  false_positive_denials: number;
  selected?: boolean;
}
