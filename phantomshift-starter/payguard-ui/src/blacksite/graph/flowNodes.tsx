import { memo, type ReactNode } from "react";
import type { NodeProps } from "@xyflow/react";
import { Handle, Position } from "@xyflow/react";

type NodeData = {
  label: string;
  kind: string;
  trust: string;
  outcome?: string;
  denied?: boolean;
};

function shell(
  children: ReactNode,
  border: string,
  dot: string,
  subtitle?: string,
) {
  return (
    <div className={`min-w-[148px] max-w-[168px] rounded-xl border px-3 py-2.5 bg-bg-s1 ${border}`}>
      <div className="flex items-center gap-2 mb-1">
        <span className={`h-2 w-2 rounded-full shrink-0 ${dot}`} aria-hidden />
        <span className="text-[10px] font-mono uppercase text-fg-muted truncate">{subtitle}</span>
      </div>
      {children}
      <Handle type="target" position={Position.Left} className="!bg-stroke !w-2 !h-2 !border-0" />
      <Handle type="source" position={Position.Right} className="!bg-stroke !w-2 !h-2 !border-0" />
    </div>
  );
}

export const UntrustedNode = memo(({ data, selected }: NodeProps) => {
  const d = data as NodeData;
  return shell(
    <p className={`text-xs font-medium leading-snug ${selected ? "text-fg" : "text-fg-muted"}`}>{d.label}</p>,
    selected ? "border-fg-muted/50" : "border-stroke",
    "bg-fg-tertiary",
    "Untrusted input",
  );
});

export const AgentNode = memo(({ data, selected }: NodeProps) => {
  const d = data as NodeData;
  return shell(
    <p className={`text-xs font-medium text-cyan ${selected ? "brightness-110" : ""}`}>{d.label}</p>,
    selected ? "border-cyan/50" : "border-cyan/30",
    "bg-cyan",
    "Agent / model",
  );
});

export const ToolNode = memo(({ data, selected }: NodeProps) => {
  const d = data as NodeData;
  return shell(
    <>
      <p className="text-xs font-medium text-coral">{d.label}</p>
      {d.outcome === "denied" && (
        <p className="text-[10px] text-coral mt-1 font-mono">BLOCKED</p>
      )}
    </>,
    "border-coral/40",
    "bg-coral",
    "Proposed action",
  );
});

export const GuardNode = memo(({ data, selected }: NodeProps) => {
  const d = data as NodeData;
  return (
    <div
      className={`min-w-[160px] rounded-xl border-2 px-3 py-2.5 bg-bg-s1 ${
        d.denied ? "border-chartreuse shadow-[0_0_0_1px_rgba(200,255,105,0.15)]" : "border-stroke"
      } ${selected ? "ring-2 ring-chartreuse/30" : ""}`}
    >
      <p className="text-[10px] font-mono uppercase text-chartreuse mb-1">Policy enforced</p>
      <p className="text-xs font-semibold text-fg">{d.label}</p>
      <Handle type="target" position={Position.Left} className="!bg-chartreuse !w-2 !h-2 !border-0" />
      <Handle type="source" position={Position.Right} className="!bg-chartreuse !w-2 !h-2 !border-0" />
      <Handle type="source" position={Position.Bottom} id="guard-out" className="!bg-chartreuse !w-2 !h-2 !border-0" />
    </div>
  );
});

export const EffectNode = memo(({ data, selected }: NodeProps) => {
  const d = data as NodeData;
  const blocked = d.outcome === "not_executed";
  return shell(
    <>
      <p className="text-xs font-medium">{d.label}</p>
      <p className={`text-[10px] mt-1 font-mono ${blocked ? "text-fg-muted" : "text-coral"}`}>
        {blocked ? "Not reached" : d.outcome ?? "—"}
      </p>
    </>,
    blocked ? "border-stroke opacity-60" : "border-coral/40",
    blocked ? "bg-fg-tertiary" : "bg-coral",
    "Business effect",
  );
});

export const ApprovalNode = memo(({ data }: NodeProps) => {
  const d = data as NodeData;
  return shell(
    <p className="text-xs text-discord">{d.label}</p>,
    "border-discord/40",
    "bg-discord",
    "Discord review",
  );
});

export const VerificationNode = memo(({ data }: NodeProps) => {
  const d = data as NodeData;
  return shell(
    <p className="text-xs text-chartreuse">{d.label}</p>,
    "border-chartreuse/35",
    "bg-chartreuse",
    "Verification",
  );
});

export const DefaultFlowNode = memo(({ data }: NodeProps) => {
  const d = data as NodeData;
  return shell(<p className="text-xs">{d.label}</p>, "border-stroke", "bg-fg-tertiary", d.kind);
});

export const nodeTypes = {
  untrusted: UntrustedNode,
  agent: AgentNode,
  tool: ToolNode,
  guard: GuardNode,
  effect: EffectNode,
  approval: ApprovalNode,
  verification: VerificationNode,
  default: DefaultFlowNode,
};
