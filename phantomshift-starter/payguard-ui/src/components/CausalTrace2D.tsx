import type { TraceEdge, TraceNode } from "../types";

interface Props {
  nodes: TraceNode[];
  edges: TraceEdge[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  denied: boolean;
}

/** Accessible 2D causal trace (mobile / no WebGL). */
export function CausalTrace2D({ nodes, edges, selectedId, onSelect, denied }: Props) {
  const sorted = [...nodes].sort((a, b) => a.position[0] - b.position[0]);
  return (
    <div className="rounded-panel border border-ink-stroke bg-graphite-panel p-3" aria-label="2D attack trace">
      <p className="text-[10px] text-ink-secondary mb-2 font-mono uppercase">2D trace · SYNTHETIC DEMO</p>
      <div className="flex flex-wrap items-center gap-2 justify-center">
        {sorted.map((n, i) => (
          <div key={n.id} className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => onSelect(n.id)}
              className={`rounded-lg border px-2 py-2 text-left text-xs max-w-[120px] ${
                selectedId === n.id ? "border-trace bg-graphite-raised" : "border-ink-stroke"
              } ${n.kind === "policy_gate" && denied ? "border-danger text-danger" : ""}`}
            >
              <div className="font-mono text-[10px] text-ink-secondary">{n.kind}</div>
              <div className="truncate">{n.label}</div>
            </button>
            {i < sorted.length - 1 && (
              <span className="text-ink-secondary" aria-hidden>
                →
              </span>
            )}
          </div>
        ))}
      </div>
      {denied && (
        <p className="text-center text-danger text-sm font-semibold mt-3" role="status">
          Blocked at policy gate — no completed payment path
        </p>
      )}
      <p className="text-[10px] text-ink-secondary mt-2">{edges.length} causal edges in graph</p>
    </div>
  );
}
