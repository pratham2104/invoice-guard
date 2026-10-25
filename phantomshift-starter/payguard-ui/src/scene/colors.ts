import type { EdgeKind, NodeKind } from "../types";

export function nodeColor(kind: NodeKind, selected: boolean, denied: boolean): string {
  if (kind === "policy_gate" && denied) return "#FF6179";
  if (kind === "external_effect" && denied) return "#243142";
  const map: Record<NodeKind, string> = {
    untrusted_input: "#5CD6F6",
    trusted_instruction: "#9AA8BA",
    agent: "#AA91FF",
    model_route: "#AA91FF",
    tool_proposal: "#F7BD66",
    policy_gate: "#53D6A1",
    external_effect: "#FF6179",
    approval: "#F7BD66",
    verification: "#53D6A1",
  };
  return selected ? "#EAF0F8" : map[kind];
}

export function edgeColor(kind: EdgeKind): string {
  if (kind === "denied_at_gate") return "#FF6179";
  if (kind === "allowed_action") return "#53D6A1";
  if (kind === "influence") return "#F7BD66";
  if (kind === "proposed_action") return "#AA91FF";
  return "#5CD6F6";
}
