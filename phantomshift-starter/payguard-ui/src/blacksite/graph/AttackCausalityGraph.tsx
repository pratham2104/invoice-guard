import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  useEdgesState,
  useNodesState,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { memo, useEffect, useMemo } from "react";
import type { TraceEdge, TraceNode } from "../../types";
import { traceToFlow } from "./layoutTrace";
import { edgeTypes } from "./CausalEdge";
import { nodeTypes } from "./flowNodes";

interface Props {
  nodes: TraceNode[];
  edges: TraceEdge[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  denied: boolean;
  motion: boolean;
}

function AttackCausalityGraphInner({ nodes, edges, selectedId, onSelect, denied, motion }: Props) {
  const initial = useMemo(() => traceToFlow(nodes, edges, denied), [nodes, edges, denied]);
  const [flowNodes, setNodes, onNodesChange] = useNodesState(initial.nodes);
  const [flowEdges, setEdges, onEdgesChange] = useEdgesState(initial.edges);

  useEffect(() => {
    const next = traceToFlow(nodes, edges, denied);
    setNodes(
      next.nodes.map((n) => ({
        ...n,
        selected: n.id === selectedId,
      })),
    );
    setEdges(next.edges.map((e) => ({ ...e, animated: motion && e.animated })));
  }, [nodes, edges, denied, selectedId, motion, setNodes, setEdges]);

  const onNodeClick = (_: React.MouseEvent, node: Node) => onSelect(node.id);

  return (
    <div className="flow-wrap" data-testid="causality-graph">
      <ReactFlow
        nodes={flowNodes}
        edges={flowEdges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={onNodeClick}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.4}
        maxZoom={1.4}
        proOptions={{ hideAttribution: true }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable
        aria-label="Attack causality graph"
      >
        <Background color="#263340" gap={20} size={1} />
        <Controls showInteractive={false} />
        <MiniMap
          nodeColor={(n) => {
            if (n.type === "guard") return "#C8FF69";
            if (n.type === "tool") return "#FF657A";
            return "#405265";
          }}
          maskColor="rgba(9,13,19,0.85)"
          className="!bg-bg-s2 !border-stroke"
        />
      </ReactFlow>
    </div>
  );
}

export const AttackCausalityGraph = memo(AttackCausalityGraphInner);
