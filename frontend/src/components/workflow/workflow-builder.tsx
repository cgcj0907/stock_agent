"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  addEdge,
  Background,
  Controls,
  Handle,
  Position,
  ReactFlow,
  useEdgesState,
  useNodesState,
  type Connection,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { ArrowLeft, Play, Plus, Save, X } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { AgentIcon } from "@/components/agent-icon";
import { LOCAL_AGENTS, type AgentInfo } from "@/lib/agents/catalog";
import type {
  CustomWorkflow,
  CustomWorkflowStep,
} from "@/types/custom-workflow";

/** 节点删除回调（经 Context 传给自定义节点） */
const DeleteContext = React.createContext<(id: string) => void>(() => {});

function BuilderNode({ id, data }: NodeProps) {
  const onDelete = React.useContext(DeleteContext);
  const agent = data.agent as AgentInfo;
  return (
    <div className="relative rounded-xl border bg-card px-3 py-2.5 shadow-sm">
      <Handle
        type="target"
        position={Position.Left}
        className="!h-2 !w-2 !border-0 !bg-muted-foreground/50"
      />
      <div className="flex items-center gap-2">
        <AgentIcon icon={agent?.icon} className="size-4" />
        <div className="min-w-0">
          <div className="truncate text-xs font-semibold leading-tight">
            {agent?.code ?? ""}
          </div>
          <div className="truncate text-[10px] leading-tight text-muted-foreground">
            {agent?.name ?? ""}
          </div>
        </div>
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onDelete(id);
          }}
          className="ml-1 rounded-md p-0.5 text-muted-foreground transition-colors hover:bg-muted hover:text-destructive"
          aria-label="移除"
        >
          <X className="size-3.5" />
        </button>
      </div>
      <Handle
        type="source"
        position={Position.Right}
        className="!h-2 !w-2 !border-0 !bg-muted-foreground/50"
      />
    </div>
  );
}

const nodeTypes = { builderNode: BuilderNode };

type BuilderNodeData = { agent: AgentInfo };

export function WorkflowBuilder({
  initial,
}: {
  initial?: CustomWorkflow | null;
}) {
  const router = useRouter();
  const [name, setName] = React.useState(initial?.name ?? "");
  const [description, setDescription] = React.useState(
    initial?.description ?? ""
  );
  const [savedId, setSavedId] = React.useState<string | null>(
    initial?.id ?? null
  );
  const [saving, setSaving] = React.useState(false);

  const [nodes, setNodes, onNodesChange] = useNodesState<Node<BuilderNodeData>>(
    (initial?.steps ?? []).map((s, i) => ({
      id: s.id,
      type: "builderNode",
      position: { x: 40 + (i % 3) * 200, y: 40 + Math.floor(i / 3) * 100 },
      data: {
        agent: LOCAL_AGENTS.find((a) => a.id === s.agent) ?? LOCAL_AGENTS[0],
      },
    })) as Node<BuilderNodeData>[]
  );
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>(
    (initial?.steps ?? []).flatMap((s) =>
      s.deps.map((dep) => ({
        id: `${dep}-${s.id}`,
        source: dep,
        target: s.id,
        type: "smoothstep",
      }))
    ) as Edge[]
  );

  const handleDelete = React.useCallback(
    (id: string) => {
      setNodes((nds) => nds.filter((n) => n.id !== id));
      setEdges((eds) => eds.filter((e) => e.source !== id && e.target !== id));
    },
    [setNodes, setEdges]
  );

  function addAgent(agent: AgentInfo) {
    if (nodes.some((n) => n.id === agent.id)) {
      toast.info("该智能体已在画布中");
      return;
    }
    const position = {
      x: 60 + (nodes.length % 4) * 190,
      y: 40 + Math.floor(nodes.length / 4) * 100,
    };
    setNodes((nds) => [
      ...nds,
      { id: agent.id, type: "builderNode", position, data: { agent } },
    ]);
  }

  const handleConnect = React.useCallback(
    (conn: Connection) => {
      if (!conn.source || !conn.target || conn.source === conn.target) return;
      setEdges((eds) =>
        addEdge({ ...conn, type: "smoothstep" }, eds)
      );
    },
    [setEdges]
  );

  const handleNodesDelete = React.useCallback(
    (deleted: Node[]) => {
      const ids = new Set(deleted.map((n) => n.id));
      setEdges((eds) =>
        eds.filter((e) => !ids.has(e.source) && !ids.has(e.target))
      );
    },
    [setEdges]
  );

  async function handleSave() {
    if (!name.trim()) {
      toast.error("请填写工作流名称");
      return;
    }
    const steps: CustomWorkflowStep[] = nodes.map((n) => ({
      id: n.id,
      agent: n.data.agent.id,
      deps: edges.filter((e) => e.target === n.id).map((e) => e.source),
    }));
    if (steps.length === 0) {
      toast.error("请至少添加一个智能体");
      return;
    }
    setSaving(true);
    try {
      const url = savedId
        ? `/api/custom-workflows/${savedId}`
        : "/api/custom-workflows";
      const res = await fetch(url, {
        method: savedId ? "PATCH" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, description, steps }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "保存失败");
      setSavedId(data.workflow.id);
      toast.success("工作流已保存");
      router.refresh();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-5">
      <div>
        <Button asChild variant="ghost" size="sm" className="mb-2 w-fit rounded-lg">
          <Link href="/workflows">
            <ArrowLeft className="size-4" />
            返回工作流
          </Link>
        </Button>
        <h1 className="text-2xl font-semibold tracking-tight">工作流编排器</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          从左侧添加智能体，连线表示依赖关系，保存后即可运行
        </p>
      </div>

      <div className="flex flex-col gap-4 lg:flex-row">
        {/* Agent 面板 */}
        <Card className="h-fit shrink-0 rounded-2xl lg:w-56">
          <CardContent className="flex flex-col gap-2 p-3">
            <Label className="px-1 text-xs text-muted-foreground">
              智能体（点击添加）
            </Label>
            {LOCAL_AGENTS.map((agent) => {
              const added = nodes.some((n) => n.id === agent.id);
              return (
                <button
                  key={agent.id}
                  type="button"
                  onClick={() => addAgent(agent)}
                  disabled={added}
                  className="flex items-center gap-2 rounded-xl border px-2.5 py-2 text-left text-xs transition-colors hover:border-emerald-300 hover:bg-emerald-50/50 disabled:cursor-not-allowed disabled:opacity-40 dark:hover:border-emerald-700 dark:hover:bg-emerald-950/30"
                >
                  <AgentIcon icon={agent.icon} className="size-4" />
                  <span className="min-w-0 flex-1 truncate font-medium">
                    {agent.name}
                  </span>
                  {added ? (
                    <Badge variant="secondary" className="rounded-md px-1.5 text-[9px]">
                      已加
                    </Badge>
                  ) : (
                    <Plus className="size-3.5 text-muted-foreground" />
                  )}
                </button>
              );
            })}
          </CardContent>
        </Card>

        {/* 画布 + 表单 */}
        <div className="flex min-w-0 flex-1 flex-col gap-3">
          <div className="flex flex-col gap-3 sm:flex-row">
            <div className="flex flex-1 flex-col gap-1.5">
              <Label htmlFor="wf-name">工作流名称 *</Label>
              <Input
                id="wf-name"
                placeholder="例如：快速成长股筛查"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
            <div className="flex flex-1 flex-col gap-1.5">
              <Label htmlFor="wf-desc">描述（可选）</Label>
              <Input
                id="wf-desc"
                placeholder="这个流程用来做什么"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </div>
          </div>

          <Card className="overflow-hidden rounded-2xl">
            <DeleteContext.Provider value={handleDelete}>
              <div className="h-[460px]">
                <ReactFlow
                  nodes={nodes}
                  edges={edges}
                  nodeTypes={nodeTypes}
                  onNodesChange={onNodesChange}
                  onEdgesChange={onEdgesChange}
                  onConnect={handleConnect}
                  onNodesDelete={handleNodesDelete}
                  deleteKeyCode={["Backspace", "Delete"]}
                  fitView
                  fitViewOptions={{ padding: 0.2 }}
                  minZoom={0.4}
                  proOptions={{ hideAttribution: true }}
                >
                  <Background gap={24} />
                  <Controls showInteractive={false} />
                </ReactFlow>
              </div>
            </DeleteContext.Provider>
            <div className="border-t px-4 py-2.5 text-xs text-muted-foreground">
              从左侧点击添加智能体；拖拽节点右侧圆点到另一节点表示「依赖」；
              选中节点按 Delete / 点击 × 移除
            </div>
          </Card>

          <div className="flex items-center gap-2">
            <Button onClick={handleSave} disabled={saving} className="rounded-full">
              {saving ? "保存中…" : "保存工作流"}
              <Save className="ml-1.5 size-4" />
            </Button>
            {savedId && (
              <Button asChild variant="outline" className="rounded-full">
                <Link href={`/workflows/custom/${savedId}`}>
                  开始分析 <Play className="ml-1.5 size-4" />
                </Link>
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
