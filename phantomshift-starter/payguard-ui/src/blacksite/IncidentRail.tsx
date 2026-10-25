import type { IncidentSummary } from "../types";

interface Props {
  incidents: IncidentSummary[];
  selectedId: string;
  filter: string;
  onFilter: (v: string) => void;
  onSelect: (id: string) => void;
}

function statusDot(status: string) {
  if (status === "blocked") return "bg-coral";
  if (status === "resolved") return "bg-chartreuse";
  return "bg-amber";
}

export function IncidentRail({ incidents, selectedId, filter, onFilter, onSelect }: Props) {
  return (
    <aside className="panel flex flex-col min-h-0 overflow-hidden" aria-label="Incidents">
      <div className="panel-head">
        <h2 className="panel-title">Incidents</h2>
        <span className="text-[10px] font-mono text-fg-tertiary">{incidents.length}</span>
      </div>
      <div className="p-3 flex-1 flex flex-col min-h-0">
        <input
          className="w-full mb-3 rounded-xl border border-stroke bg-bg-s2 px-3 py-2 text-xs placeholder:text-fg-tertiary focus:border-cyan/40 focus:outline-none"
          placeholder="Search ID, title, scenario…"
          value={filter}
          onChange={(e) => onFilter(e.target.value)}
          aria-label="Filter incidents"
        />
        <ul className="space-y-2 overflow-auto flex-1 pr-1">
          {incidents.map((inc) => (
            <li key={inc.id}>
              <button
                type="button"
                onClick={() => onSelect(inc.id)}
                className={`incident-card ${selectedId === inc.id ? "incident-card-active" : ""}`}
              >
                <div className="flex items-start gap-2">
                  <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${statusDot(inc.status)}`} />
                  <div className="min-w-0 flex-1">
                    <div className="text-[10px] font-mono text-fg-tertiary uppercase">{inc.id.replace("fixture-", "PAY-")}</div>
                    <div className="font-medium text-sm truncate mt-0.5">{inc.title}</div>
                    <div className="text-[10px] text-fg-muted mt-1 line-clamp-2">{inc.source_type}</div>
                    {inc.financial_exposure_usd != null && inc.financial_exposure_usd > 0 && (
                      <div className="text-[10px] text-fg-tertiary mt-1">${inc.financial_exposure_usd.toLocaleString()} exposure</div>
                    )}
                  </div>
                </div>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </aside>
  );
}
