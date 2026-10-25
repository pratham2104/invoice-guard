import { BaseEdge, EdgeLabelRenderer, getBezierPath, type EdgeProps } from "@xyflow/react";

export function CausalEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  markerEnd,
}: EdgeProps) {
  const d = data as { kind?: string; denied?: boolean } | undefined;
  const kind = d?.kind ?? "";
  const denied = d?.denied || kind === "denied_at_gate";

  const [path, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  let stroke = "#405265";
  let dash = undefined;
  if (kind === "proposed_action" || kind === "influence") {
    stroke = denied ? "#FF657A" : "#70C7E6";
    dash = denied ? "6 4" : undefined;
  }
  if (kind === "allowed_action") stroke = "#C8FF69";
  if (kind === "denied_at_gate") {
    stroke = "#FF657A";
    dash = "4 4";
  }

  return (
    <>
      <BaseEdge id={id} path={path} markerEnd={markerEnd} style={{ stroke, strokeWidth: 2, strokeDasharray: dash }} />
      {denied && (
        <EdgeLabelRenderer>
          <div
            className="pointer-events-none absolute flex items-center justify-center rounded-full border-2 border-coral bg-bg-s1 text-coral text-[10px] font-bold w-6 h-6"
            style={{ transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)` }}
            aria-label="Blocked at trust boundary"
          >
            ×
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}

export const edgeTypes = { causal: CausalEdge };
