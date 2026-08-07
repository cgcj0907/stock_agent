"use client";

import * as React from "react";
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { AgentIcon } from "@/components/agent-icon";
import { findAgent } from "@/lib/agents/catalog";
import type { StepStatus, WorkflowStep } from "@/lib/workflows/catalog";
import { layoutWorkflow } from "@/lib/workflows/layout";
import { cn } from "@/lib/utils";

const STATUS_LABEL: Record<StepStatus, string> = {
  pending: "待运行",
  running: "运行中",
  done: "已完成",
  failed: "失败",
  skipped: "已跳过",
};

/** 状态指示点：节点保持黑白简笔画，仅状态用彩色区分 */
export function StatusIndicator({
  status,
  className,
}: {
  status: StepStatus;
  className?: string;
}) {
  switch (status) {
    case "running":
      return (
        <span
          className={cn(
            "size-2 animate-pulse rounded-full bg-emerald-500",
            className
          )}
        />
      );
    case "done":
      return (
        <span className={cn("size-2 rounded-full bg-emerald-500", className)} />
      );
    case "failed":
      return (
        <span className={cn("size-2 rounded-full bg-red-500", className)} />
      );
    case "skipped":
      return (
        <span className={cn("size-2 rounded-full bg-amber-500", className)} />
      );
    default:
      return (
        <span
          className={cn("size-2 rounded-full bg-muted-foreground/40", className)}
        />
      );
  }
}

/** 按状态着色的连线：目标运行中→深灰虚线滚动动画；其余→中性灰 */
function buildEdges(
  steps: WorkflowStep[],
  statuses: Record<string, StepStatus>
): Edge[] {
  const edges: Edge[] = [];
  for (const s of steps) {
    for (const dep of s.deps) {
      const running = statuses[s.id] === "running";
      const color = running ? "#3f3f46" : "#a1a1aa";
      edges.push({
        id: `${dep}-${s.id}`,
        source: dep,
        target: s.id,
        type: "smoothstep",
        animated: running,
        style: {
          stroke: color,
          strokeWidth: running ? 2 : 1.5,
          strokeDasharray: running ? "5 4" : undefined,
          transition: "stroke 250ms ease, stroke-width 250ms ease",
        },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          width: 14,
          height: 14,
          color,
        },
      });
    }
  }
  return edges;
}

function AgentFlowNode({ data }: NodeProps) {
  const status = (data.status as StepStatus) ?? "pending";
  const agent = findAgent(data.agent as string);
  const code = (agent?.code as string) ?? (data.code as string) ?? "";
  const name = agent?.name ?? (data.agent as string);
  return (
    <div
      className="relative w-[150px] rounded-xl border border-border bg-card px-3 py-2.5 shadow-sm transition-shadow hover:shadow-md"
      title={`${code} ${name} · ${STATUS_LABEL[status]}`}
    >
      <Handle
        type="target"
        position={Position.Left}
        className="!h-2 !w-2 !border-0 !bg-muted-foreground/50"
      />
      <div className="flex items-center gap-2">
        <AgentIcon icon={agent?.icon} className="size-4" />
        <div className="min-w-0">
          <div className="truncate text-xs font-semibold leading-tight">
            {code}
          </div>
          <div className="truncate text-[10px] leading-tight text-muted-foreground">
            {name}
          </div>
        </div>
        <span className="ml-auto flex shrink-0 items-center">
          <StatusIndicator status={status} />
        </span>
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
  height,
}: {
  steps: WorkflowStep[];
  statuses: Record<string, StepStatus>;
  height?: number;
}) {
  const layout = React.useMemo(
    () => layoutWorkflow(steps, { nodeWidth: 150 }),
    [steps]
  );

  const { nodes, edges } = React.useMemo(() => {
    const nodes: Node[] = steps.map((s) => ({
      id: s.id,
      type: "agentFlow",
      position: layout.positions[s.id] ?? { x: 0, y: 0 },
      data: {
        agent: s.agent,
        code: s.id,
        status: statuses[s.id] ?? "pending",
      },
    }));
    return { nodes, edges: buildEdges(steps, statuses) };
  }, [steps, statuses, layout]);

  // 未显式指定高度时，按排版结果自适应（并夹在可读区间内）
  const autoHeight = React.useMemo(() => {
    if (height && height > 0) return height;
    return Math.min(Math.max(Math.ceil(layout.height), 220), 400);
  }, [height, layout]);

  return (
    <div style={{ height: autoHeight }} className="w-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.18 }}
        nodesConnectable={false}
        nodesDraggable={false}
        elementsSelectable={false}
        zoomOnScroll={false}
        minZoom={0.3}
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={24} size={1} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
