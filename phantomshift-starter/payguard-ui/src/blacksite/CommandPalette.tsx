import { useEffect } from "react";

export type PaletteAction = { id: string; label: string; run: () => void };

interface Props {
  open: boolean;
  onClose: () => void;
  query: string;
  onQuery: (q: string) => void;
  actions: PaletteAction[];
}

export function CommandPalette({ open, onClose, query, onQuery, actions }: Props) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const filtered = actions.filter((a) => !query || a.label.toLowerCase().includes(query.toLowerCase()));

  return (
    <div className="fixed inset-0 z-[60] bg-black/60 flex items-start justify-center pt-[15vh] px-4" role="dialog" aria-modal="true">
      <div className="panel w-full max-w-lg overflow-hidden">
        <input
          autoFocus
          className="w-full border-b border-stroke bg-bg-s2 px-4 py-3 text-sm focus:outline-none"
          placeholder="Jump to workspace or incident…"
          value={query}
          onChange={(e) => onQuery(e.target.value)}
          aria-label="Command palette"
        />
        <ul className="max-h-64 overflow-auto py-2">
          {filtered.map((a) => (
            <li key={a.id}>
              <button
                type="button"
                className="w-full text-left px-4 py-2 text-sm hover:bg-bg-s3"
                onClick={() => {
                  a.run();
                  onClose();
                }}
              >
                {a.label}
              </button>
            </li>
          ))}
        </ul>
        <p className="text-[10px] text-fg-tertiary px-4 py-2 border-t border-stroke">Read-only navigation · no shell execution</p>
      </div>
    </div>
  );
}
