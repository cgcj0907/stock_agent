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
}: {
  step: WorkflowStep;
  status: StepStatus;
}) {
  const agent = findAgent(step.agent);
  const meta = STATUS_META[status] ?? STATUS_META.pending;
  return (
    <li
      className={cn(
        "flex items-center gap-2.5 px-4 py-2 text-sm transition-colors",
        status === "running" && "bg-emerald-50/70 dark:bg-emerald-950/30"
      )}
    >
      <span className="text-base leading-none">{agent?.emoji ?? "🤖"}</span>
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
  className,
}: {
  steps: WorkflowStep[];
  statuses: Record<string, StepStatus>;
  running: boolean;
  connected?: boolean;
  companyLabel?: string;
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
          <StepRow key={s.id} step={s} status={statuses[s.id] ?? "pending"} />
        ))}
      </ol>
    </div>
  );
}
