import { Info } from "lucide-react";
import { useState } from "react";

interface Props {
  label: string;
  detail: string;
}

export function SourceAssumptionTag({ label, detail }: Props) {
  const [open, setOpen] = useState(false);
  return (
    <span className="relative inline-flex">
      <button
        type="button"
        className="inline-flex items-center gap-1 text-[10px] text-ink-secondary border border-ink-stroke rounded px-1.5 py-0.5"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <Info size={10} /> Source
      </button>
      {open && (
        <div
          role="tooltip"
          className="absolute z-20 bottom-full left-0 mb-1 w-56 rounded border border-ink-stroke bg-graphite-raised p-2 text-[10px] text-ink-secondary shadow-lg"
        >
          <strong className="text-ink-primary block mb-1">{label}</strong>
          {detail}
        </div>
      )}
    </span>
  );
}
