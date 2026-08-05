"use client";

import * as React from "react";
import {
  Background,
  Controls,
  Handle,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { findAgent } from "@/lib/agents/catalog";
import {
  computeStepDepths,
  type StepStatus,
  type WorkflowStep,
} from "@/lib/workflows/catalog";

const STATUS_META: Record<
  StepStatus,
  { label: string; nodeClass: string; dot: string }
> = {
  pending: {
    label: "待运行",
    nodeClass: "border-border bg-card",
    dot: "bg-muted-foreground/40",
  },
  running: {
    label: "运行中",
    nodeClass:
      "border-emerald-400 bg-emerald-50 ring-2 ring-emerald-400/50 dark:bg-emerald-950/40",
    dot: "bg-emerald-500 animate-pulse",
  },
  done: {
    label: "已完成",
    nodeClass:
      "border-emerald-200 bg-emerald-50/80 dark:border-emerald-800 dark:bg-emerald-950/30",
    dot: "bg-emerald-500",
  },
  failed: {
    label: "失败",
    nodeClass: "border-red-300 bg-red-50 dark:border-red-800 dark:bg-red-950/40",
    dot: "bg-red-500",
  },
  skipped: {
    label: "已跳过",
    nodeClass:
      "border-amber-200 bg-amber-50/70 opacity-70 dark:border-amber-800 dark:bg-amber-950/30",
    dot: "bg-amber-500",
  },
};

function AgentFlowNode({ data }: NodeProps) {
  const status = (data.status as StepStatus) ?? "pending";
  const meta = STATUS_META[status];
  const agent = findAgent(data.agent as string);
  return (
    <div
      className={`relative w-[150px] rounded-xl border bg-card px-3 py-2.5 shadow-sm transition-colors ${meta.nodeClass}`}
    >
      <Handle
        type="target"
        position={Position.Left}
        className="!h-2 !w-2 !border-0 !bg-muted-foreground/50"
      />
      <div className="flex items-center gap-2">
        <span className="text-base leading-none">{agent?.emoji ?? "🤖"}</span>
        <div className="min-w-0">
          <div className="truncate text-xs font-semibold leading-tight">
            {data.code as string}
          </div>
          <div className="truncate text-[10px] leading-tight text-muted-foreground">
            {agent?.name ?? (data.agent as string)}
          </div>
        </div>
        <span
          className={`ml-auto size-2 shrink-0 rounded-full ${meta.dot}`}
          title={meta.label}
        />
      </div>
      <Handle
        type="source"
        position={Position.Right}
        className="!h-2 !w-2 !border-0 !bg-muted-foreground/50"
      />
    </div>
  );
}

const nodeTypes = { agentFlow: AgentFlowNode };

export function WorkflowDag({
  steps,
  statuses,
  height = 240,
}: {
  steps: WorkflowStep[];
  statuses: Record<string, StepStatus>;
  height?: number;
}) {
  const { nodes, edges } = React.useMemo(() => {
    const depth = computeStepDepths(steps);
    const columns: Record<number, string[]> = {};
    for (const s of steps) {
      (columns[depth[s.id]] ??= []).push(s.id);
    }

    const nodes: Node[] = steps.map((s) => ({
      id: s.id,
      type: "agentFlow",
      position: {
        x: depth[s.id] * 180,
        y: (columns[depth[s.id]].indexOf(s.id) ?? 0) * 86,
      },
      data: {
        agent: s.agent,
        code: s.id,
        status: statuses[s.id] ?? "pending",
      },
    }));

    const edges: Edge[] = [];
    for (const s of steps) {
      for (const dep of s.deps) {
        edges.push({
          id: `${dep}-${s.id}`,
          source: dep,
          target: s.id,
          type: "smoothstep",
          style: { strokeWidth: 1.5 },
        });
      }
    }
    return { nodes, edges };
  }, [steps, statuses]);

  return (
    <div style={{ height }} className="w-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.25 }}
        nodesConnectable={false}
        nodesDraggable={false}
        elementsSelectable={false}
        zoomOnScroll={false}
        minZoom={0.4}
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={24} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
