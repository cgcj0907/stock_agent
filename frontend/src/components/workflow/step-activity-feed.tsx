"use client";

import * as React from "react";
import {
  Bot,
  CheckCircle2,
  Circle,
  Loader2,
  MinusCircle,
  XCircle,
} from "lucide-react";

import { AgentIcon } from "@/components/agent-icon";
import { findAgent } from "@/lib/agents/catalog";
import type { StepStatus, WorkflowStep } from "@/lib/workflows/catalog";
import { cn } from "@/lib/utils";

const STATUS_META: Record<
  StepStatus,
  { label: string; icon: React.ReactNode; text: string }
> = {
  pending: {
    label: "等待中",
    icon: <Circle className="size-3.5 text-muted-foreground/40" />,
    text: "text-muted-foreground",
  },
  running: {
    label: "正在执行…",
    icon: <Loader2 className="size-3.5 animate-spin text-emerald-500" />,
    text: "text-emerald-600 dark:text-emerald-400",
  },
  done: {
    label: "完成",
    icon: <CheckCircle2 className="size-3.5 text-emerald-500" />,
    text: "text-emerald-600 dark:text-emerald-400",
  },
  failed: {
    label: "失败",
    icon: <XCircle className="size-3.5 text-red-500" />,
    text: "text-red-600 dark:text-red-400",
  },
  skipped: {
    label: "跳过",
    icon: <MinusCircle className="size-3.5 text-amber-500" />,
    text: "text-amber-600 dark:text-amber-400",
  },
};

function StepRow({
  step,
  status,
  stream,
  thinking,
}: {
  step: WorkflowStep;
  status: StepStatus;
  /** 该步骤 LLM 已流式产出的正文增量（打字机渲染源） */
  stream?: string;
  /** 该步骤 LLM 的思考过程增量（reasoning_content，灰字思考区） */
  thinking?: string;
}) {
  const agent = findAgent(step.agent);
  const meta = STATUS_META[status] ?? STATUS_META.pending;
  const showStream = status === "running" && (!!stream || !!thinking);
  return (
    <li
      className={cn(
        "px-4 py-2 text-sm transition-colors",
        status === "running" && "bg-emerald-50/70 dark:bg-emerald-950/30"
      )}
    >
      <div className="flex items-center gap-2.5">
        <AgentIcon icon={agent?.icon} className="size-4" />
        <span className="min-w-0 flex-1 truncate font-medium">
          {agent?.name ?? step.agent}
        </span>
        <span
          className={cn(
            "flex shrink-0 items-center gap-1.5 text-xs font-medium",
            meta.text
          )}
        >
          {meta.icon}
          {meta.label}
        </span>
      </div>
      {showStream && (
        <div className="mt-2 flex flex-col gap-1.5 pl-6">
          {thinking && (
            <div className="flex gap-2">
              <span className="mt-0.5 size-1.5 shrink-0 animate-pulse rounded-full bg-amber-500/70" />
              <pre className="max-h-28 min-w-0 flex-1 overflow-y-auto whitespace-pre-wrap break-words rounded-lg border border-dashed border-muted-foreground/20 bg-muted/30 px-3 py-2 font-mono text-[11px] italic leading-5 text-muted-foreground/80">
                {thinking}
              </pre>
            </div>
          )}
          {stream && (
            <div className="flex gap-2">
              <span className="mt-0.5 size-1.5 shrink-0 animate-pulse rounded-full bg-emerald-500" />
              <pre className="max-h-40 min-w-0 flex-1 overflow-y-auto whitespace-pre-wrap break-words rounded-lg bg-muted/50 px-3 py-2 font-mono text-[11px] leading-5 text-muted-foreground">
                {stream}
                <span className="ml-0.5 inline-block h-3.5 w-1.5 animate-pulse rounded-sm bg-emerald-500 align-middle" />
              </pre>
            </div>
          )}
        </div>
      )}
    </li>
  );
}

/**
 * Codex 风格的处理动作流：在对话中逐行展示每个步骤的实时状态
 * （等待中 → 正在执行… → 完成 / 失败 / 跳过）。
 */
export function StepActivityFeed({
  steps,
  statuses,
  running,
  connected,
  companyLabel,
  streams,
  thinkings,
  className,
}: {
  steps: WorkflowStep[];
  statuses: Record<string, StepStatus>;
  running: boolean;
  connected?: boolean;
  companyLabel?: string;
  /** step id -> LLM 流式正文增量（运行中展示打字机效果） */
  streams?: Record<string, string>;
  /** step id -> LLM 思考过程增量（运行中展示灰字思考区） */
  thinkings?: Record<string, string>;
  className?: string;
}) {
  const failed = steps.some((s) => statuses[s.id] === "failed");
  const doneCount = steps.filter(
    (s) => statuses[s.id] === "done" || statuses[s.id] === "skipped"
  ).length;

  return (
    <div
      className={cn(
        "overflow-hidden rounded-2xl border bg-card",
        className
      )}
    >
      <div className="flex items-center justify-between gap-3 border-b bg-muted/30 px-4 py-2.5 dark:bg-muted/20">
        <div className="flex min-w-0 items-center gap-2 text-sm font-semibold">
          {running ? (
            <Loader2 className="size-4 shrink-0 animate-spin text-emerald-600 dark:text-emerald-400" />
          ) : failed ? (
            <XCircle className="size-4 shrink-0 text-red-500" />
          ) : (
            <Bot className="size-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
          )}
          <span className="truncate">
            {running
              ? companyLabel
                ? `正在分析 ${companyLabel}`
                : "正在分析…"
              : failed
                ? "分析未完成"
                : "分析完成"}
          </span>
        </div>
        <div className="flex shrink-0 items-center gap-2 text-xs text-muted-foreground">
          {running && connected && (
            <span className="flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 font-medium text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300">
              <span className="size-1.5 animate-pulse rounded-full bg-emerald-500" />
              实时
            </span>
          )}
          <span className="tabular-nums">
            {doneCount}/{steps.length}
          </span>
        </div>
      </div>
      <ol className="divide-y divide-border/60">
        {steps.map((s) => (
          <StepRow
            key={s.id}
            step={s}
            status={statuses[s.id] ?? "pending"}
            stream={streams?.[s.id]}
            thinking={thinkings?.[s.id]}
          />
        ))}
      </ol>
    </div>
  );
}
