import type { TraceNode } from "../types";

interface Props {
  nodes: TraceNode[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  denied: boolean;
}

export function MobileTimeline({ nodes, selectedId, onSelect, denied }: Props) {
  const sorted = [...nodes].sort((a, b) => a.position[0] - b.position[0]);
  return (
    <ol className="space-y-2 p-2" aria-label="Incident timeline">
      {sorted.map((n) => (
        <li key={n.id}>
          <button
            type="button"
            onClick={() => onSelect(n.id)}
            className={`w-full text-left rounded-xl border px-3 py-2 ${
              selectedId === n.id ? "border-cyan/50 bg-bg-s3" : "border-stroke bg-bg-s2/60"
            }`}
          >
            <span className="text-[10px] font-mono uppercase text-fg-muted">{n.kind.replace(/_/g, " ")}</span>
            <p className="text-sm font-medium mt-0.5">{n.label}</p>
            {n.kind === "policy_gate" && denied && (
              <p className="text-xs text-coral mt-1 font-semibold">Blocked at trust boundary</p>
            )}
          </button>
        </li>
      ))}
    </ol>
  );
}
