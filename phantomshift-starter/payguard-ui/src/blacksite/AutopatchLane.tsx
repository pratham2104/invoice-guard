import type { AutopatchEvent, AutopatchFinding } from "../api";

const STEPS = ["OBSERVE", "HYPOTHESIZE", "REPRODUCE", "EVALUATE", "REVIEW", "VERIFY"] as const;

interface Props {
  events: AutopatchEvent[];
  findings: AutopatchFinding[];
  mode: string;
}

export function AutopatchLane({ events, findings, mode }: Props) {
  const latest = findings[0];
  return (
    <section className="panel overflow-hidden" aria-label="AUTOPATCH research">
      <div className="panel-head">
        <div>
          <h2 className="panel-title">AUTOPATCH</h2>
          <p className="text-[10px] text-fg-tertiary mt-0.5">Continuous discovery · fixture-backed on this host</p>
        </div>
        <span className="badge-demo text-[9px]">{mode.replace("_", " ")}</span>
      </div>
      <div className="px-4 py-2 flex flex-wrap gap-1 border-b border-stroke/60">
        {STEPS.map((s, i) => (
          <span
            key={s}
            className={`text-[9px] font-mono uppercase px-2 py-0.5 rounded-md border ${
              latest && i <= 3 ? "border-chartreuse/30 text-chartreuse" : "border-stroke text-fg-tertiary"
            }`}
          >
            {s}
          </span>
        ))}
      </div>
      <div className="p-3 grid md:grid-cols-2 gap-3 max-h-[140px] overflow-auto">
        <div>
          <p className="text-[10px] uppercase text-fg-muted mb-2">Activity</p>
          {events.length === 0 ? (
            <p className="text-xs text-fg-tertiary">No events yet — run `autopatch --research-once` or trigger firewall deny.</p>
          ) : (
            <ul className="space-y-1">
              {events.slice(0, 5).map((e) => (
                <li key={e.fingerprint} className="text-[11px] font-mono truncate">
                  <span className="text-cyan">{e.event_type}</span> · {e.created_at?.slice(11, 19) ?? "—"}
                </li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <p className="text-[10px] uppercase text-fg-muted mb-2">Findings</p>
          {!latest ? (
            <p className="text-xs text-fg-tertiary">No confirmed findings in store.</p>
          ) : (
            <div className="rounded-lg border border-stroke bg-bg-s2/80 p-2 text-xs">
              <p className="font-mono text-[10px] text-fg-muted">{latest.finding_id}</p>
              <p className="text-chartreuse font-medium mt-1">{latest.state ?? "PROPOSED"}</p>
              <p className="text-[10px] text-fg-tertiary mt-1">RWCR priority {latest.priority_index ?? "—"} (heuristic)</p>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
