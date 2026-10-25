import type { DashboardStatus, ReplayRow } from "../types";

interface Props {
  status?: DashboardStatus;
  exposure?: { value: number; basis: string };
  replays: ReplayRow[];
  approvalNote?: string;
  historicalNote?: string;
}

export function RealityStrip({ status, exposure, replays, approvalNote, historicalNote }: Props) {
  const ctx = replays.find((r) => r.policy_label.toLowerCase().includes("context"));
  const baseline = replays.find((r) => r.policy_label.toLowerCase().includes("baseline") || r.candidate_policy_digest === "baseline");

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3 p-3 border-t border-stroke bg-bg-s1/80" data-testid="reality-strip">
      <div className="rounded-xl border border-stroke bg-bg-s2/60 p-3">
        <p className="kpi-label">Exposure</p>
        <p className="kpi-value text-lg">{exposure ? `$${exposure.value.toLocaleString()}` : "—"}</p>
        <p className="text-[10px] text-fg-muted mt-1">Simulated transaction exposure · not savings</p>
      </div>
      <div className="rounded-xl border border-stroke bg-bg-s2/60 p-3" data-testid="policy-fork-panel">
        <p className="kpi-label">Policy comparison</p>
        <p className="text-xs font-mono tabular-nums mt-1">
          Baseline atk {baseline ? `${baseline.malicious_total - baseline.malicious_blocked}/${baseline.malicious_total}` : "—"}
        </p>
        <p className="text-xs font-mono tabular-nums text-chartreuse">
          Context bound blk {ctx ? `${ctx.malicious_blocked}/${ctx.malicious_total}` : "—"} · legit{" "}
          {ctx ? `${ctx.benign_allowed}/${ctx.benign_total}` : "—"}
        </p>
      </div>
      <div className="rounded-xl border border-stroke bg-bg-s2/60 p-3">
        <p className="kpi-label">Runtime</p>
        <p className="text-xs mt-1">
          GB10 / Nemotron: <span className="font-mono text-amber">{status?.local_llm_gate ?? "not_tested"}</span>
        </p>
        <p className="text-[10px] text-fg-muted mt-1">{historicalNote ?? "Local inference not verified from this UI host."}</p>
      </div>
      <div className="rounded-xl border border-stroke bg-bg-s2/60 p-3">
        <p className="kpi-label">Approval</p>
        <p className="text-xs text-discord mt-1">Discord · server-authenticated only</p>
        <p className="text-[10px] font-mono text-fg-muted mt-1 truncate">{approvalNote ?? "No pending hash-bound request"}</p>
      </div>
    </div>
  );
}
