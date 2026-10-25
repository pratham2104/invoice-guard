import type { Edge, Node } from "@xyflow/react";
import type { TraceEdge, TraceNode } from "../../types";

const X_SCALE = 200;

export function traceToFlow(
  nodes: TraceNode[],
  edges: TraceEdge[],
  denied: boolean,
): { nodes: Node[]; edges: Edge[] } {
  const flowNodes: Node[] = nodes.map((n, i) => {
    const x = (n.position[0] + 5) * X_SCALE;
    const y = n.position[2] * 48 + 120;
    const type = nodeType(n.kind);
    return {
      id: n.id,
      type,
      position: { x, y },
      data: {
        label: displayLabel(n),
        kind: n.kind,
        trust: n.trust,
        outcome: n.outcome,
        denied: denied && n.kind === "policy_gate",
        evidenceRefs: n.evidence_refs,
      },
      selectable: true,
    };
  });

  const flowEdges: Edge[] = edges.map((e) => ({
    id: e.id,
    source: e.from,
    target: e.to,
    type: "causal",
    data: { kind: e.kind, denied: e.kind === "denied_at_gate" },
    animated: e.kind === "proposed_action" && !denied,
  }));

  return { nodes: flowNodes, edges: flowEdges };
}

function nodeType(kind: TraceNode["kind"]): string {
  switch (kind) {
    case "untrusted_input":
      return "untrusted";
    case "agent":
    case "model_route":
      return "agent";
    case "tool_proposal":
      return "tool";
    case "policy_gate":
      return "guard";
    case "external_effect":
      return "effect";
    case "approval":
      return "approval";
    case "verification":
      return "verification";
    default:
      return "default";
  }
}

function displayLabel(n: TraceNode): string {
  if (n.kind === "model_route") return "Nemotron (local path)";
  if (n.kind === "agent") return "Agent reasoning";
  if (n.kind === "untrusted_input") return "Invoice (untrusted)";
  if (n.kind === "tool_proposal") return "Payment tool";
  if (n.kind === "policy_gate") return "Trust boundary";
  if (n.kind === "external_effect") return "Simulated payment";
  return n.label;
}
