import { X } from "lucide-react";

const STEPS = [
  "Synthetic invoice appears in incident rail (fixture PAYGUARD scenario).",
  "Trace shows untrusted input → agent/Nemotron path → proposed payment tool.",
  "Deterministic trust boundary breaks the path; simulated ledger unchanged.",
  "Policy Lab compares baseline, broad deny, and context-bound on same denominators.",
  "Discord approval shows hash-bound request — approve only via authenticated channel.",
  "Verification receipt and benchmarks — label HISTORICAL vs LIVE explicitly.",
];

interface Props {
  open: boolean;
  step: number;
  onStep: (n: number) => void;
  onClose: () => void;
}

export function DemoGuide({ open, step, onStep, onClose }: Props) {
  if (!open) return null;
  return (
    <div className="fixed bottom-4 right-4 z-50 w-full max-w-md panel shadow-xl" role="dialog" aria-labelledby="demo-guide-title">
      <div className="panel-head">
        <div>
          <h3 id="demo-guide-title" className="text-sm font-semibold text-fg">
            Demo guide
          </h3>
          <p className="text-[10px] text-amber font-mono uppercase mt-0.5">SYNTHETIC DEMO · manual advance</p>
        </div>
        <button type="button" className="btn-ghost" aria-label="Close demo guide" onClick={onClose}>
          <X size={14} />
        </button>
      </div>
      <div className="p-4 text-sm text-fg-muted">
        <p>{STEPS[step]}</p>
        <div className="flex gap-2 mt-4">
          <button type="button" className="btn-ghost" disabled={step <= 0} onClick={() => onStep(step - 1)}>
            Back
          </button>
          <button type="button" className="btn-ghost btn-ghost-active" disabled={step >= STEPS.length - 1} onClick={() => onStep(step + 1)}>
            Next
          </button>
        </div>
        <p className="text-[10px] text-fg-tertiary mt-3">
          Step {step + 1}/{STEPS.length} · Protect the action. Prove the fix.
        </p>
      </div>
    </div>
  );
}
