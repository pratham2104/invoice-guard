import type { TraceNode } from "../types";

interface Props {
  nodes: TraceNode[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export function AccessibleGraphList({ nodes, selectedId, onSelect }: Props) {
  return (
    <ul className="mt-2 space-y-1 text-xs font-mono" aria-label="Graph nodes (keyboard accessible)">
      {nodes.map((n) => (
        <li key={n.id}>
          <button
            type="button"
            className={`w-full text-left rounded px-2 py-1 border ${
              selectedId === n.id ? "border-trace bg-graphite-raised" : "border-transparent hover:border-ink-stroke"
            }`}
            onClick={() => onSelect(n.id)}
          >
            <span className="text-ink-secondary">{n.kind}</span> — {n.label}
          </button>
        </li>
      ))}
    </ul>
  );
}
