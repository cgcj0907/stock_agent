"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  addEdge,
  Background,
  Controls,
  Handle,
  MarkerType,
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
import { ArrowLeft, ArrowRight, Info, LayoutGrid, Play, Plus, Save, X } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { AgentIcon } from "@/components/agent-icon";
import { LOCAL_AGENTS, findAgent, type AgentInfo } from "@/lib/agents/catalog";
import {
  CONNECTION_HINTS,
  connectionWarning,
  type ConnectionHint,
} from "@/lib/workflows/connection-hints";
import { layoutWorkflow } from "@/lib/workflows/layout";
import { WORKFLOWS } from "@/lib/workflows/catalog";
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
    <div className="relative w-[150px] rounded-xl border border-border bg-card px-3 py-2.5 shadow-sm transition-shadow hover:shadow-md">
      <Handle
        type="target"
        position={Position.Left}
        className="!h-2 !w-2 !border-0 !bg-muted-foreground/50"
      />
      <div className="flex items-center gap-2">
        <AgentIcon icon={agent?.icon} className="size-4" />
        <div className="min-w-0 flex-1">
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
          className="ml-0.5 rounded-md p-0.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
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

/** 由当前节点与连线生成 WorkflowStep 列表，供自动排版使用 */
function toSteps(
  nodes: Node<BuilderNodeData>[],
  edges: Edge[]
): CustomWorkflowStep[] {
  return nodes.map((n) => ({
    id: n.id,
    agent: n.data.agent.id,
    deps: edges.filter((e) => e.target === n.id).map((e) => e.source),
  }));
}

/** 加入 source→target 连线后是否成环（DFS 从 target 能否回到 source）。 */
function wouldCreateCycle(source: string, target: string, edges: Edge[]): boolean {
  const adj = new Map<string, string[]>();
  for (const e of edges) {
    const list = adj.get(e.source) ?? [];
    list.push(e.target);
    adj.set(e.source, list);
  }
  const stack = [target];
  const seen = new Set<string>();
  while (stack.length) {
    const cur = stack.pop()!;
    if (cur === source) return true;
    if (seen.has(cur)) continue;
    seen.add(cur);
    for (const next of adj.get(cur) ?? []) stack.push(next);
  }
  return false;
}

/** 「连接提示」芯片行：点击自动补节点+连线（已连接的显示为绿色 ✓） */
function HintChips({
  label,
  icon: Icon,
  items,
  selectedId,
  connected,
  mode,
  muted,
  onConnect,
}: {
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  items: string[];
  selectedId: string | null;
  connected: Set<string>;
  mode: "source" | "target";
  muted?: boolean;
  onConnect: (from: string, to: string) => void;
}) {
  if (items.length === 0) return null;
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
        <Icon className="size-3.5" />
        {label}
      </div>
      <div className="flex flex-wrap gap-1.5">
        {items.map((id) => {
          const agent = findAgent(id);
          const isConnected = connected.has(id);
          return (
            <button
              key={id}
              type="button"
              onClick={() => {
                if (!selectedId) return;
                if (mode === "source") onConnect(id, selectedId);
                else onConnect(selectedId, id);
              }}
              disabled={isConnected}
              title={agent?.description}
              className={`flex items-center gap-1 rounded-lg border px-2 py-1 text-[11px] transition-colors disabled:cursor-default ${
                isConnected
                  ? "border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300"
                  : muted
                    ? "border-dashed border-border/70 text-muted-foreground hover:border-sky-300 hover:bg-sky-50/60 hover:text-sky-700 dark:hover:border-sky-700 dark:hover:bg-sky-950/30 dark:hover:text-sky-300"
                    : "border-border/70 text-foreground/80 hover:border-sky-300 hover:bg-sky-50/60 hover:text-sky-700 dark:hover:border-sky-700 dark:hover:bg-sky-950/30 dark:hover:text-sky-300"
              }`}
            >
              <span className="font-semibold">{agent?.code ?? ""}</span>
              <span>{agent?.name ?? id}</span>
              {isConnected && <span>✓</span>}
            </button>
          );
        })}
      </div>
    </div>
  );
}

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
  // 当前选中的节点 id（用于展示「连接提示」面板）
  const [selectedId, setSelectedId] = React.useState<string | null>(null);

  const initialSteps: CustomWorkflowStep[] = initial?.steps ?? [];
  const initialLayout = React.useMemo(
    () => layoutWorkflow(initialSteps, { columnGap: 230, rowGap: 110, nodeWidth: 150 }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  );

  const [nodes, setNodes, onNodesChange] = useNodesState<Node<BuilderNodeData>>(
    initialSteps.map((s) => ({
      id: s.id,
      type: "builderNode",
      position:
        initialLayout.positions[s.id] ?? { x: 60, y: 40 },
      data: {
        agent: LOCAL_AGENTS.find((a) => a.id === s.agent) ?? LOCAL_AGENTS[0],
      },
    })) as Node<BuilderNodeData>[]
  );
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>(
    initialSteps.flatMap((s) =>
      s.deps.map((dep) => ({
        id: `${dep}-${s.id}`,
        source: dep,
        target: s.id,
        type: "smoothstep",
        style: { stroke: "#a1a1aa", strokeWidth: 1.75 },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          width: 14,
          height: 14,
          color: "#a1a1aa",
        },
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

  /** 在网格中寻找不与现有节点重叠的空位 */
  function findFreeSlot(occupied: { x: number; y: number }[]) {
    for (let row = 0; row < 12; row++) {
      for (let col = 0; col < 8; col++) {
        const x = 60 + col * 230;
        const y = 40 + row * 110;
        if (
          !occupied.some(
            (p) => Math.abs(p.x - x) < 190 && Math.abs(p.y - y) < 100
          )
        ) {
          return { x, y };
        }
      }
    }
    return { x: 60 + occupied.length * 20, y: 40 };
  }

  function addAgent(agent: AgentInfo) {
    setNodes((nds) => {
      if (nds.some((n) => n.id === agent.id)) {
        return nds;
      }
      const position = findFreeSlot(nds.map((n) => n.position));
      return [
        ...nds,
        {
          id: agent.id,
          type: "builderNode",
          position,
          data: { agent },
        },
      ];
    });
  }

  /** 一键自动排版：按依赖深度分层、层内降交叉、列居中 */
  function handleAutoLayout() {
    if (nodes.length === 0) return;
    const steps = toSteps(nodes, edges);
    const layout = layoutWorkflow(steps, { columnGap: 230, rowGap: 110, nodeWidth: 150 });
    setNodes((nds) =>
      nds.map((n) => ({
        ...n,
        position: layout.positions[n.id] ?? n.position,
      }))
    );
    toast.success("已自动排版");
  }

  /** 载入内置工作流模板：节点 + 依赖连线 + 自动排版 */
  function applyPreset(wf: (typeof WORKFLOWS)[number]) {
    const layout = layoutWorkflow(wf.steps, {
      columnGap: 230,
      rowGap: 110,
      nodeWidth: 150,
    });
    setNodes(
      wf.steps.map((s) => ({
        id: s.id,
        type: "builderNode",
        position: layout.positions[s.id] ?? { x: 60, y: 40 },
        data: {
          agent:
            LOCAL_AGENTS.find((a) => a.id === s.agent) ?? LOCAL_AGENTS[0],
        },
      })) as Node<BuilderNodeData>[]
    );
    setEdges(
      wf.steps.flatMap((s) =>
        s.deps.map((dep) => ({
          id: `${dep}-${s.id}`,
          source: dep,
          target: s.id,
          type: "smoothstep",
          style: { stroke: "#10b981", strokeWidth: 1.75 },
          markerEnd: {
            type: MarkerType.ArrowClosed,
            width: 14,
            height: 14,
            color: "#10b981",
          },
        }))
      ) as Edge[]
    );
    setSelectedId(null);
    toast.success(`已载入模板「${wf.name}」（${wf.steps.length} 个智能体）`);
  }

  /** 清空画布 */
  function clearCanvas() {
    setNodes([]);
    setEdges([]);
    setSelectedId(null);
    toast.success("已清空画布");
  }

  const handleConnect = React.useCallback(
    (conn: Connection) => {
      if (!conn.source || !conn.target || conn.source === conn.target) return;
      if (wouldCreateCycle(conn.source, conn.target, edges)) {
        toast.error("不能形成循环依赖（A 依赖 B、B 又依赖 A）");
        return;
      }
      const warning = connectionWarning(conn.source, conn.target);
      if (warning) {
        const srcName = findAgent(conn.source)?.name ?? conn.source;
        const tgtName = findAgent(conn.target)?.name ?? conn.target;
        toast.warning(`⚠️ ${srcName} 通常不建议直接接在 ${tgtName} 后面`, {
          description: warning,
        });
      }
      setEdges((eds) =>
        addEdge(
          {
            ...conn,
            type: "smoothstep",
            style: { stroke: "#a1a1aa", strokeWidth: 1.75 },
            markerEnd: {
              type: MarkerType.ArrowClosed,
              width: 14,
              height: 14,
              color: "#a1a1aa",
            },
          },
          eds
        )
      );
    },
    [setEdges, edges]
  );

  /** 确保画布存在某 agent 节点（缺失则添加，供「一键连线」使用） */
  function ensureNode(agentId: string) {
    setNodes((nds) => {
      if (nds.some((n) => n.id === agentId)) return nds;
      const agent = LOCAL_AGENTS.find((a) => a.id === agentId);
      if (!agent) return nds;
      const position = findFreeSlot(nds.map((n) => n.position));
      return [...nds, { id: agent.id, type: "builderNode", position, data: { agent } }];
    });
  }

  /** 点击建议芯片：自动补节点 + 连线（防重复、防环） */
  function connectSuggestion(from: string, to: string) {
    ensureNode(from);
    ensureNode(to);
    setEdges((eds) => {
      if (eds.some((e) => e.source === from && e.target === to)) return eds;
      if (wouldCreateCycle(from, to, eds)) {
        toast.error("不能形成循环依赖（A 依赖 B、B 又依赖 A）");
        return eds;
      }
      return addEdge(
        {
          id: `${from}-${to}`,
          source: from,
          target: to,
          type: "smoothstep",
          style: { stroke: "#10b981", strokeWidth: 1.75 },
          markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14, color: "#10b981" },
        },
        eds
      );
    });
  }

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
        method: savedId ? "PUT" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, description, steps }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || "保存失败");
      }
      if (!savedId) setSavedId(data.id as string);
      toast.success("工作流已保存");
      router.refresh();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  const selectedAgent = selectedId ? findAgent(selectedId) : undefined;
  const hint: ConnectionHint | undefined = selectedId
    ? CONNECTION_HINTS[selectedId]
    : undefined;
  const currentUpstream = new Set(
    edges.filter((e) => e.target === selectedId).map((e) => e.source)
  );
  const currentDownstream = new Set(
    edges.filter((e) => e.source === selectedId).map((e) => e.target)
  );
  const unusual = hint
    ? [...currentUpstream].filter(
        (s) => !hint.suggestedDeps.includes(s) && !hint.optionalUpstream.includes(s)
      )
    : [];

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
            <div className="flex flex-wrap items-center justify-between gap-2 border-b bg-muted/30 px-4 py-2 dark:bg-muted/20">
              <span className="text-xs font-medium text-muted-foreground">
                DAG 画布 · {nodes.length} 个节点 · 拖拽可调整位置
              </span>
              <div className="flex items-center gap-1.5">
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 rounded-lg px-2.5 text-xs"
                  onClick={() => applyPreset(WORKFLOWS[0])}
                >
                  标准分析模板
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 rounded-lg px-2.5 text-xs"
                  onClick={() => applyPreset(WORKFLOWS[1])}
                >
                  快速估值模板
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 rounded-lg px-2.5 text-xs text-destructive"
                  onClick={clearCanvas}
                  disabled={nodes.length === 0}
                >
                  清空
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 rounded-lg px-2.5 text-xs"
                  onClick={handleAutoLayout}
                  disabled={nodes.length === 0}
                >
                  <LayoutGrid className="size-3.5" />
                  自动排版
                </Button>
              </div>
            </div>
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
                  onNodeClick={(_, node) => setSelectedId(node.id)}
                  onPaneClick={() => setSelectedId(null)}
                  onEdgeClick={(_, edge) => {
                    setEdges((eds) => eds.filter((e) => e.id !== edge.id));
                    toast.success("已移除连线");
                  }}
                  deleteKeyCode={["Backspace", "Delete"]}
                  fitView
                  fitViewOptions={{ padding: 0.15 }}
                  minZoom={0.3}
                  proOptions={{ hideAttribution: true }}
                >
                  <Background gap={24} size={1} />
                  <Controls showInteractive={false} />
                </ReactFlow>
              </div>
            </DeleteContext.Provider>
            <div className="border-t px-4 py-2.5 text-xs text-muted-foreground">
              从左侧点击添加智能体；拖拽节点右侧圆点到另一节点表示「依赖」；
              选中节点查看「连接提示」；选中节点按 Delete / 点击 × 移除；点击连线可移除；连线杂乱时可用「自动排版」一键整理
            </div>
          </Card>

          {selectedAgent && hint && (
            <Card className="rounded-2xl">
              <CardContent className="flex flex-col gap-3 p-4">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <Info className="size-4 text-sky-600 dark:text-sky-400" />
                    <span className="text-sm font-semibold">
                      连接提示 · {selectedAgent.name}
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => setSelectedId(null)}
                    className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                    aria-label="关闭提示"
                  >
                    <X className="size-3.5" />
                  </button>
                </div>
                {hint.note && (
                  <p className="text-xs leading-5 text-muted-foreground">{hint.note}</p>
                )}
                <HintChips
                  label="建议上游（可接在前面）"
                  icon={ArrowLeft}
                  items={hint.suggestedDeps}
                  selectedId={selectedId}
                  connected={currentUpstream}
                  mode="source"
                  onConnect={connectSuggestion}
                />
                <HintChips
                  label="建议下游（可接在后面）"
                  icon={ArrowRight}
                  items={hint.suggestedDownstream}
                  selectedId={selectedId}
                  connected={currentDownstream}
                  mode="target"
                  onConnect={connectSuggestion}
                />
                <HintChips
                  label="可选上游（个性化画像）"
                  icon={ArrowLeft}
                  items={hint.optionalUpstream}
                  selectedId={selectedId}
                  connected={currentUpstream}
                  mode="source"
                  muted
                  onConnect={connectSuggestion}
                />
                {unusual.length > 0 && (
                  <div className="flex flex-col gap-1.5 rounded-lg border border-amber-200/60 bg-amber-50/50 px-3 py-2 dark:border-amber-900/60 dark:bg-amber-950/30">
                    <span className="text-[11px] font-bold uppercase tracking-wider text-amber-700 dark:text-amber-300">
                      当前非常规连接
                    </span>
                    <ul className="flex flex-wrap gap-1.5">
                      {unusual.map((id) => {
                        const agent = findAgent(id);
                        return (
                          <li
                            key={id}
                            className="text-[11px] text-amber-700 dark:text-amber-300"
                          >
                            {agent?.code} {agent?.name}
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

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
