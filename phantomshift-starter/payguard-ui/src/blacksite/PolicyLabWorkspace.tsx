import type { IncidentDetail, ReplayRow } from "../types";

interface Props {
  detail?: IncidentDetail;
  replays: ReplayRow[];
  loading: boolean;
}

function laneClass(status: string) {
  if (status === "passed") return "border-chartreuse/35 bg-chartreuse/[0.04]";
  if (status === "failed") return "border-coral/35 bg-coral/[0.04]";
  return "border-amber/30 bg-amber/[0.04]";
}

export function PolicyLabWorkspace({ detail, replays, loading }: Props) {
  return (
    <div className="flex flex-col gap-4 min-h-0 flex-1 overflow-auto p-4">
      <div>
        <h2 className="text-base font-semibold tracking-tight">Policy comparison</h2>
        <p className="text-xs text-fg-muted mt-1">{detail?.scenario_id ?? "—"} · same corpus, all policies</p>
      </div>

      {loading && <p className="text-sm text-fg-muted">Loading replay matrix…</p>}

      <div className="grid gap-3">
        {replays.map((r) => (
          <article
            key={r.candidate_policy_digest}
            className={`rounded-xl border p-4 ${laneClass(r.status)}`}
          >
            <div className="flex flex-wrap justify-between gap-2 mb-3">
              <h3 className="font-medium text-sm">{r.policy_label}</h3>
              <span className="text-[10px] font-mono uppercase text-fg-muted">{r.status}</span>
            </div>
            <div className="grid sm:grid-cols-3 gap-3 text-xs font-mono tabular-nums">
              <div>
                <p className="kpi-label mb-1">Attacker goal</p>
                <p>
                  {r.malicious_blocked}/{r.malicious_total} blocked
                </p>
              </div>
              <div>
                <p className="kpi-label mb-1">Legitimate tasks</p>
                <p>
                  {r.benign_allowed}/{r.benign_total} allowed
                </p>
              </div>
              <div>
                <p className="kpi-label mb-1">False denials</p>
                <p>{r.false_positive_denials}</p>
              </div>
            </div>
            {r.selected && <p className="text-[10px] text-chartreuse mt-2 font-mono">Selected verified candidate</p>}
          </article>
        ))}
      </div>

    </div>
  );
}
