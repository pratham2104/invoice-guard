import { ChevronDown, Lock, ShieldAlert } from "lucide-react";
import { useState } from "react";
import type { IncidentDetail, TraceNode } from "../types";

interface Props {
  detail: IncidentDetail;
  selected?: TraceNode;
  onRequestApproval: () => void;
  approvalPending: boolean;
  approvalData?: Record<string, unknown>;
}

export function EvidenceInspector({ detail, selected, onRequestApproval, approvalPending, approvalData }: Props) {
  const [rawOpen, setRawOpen] = useState(false);
  const verdict = detail.policy_verdict as { held?: boolean; boundary?: string; violations?: unknown[] };
  const proposal = detail.tool_proposal as { tool?: string; note?: string; args_redacted?: Record<string, unknown> };

  return (
    <div className="space-y-4 text-sm">
      <div>
        <p className="kpi-label mb-1">Incident</p>
        <p className="font-mono text-[11px] text-ink-secondary break-all">{detail.id}</p>
      </div>

      {verdict.held && (
        <div className="flex gap-2 rounded-lg border border-danger/30 bg-danger/[0.06] p-3">
          <ShieldAlert className="shrink-0 text-danger" size={18} />
          <div>
            <p className="font-medium text-danger text-xs">Action held before execution</p>
            <p className="text-[11px] text-ink-secondary mt-1">{verdict.boundary}</p>
          </div>
        </div>
      )}

      <div>
        <p className="panel-title mb-2">Untrusted source</p>
        <div className="evidence-block max-h-28 overflow-y-auto whitespace-pre-wrap font-mono text-[11px]">
          {detail.source_excerpt}
        </div>
      </div>

      <div>
        <p className="panel-title mb-2">Tool proposal</p>
        <div className="evidence-block space-y-1">
          <p>
            <span className="text-ink-primary font-medium">{proposal.tool ?? "—"}</span>
            {proposal.note && <span className="text-ink-secondary"> — {proposal.note}</span>}
          </p>
          {proposal.args_redacted && (
            <p className="font-mono text-[11px]">
              vendor {String(proposal.args_redacted.vendor_id)} · amount {String(proposal.args_redacted.amount)} · acct{" "}
              {String(proposal.args_redacted.account)}
            </p>
          )}
        </div>
      </div>

      {selected && (
        <div className="flex flex-wrap gap-2 text-[11px] font-mono">
          <span className="rounded-md bg-graphite-raised px-2 py-0.5 border border-ink-stroke">{selected.kind}</span>
          <span className="rounded-md bg-graphite-raised px-2 py-0.5 border border-ink-stroke">{selected.trust}</span>
          {selected.outcome && (
            <span className="rounded-md bg-graphite-raised px-2 py-0.5 border border-ink-stroke">{selected.outcome}</span>
          )}
        </div>
      )}

      <button
        type="button"
        className="btn-ghost w-full justify-center text-warn border-warn/30"
        onClick={onRequestApproval}
        disabled={approvalPending}
      >
        <Lock size={14} /> Check approval status (read-only)
      </button>

      {approvalData && (
        <p className="text-[11px] text-ink-secondary font-mono" data-testid="approval-json">
          UI cannot deploy — {String(approvalData.reason ?? "ui_cannot_deploy_policy")}.
        </p>
      )}

      <button
        type="button"
        className="flex w-full items-center justify-between text-[11px] text-ink-secondary hover:text-ink-primary"
        onClick={() => setRawOpen((v) => !v)}
      >
        Raw verdict JSON
        <ChevronDown size={14} className={rawOpen ? "rotate-180" : ""} />
      </button>
      {rawOpen && (
        <pre className="evidence-block text-[10px] overflow-auto max-h-40">{JSON.stringify(verdict, null, 2)}</pre>
      )}
    </div>
  );
}
